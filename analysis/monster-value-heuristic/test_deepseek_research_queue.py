from concurrent.futures import ThreadPoolExecutor
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import deepseek_research_queue as queue


class FakeClient:
    def __init__(self, registry, calls, lock, failure=None, secret="FAKE_SECRET"):
        self.registry, self.calls, self.lock, self.failure, self.secret = registry, calls, lock, failure, secret

    def complete(self, payload):
        task = self.registry[queue.digest(payload)]
        with self.lock:
            self.calls.append((task["id"], threading.get_ident(), id(self)))
        time.sleep(.015)
        if self.failure == task["id"]:
            raise RuntimeError("fake failure " + self.secret)
        kind = task["context"]["kind"]
        rows = []
        if kind == "inventory":
            for card in task["context"]["cards"]:
                text = card["effect_readable"]
                rows.append({"card_id": card["id"], "printed_effect": text, "modules": [],
                             "conditions": [], "condition_codes": [], "timing": "none", "silence_exposure": "none",
                             "unresolved": ["offline fake response, not a semantic judgment"] if text else [],
                             "notes": "offline test only", "annotation_status": "placeholder" if text else "parsed"})
        data = {"task_id": task["id"], "kind": kind, "annotations": rows, "findings": [], "unresolved": []}
        return {"model": "fake-local", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(data, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 2000, "completion_tokens": 100, "total_tokens": 2100,
                          "prompt_tokens_details": {"cached_tokens": 1024}}}

    def redact(self, value):
        return str(value).replace(self.secret, "[REDACTED]")


class ResearchQueueTests(unittest.TestCase):
    def setUp(self):
        # Explicit workspace parent also keeps temporary cleanup confined here.
        self.temp = tempfile.TemporaryDirectory(dir=queue.HERE)
        self.root = Path(self.temp.name)
        self.folder = self.root / "queue"
        queue.make_plan(self.folder)
        self.manifest, self.api = queue.verify_plan(self.folder)
        self.calls, self.lock = [], threading.Lock()
        self.registry = {queue.digest(self.manifest["payloads"][task["id"]]): task for task in self.manifest["tasks"]}

    def tearDown(self):
        self.assertEqual(self.root.resolve().parent, queue.HERE.resolve())
        self.temp.cleanup()

    def factory(self, failure=None):
        return lambda: FakeClient(self.registry, self.calls, self.lock, failure)

    def run_offline(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return queue.run(self.folder, client_factory=self.factory(), **kwargs)

    def test_fixed_inventory_and_full_shared_prefix_and_reference_provenance(self):
        self.assertEqual(len(self.manifest["tasks"]), 12)
        self.assertEqual(self.manifest["shared_prefix_message_count"], 29)
        new_ids = []
        for task in self.manifest["tasks"]:
            payload = self.manifest["payloads"][task["id"]]
            self.assertEqual(payload["messages"][:-1], self.manifest["shared_prefix"])
            self.assertEqual(payload["messages"][-1]["role"], "user")
            if task["context"]["kind"] == "inventory":
                ids = [card["id"] for card in task["context"]["cards"]]
                self.assertEqual(len(ids), 10)
                self.assertTrue(set(queue.PROBES) <= set(ids))
                new_ids.extend(task["context"]["requested_card_ids"])
                self.assertTrue(all(card["effect_readable"] is not None and card["source_id"] == "card:" + str(card["id"])
                                    for card in task["context"]["references"]))
        self.assertEqual(len(set(new_ids)), 64)
        self.assertFalse(set(new_ids) & set(self.manifest["excluded_observed_requested_ids"]))
        system = self.manifest["shared_prefix"][0]["content"]
        self.assertTrue(all(f"K00{i}:" in system for i in range(1, 9)))
        self.assertIn((self.folder / "sources/rules.md").read_text(encoding="utf8"), system)
        self.assertIn((self.folder / "sources/mechanics.json").read_text(encoding="utf8"), system)

    def test_draft_can_be_edited_before_freeze_and_existing_plan_is_not_overwritten(self):
        draft = self.root / "draft.json"
        new_folder = self.root / "edited"
        result = queue.make_plan(new_folder, draft_output=draft)
        self.assertFalse(result["frozen"])
        self.assertFalse(new_folder.exists())
        spec = json.loads(draft.read_text(encoding="utf8"))
        spec["tasks"][-1]["prompt"] += " 人工追加：费用不可以重复减。"
        queue.dump(draft, spec)
        queue.make_plan(new_folder, spec_path=draft)
        frozen, _ = queue.verify_plan(new_folder)
        self.assertIn("人工追加", frozen["tasks"][-1]["prompt"])
        with self.assertRaises(ValueError):
            queue.make_plan(new_folder, spec_path=draft)

    def test_budget_resume_warm_first_and_independent_parallel_clients(self):
        first = self.run_offline(workers=4, max_api_calls=6)
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(self.calls[0][0], "inventory_000")
        self.assertFalse(first["all_tasks_completed_and_structurally_valid"])
        # Warm client lives on the controller; pool worker clients cannot share it.
        self.assertNotIn(self.calls[0][2], {client for _, _, client in self.calls[1:]})
        self.assertGreaterEqual(len({thread for _, thread, _ in self.calls[1:]}), 2)
        final = self.run_offline(workers=4, max_api_calls=32)
        self.assertTrue(final["all_tasks_completed_and_structurally_valid"])
        self.assertEqual(len(self.calls), 12)
        self.assertFalse(final["semantic_approval"])
        self.assertEqual(len(final["probe_observations"]["20"]), 8)
        self.run_offline(max_api_calls=32)
        self.assertEqual(len(self.calls), 12)
        record = json.loads((self.folder / "inventory_000.json").read_text(encoding="utf8"))
        self.assertEqual(record["raw_usage"]["prompt_tokens_details"]["cached_tokens"], 1024)
        self.assertEqual(record["cache_metrics"]["cached_tokens"], 1024)
        self.assertTrue(record["semantic_review_required"])

    def test_failure_redaction_and_ambiguous_started_task_never_automatically_retry(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = queue.run(self.folder, max_api_calls=1, client_factory=self.factory("inventory_000"))
        self.assertFalse(result["tasks"][0]["ok"])
        raw = (self.folder / "inventory_000.json").read_text(encoding="utf8")
        self.assertNotIn("FAKE_SECRET", raw)
        self.assertIn("[REDACTED]", raw)
        self.run_offline(max_api_calls=1)
        self.assertEqual([call[0] for call in self.calls], ["inventory_000", "inventory_001"])
        path = self.folder / "inventory_002.json"
        queue.dump(path, {"status": "started_ambiguous_if_interrupted", "ok": False})
        self.run_offline(max_api_calls=1)
        self.assertEqual(self.calls[-1][0], "inventory_003")
        self.assertNotIn("inventory_002", [call[0] for call in self.calls])

    def test_frozen_mutation_or_missing_response_cannot_be_success(self):
        self.run_offline(max_api_calls=1)
        path = self.folder / "inventory_000.json"
        record = json.loads(path.read_text(encoding="utf8"))
        record["raw_response"]["choices"][0]["message"]["content"] = "{}"
        queue.dump(path, record)
        self.assertFalse(queue.merge(self.folder)["tasks"][0]["ok"])
        manifest = copy.deepcopy(self.manifest)
        manifest["tasks"][0]["prompt"] += " changed"
        queue.dump(self.folder / "manifest.json", manifest)
        with self.assertRaises(ValueError):
            queue.verify_plan(self.folder)

    def test_nonliteral_review_evidence_and_wrong_kind_are_rejected(self):
        task = self.manifest["tasks"][-1]
        finding = {"id": "proposal", "claim": "hypothesis only", "evidence": [{"source_id": "source:unified_value.py", "quote": "NOT IN THE SOURCE"}],
                   "reproduction": None, "information_boundary": "current", "accounting_boundary": "one delta", "unresolved": []}
        data = {"task_id": task["id"], "kind": "model_review", "annotations": [], "findings": [finding], "unresolved": []}
        self.assertTrue(queue.validate_output(data, task, queue.semantic_v6, {}))
        finding["evidence"][0]["quote"] = task["context"]["sources"][0]["text"].splitlines()[0]
        self.assertFalse(queue.validate_output(data, task, queue.semantic_v6, {}))
        data["kind"] = "counterexample"
        self.assertTrue(queue.validate_output(data, task, queue.semantic_v6, {}))

    def test_observed_exclusion_uses_returned_requested_ids_not_future_manifest(self):
        folder = self.root / "old-runs/example"
        folder.mkdir(parents=True)
        queue.dump(folder / "manifest.json", {"version": "semantic-v6-test", "requested_ids": [11, 12, 13],
                                              "tasks": [{"id": "batch_000"}, {"id": "batch_001"}]})
        queue.dump(folder / "batch_000.json", {"ok": True, "data": {"annotations": [{"card_id": 11}, {"card_id": 20}]}})
        observed, provenance = queue.observed_ids(folder.parent)
        self.assertEqual(observed, {11})
        self.assertEqual(provenance[0]["observed_requested_ids"], [11])

    def test_env_helper_and_frozen_source_hashes_are_recomputable(self):
        helper = self.root / "copied_api.py"
        helper.write_bytes((self.folder / "sources/api_helper.py").read_bytes())
        with patch.dict(os.environ, {"UNDERCARDS_API_HELPER": str(helper)}):
            self.assertEqual(queue.api_path(), helper.resolve())
            new_folder = self.root / "portable"
            queue.make_plan(new_folder)
        manifest, _ = queue.verify_plan(new_folder)
        for name, source in manifest["assets"].items():
            self.assertEqual(source["sha256"], queue.digest((new_folder / "sources" / name).read_bytes()))
        (new_folder / "sources/rules.md").write_text("changed", encoding="utf8")
        with self.assertRaises(ValueError):
            queue.verify_plan(new_folder)


if __name__ == "__main__":
    unittest.main()
