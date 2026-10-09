import copy
import json
from pathlib import Path
import tempfile
import unittest

import batch_annotate as b


def row(cid=20):
    return {'card_id': cid, 'printed_effect': 'Magic: Deal DMG 2.',
            'modules': [{'kind': 'damage', 'trigger': 'magic', 'target': 'other',
                         'amount': 2, 'count': 1, 'card_ref': None, 'condition': '',
                         'evidence': 'Magic: Deal DMG 2.', 'amount_basis': 'fixed',
                         'stat': 'none', 'repeat_rule': 'none', 'choice_group': None}],
            'conditions': [], 'condition_codes': [], 'timing': 'immediate',
            'silence_exposure': 'none', 'unresolved': [], 'notes': ''}


class AnnotationContracts(unittest.TestCase):
    def setUp(self):
        self.cards = {20: {'effect_readable': 'Magic: Deal DMG 2.'}, 15: {'effect_readable': ''}}

    def check(self, r):
        return b.validate({'annotations': [r]}, [20], self.cards)

    def test_literal_reference_not_paraphrase(self):
        self.assertFalse(self.check(row()))
        bad = row()
        bad['modules'][0]['evidence'] = 'Magic: Deal 2 DMG.'
        self.assertTrue(self.check(bad))

    def test_no_numeric_grade_or_fabricated_blank_effect(self):
        bad = row()
        bad['score'] = 9
        self.assertTrue(self.check(bad))
        bad = row(15)
        bad['printed_effect'] = ''
        self.assertTrue(b.validate({'annotations': [bad]}, [15], self.cards))

    def test_invalid_or_duplicate_ids_fail_without_crash(self):
        for value in ({}, [], True, '20', None):
            bad = row()
            bad['card_id'] = value
            self.assertTrue(self.check(bad))
        self.assertTrue(b.validate({'annotations': [row(), row()]}, [20], self.cards))

    def test_unknown_reference_nonfinite_and_bool_numbers(self):
        for field, value in [('card_ref', 99999), ('amount', float('nan')), ('count', True)]:
            bad = row()
            bad['modules'][0][field] = value
            self.assertTrue(self.check(bad))

    def test_normal_kill_is_not_bullseye(self):
        bad = row()
        bad['condition_codes'] = ['exact_kill']
        self.assertTrue(self.check(bad))

    def test_condition_error_not_misreported_as_evidence(self):
        bad = row()
        bad['modules'][0]['condition'] = None
        errors = self.check(bad)
        self.assertTrue(any('condition must be' in e for e in errors))
        self.assertFalse(any('evidence' in e for e in errors))

    def test_signature_tracks_formula_stat_instances_and_rule_unknowns(self):
        initial = b.signature(row())
        for field, value in [('amount_basis', 'other_monster_count'), ('stat', 'HP'),
                             ('count', 2), ('repeat_rule', 'on_kill')]:
            bad = row()
            bad['modules'][0][field] = value
            self.assertNotEqual(b.signature(bad), initial)
        bad = row()
        bad['unresolved'] = ['Different real rule question']
        self.assertNotEqual(b.signature(bad), initial)
        prose = row()
        prose['notes'] = 'Same typed semantics, different phrasing'
        self.assertEqual(b.signature(prose), initial)

    def test_task_provenance_and_missing_tasks_are_quarantined(self):
        task = {'id': 'x', 'context': {'cards': [{'id': 20}]}}
        manifest = {'version': b.VERSION, 'tasks': [task], 'requested_ids': [20],
                    'probe_ids': [20], 'snapshot_sha256': 'not-used'}
        with tempfile.TemporaryDirectory(dir=b.HERE) as temp:
            path = Path(temp)
            status = b.merge(path, manifest, self.cards)
            self.assertFalse(status['all_batches_consistent'])
            b.dump(path / 'x.json', {'ok': True, 'task_sha256': 'wrong',
                                     'data': {'annotations': [row()]}})
            status = b.merge(path, manifest, self.cards)
            self.assertEqual(status['accepted_count'], 0)
            self.assertIn('provenance', str(status['invalid_tasks']))
            self.assertFalse(json.loads((path / 'annotations.json').read_text())['consistency_passed'])


if __name__ == '__main__':
    unittest.main()
