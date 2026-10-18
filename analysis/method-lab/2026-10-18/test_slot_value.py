"""Independent small arithmetic checks of the finite payment comparator."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from slot_value import Plan, SlotSolver, compare_slot


class SumScale:
    def value(self, attack, health):
        return attack + health if health > 0 else 0.


class AttackScale:
    def value(self, attack, health):
        return attack if health > 0 else 0.


class SlotArithmetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((Path(__file__).parent / "statistical_inputs.json").read_text(encoding="utf-8"))["cards"]

    def solver(self, scale=None, updates=None):
        cards = deepcopy(self.source)
        for cid, changes in (updates or {}).items():
            cards[str(cid)].update(changes)
        return SlotSolver(cards, scale or SumScale())

    def test_budget_competition_not_sum_of_independent_best(self):
        solver = self.solver(AttackScale(), {15: dict(cost=6, attack=7),
                                            4: dict(cost=4, attack=6), 2: dict(cost=2, attack=2)})
        result = compare_slot(solver, 15, 2, (4,), (), 6, 2, 0.)
        self.assertEqual(result["candidate_value"], 7.)
        self.assertEqual(result["reference_value"], 8.)
        self.assertEqual(result["slot_delta"], -1.)

    def test_one_slot_excludes_individually_useful_candidate(self):
        solver = self.solver(AttackScale(), {15: dict(cost=2, attack=4),
                                            4: dict(cost=4, attack=6), 2: dict(cost=2, attack=2)})
        result = compare_slot(solver, 15, 2, (4,), (), 6, 1, 0.)
        self.assertFalse(result["candidate_used"])
        self.assertEqual(result["slot_delta"], 0.)
        self.assertEqual(result["plus_slot_delta"], 2.)

    def test_hand_growth_counts_physical_prefix_only(self):
        solver = self.solver()
        before = solver.fixed(Plan((), (0,), True, "deploy:hold_attack"),
                              49, (2, 4), (), 10, 4, 0.)
        after = solver.fixed(Plan((0,), (), True, "deploy:hold_attack"),
                             49, (2, 4), (), 10, 4, 0.)
        self.assertEqual(before, 5 + 8)  # Froggit2/3 and Glyde4/4.
        self.assertEqual(after, 5 + 6)   # Same Froggit, Glyde3/3.

    def test_archer_explicit_child_stats_and_capacity_failure(self):
        solver = self.solver()
        plan = Plan((), (), True, "magic_target_0:hold_attack")
        small = solver.fixed(plan, 984, (2, 4), ((1, 2),), 6, 1, 0.)
        large = solver.fixed(plan, 984, (2, 4), ((1, 2),), 6, 2, 0.)
        self.assertEqual(small, 7 + 3)  # Archer3/4 and removed enemy1/2.
        self.assertEqual(large, small + 5)  # Explicit Clover2/3, not1/1.
        quote = next(q for q in solver.quotes(984, (2, 4), ((1, 2),), 1) if q.plan == plan)
        self.assertEqual(quote.summon_failure_weight, 1.)
        overkill = solver.fixed(plan, 984, (2, 4), ((1, 1),), 6, 2, 0.)
        self.assertEqual(overkill, 7 + 2)

    def test_b_death_child_replaces_body_in_same_slot(self):
        solver = self.solver()
        plan = Plan((), (), True, "deploy:attack_0")
        value = solver.fixed(plan, 469, (), ((4, 3),), 5, 1, 0.)
        self.assertEqual(value, 7 + 7)  # Enemy removed and O4/3; no B body.

    def test_random_chain_integrates_after_fixed_initial_target(self):
        solver = self.solver()
        plan = Plan((), (), True, "deploy:attack_0")
        enemy = ((4, 4), (2, 1), (3, 2))
        value = solver.fixed(plan, 530, (), enemy, 6, 1, 0.)
        # Kill4/4; Dodge preserves4/4. Equal chain branches yield20 or17.
        self.assertEqual(value, 18.5)
        self.assertLess(value, 20.)

    def test_true_identity_and_no_forced_payment(self):
        solver = self.solver()
        same = compare_slot(solver, 2, 2, (4, 187), ((6, 7),), 6, 2, .5)
        self.assertEqual(same["slot_delta"], 0.)
        cannot = compare_slot(solver, 49, 2, (), (), 0, 1, 1.)
        self.assertEqual(cannot["candidate_paid"], 0.)
        self.assertTrue(cannot["candidate_no_plays"])

    def test_cash_retention_not_deducted_twice(self):
        solver = self.solver(AttackScale(), {15: dict(cost=6, attack=7), 2: dict(cost=2, attack=2)})
        result = compare_slot(solver, 15, 2, (), (), 6, 1, 1.)
        self.assertEqual(result["candidate_value"], 7.)
        self.assertEqual(result["reference_value"], 6.)  # Playing ref and holding both6.
        self.assertEqual(result["slot_delta"], 1.)


if __name__ == "__main__":
    unittest.main()
