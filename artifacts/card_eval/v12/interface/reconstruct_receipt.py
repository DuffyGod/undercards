"""Preserve the failed first verifier's outputs without rerunning any game.

The first runner raised before writing verification.json. This script only
checks saved CLI outputs and NPZ fingerprints; it cannot recover the temporary
module-origin pathname. Import isolation assertion had passed in that runner.
"""
from pathlib import Path
import gzip
import hashlib
import json
from card_eval.network import Network

folder = Path(__file__).resolve().parent
read = lambda name: json.loads((folder / name).read_text())
actor = read('actor/result.json'); fitted = read('fitted-value/result.json')
blocked = read('blocked/result.json'); unfitted = read('unfitted-value/result.json'); unknown = read('unknown.json')
net, _ = Network.load(folder.parent / 'robust-selected.npz')
own, _ = Network.load(folder.parent / 'primary-value.npz')
assert actor['frozen_policy'] == net.fingerprint and fitted['base_model'] == own.fingerprint
assert net.actor_fingerprint == own.actor_fingerprint
assert actor['games'] == 8 and actor['unresolved'] == 0
assert blocked['status'] == 'unqualified_policy' and blocked['scores'] is None
assert unfitted['status'] == 'unsupported_policy_configuration' and unfitted['scores'] is None
assert unknown['status'] == 'unsupported' and unknown['score'] is None
with gzip.open(folder / 'fitted-value/games.jsonl.gz', 'rt') as stream:
    failed = [json.loads(line) for line in stream if json.loads(line).get('unfinished')]
assert len(failed) == fitted['unresolved'] == 3
receipt = dict(status='failed_fitted_value_contract', source_commit='7484cb833c0de34ff5c4bf4b275a2a6b60eca91d',
    reconstructed_from_saved_outputs=True, no_game_replays=True, initial_exception='ValueError: Fitted value planner standalone contract failed',
    isolation='Runner imported a temporary standalone source copy, asserted its module origin outside checkout, then executed independent NPZ. Exact temporary pathname was not retained when failure raised.',
    actor_contract=dict(slots=8, unresolved=0, strict_budget_passed=True, frozen_policy=net.fingerprint),
    fitted_value_contract=dict(slots=8, unresolved=3, strict_budget_passed=False, base_model=own.fingerprint,
        planner_fingerprint=fitted['frozen_policy'], failures=failed),
    checkpoint_sha256={name: hashlib.sha256((folder.parent / name).read_bytes()).hexdigest()
                       for name in ('robust-selected.npz', 'primary-value.npz')},
    decision_seconds=.25, quality_gate=True, unfitted_value_rejected=True, unknown_not_zero=True,
    default_model_replaced=False, limitation='Actor interface passed; optional value planning failed strict wall budget. No wider-budget retry or policy-quality claim.')
(folder / 'verification.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
