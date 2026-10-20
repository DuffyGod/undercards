"""Hand-calculated public-action counterexamples, not old experiment replays."""
import copy
from dataclasses import replace
import unittest
from unittest.mock import patch

from model import (Board, Config, Held, Match, MIDDLE, POLICIES, Unit,
                   View, attack, board_score, choose_combat)
from tactical import _combat_endpoint, _project_plane, precombat_choice


def public_view(board, hand=(Held(100, 21),), cash=7, slots=4):
    return View(board=board, hand=hand, cash=cash, turn=4, seat=0,
                hand_cap=7, slots=slots, soul='INTEGRITY', healing=True,
                knight_damage='packet', deck_count=10, fatigue=0)


class PublicTacticsTests(unittest.TestCase):
    def test_tiny_plane_visible_lethal_and_no_haste_face(self):
        # Plane: Gyftrot 1 -> 0, hero 4 -> 1. Tiny then attacks face 1 -> 0.
        # Combat first instead sacrifices Tiny to 6/1 Taunt, leaving no face hit.
        tiny = Unit(1, 196, 1, 1, 1, ready=True)
        taunt = Unit(2, 44, 6, 1, 8, taunt=True)
        view = public_view(Board((tiny,), (taunt,), 30, 4))
        for policy in POLICIES:
            with self.subTest(policy=policy):
                plan, _ = choose_combat(view, policy, Config())
                self.assertEqual(plan, ((1, 2),))
                sacrificed, _ = attack(view.board, 1, 2, Config())
                self.assertEqual((sacrificed.own, sacrificed.foe), ((), ()))
                self.assertEqual(precombat_choice(view, policy, Config()), 100)
                projected = _project_plane(view, view.hand[0])
                self.assertEqual(projected.board.foe, ())
                self.assertEqual(projected.board.foe_hp, 1)
                self.assertTrue(projected.board.own[-1].ready)
                self.assertFalse(projected.board.own[-1].face_allowed)
                lethal, _ = attack(projected.board, 1, None, Config())
                self.assertEqual(lethal.foe_hp, 0)

    def test_nonlethal_same_card_order_is_strictly_better(self):
        # At 30 enemy HP, old order ends at 27 without Tiny; new at 26 with Tiny.
        tiny = Unit(1, 196, 1, 1, 1, ready=True)
        taunt = Unit(2, 44, 6, 1, 8, taunt=True)
        view = public_view(Board((tiny,), (taunt,), 30, 30))
        for policy in POLICIES:
            with self.subTest(policy=policy):
                before = _combat_endpoint(view, policy, Config())
                after_old = _combat_endpoint(
                    _project_plane(before, view.hand[0]), policy, Config())
                after_new = _combat_endpoint(
                    _project_plane(view, view.hand[0]), policy, Config())
                self.assertEqual(after_old.board.foe_hp, 27)
                self.assertEqual(after_new.board.foe_hp, 26)
                self.assertEqual(len(after_old.board.own), 1)
                self.assertEqual(len(after_new.board.own), 2)
                self.assertGreater(board_score(after_new.board, policy),
                                   board_score(after_old.board, policy))
                self.assertEqual(precombat_choice(view, policy, Config()), 100)

    def test_nonlethal_does_not_choose_another_deployment(self):
        view = public_view(Board((Unit(1, 196, 1, 1, 1, True),),
                                 (Unit(2, 44, 6, 1, 8, taunt=True),), 30, 30))
        # A different greedy choice disables nonlethal order optimization.
        with patch('tactical.choose_deployment', return_value=999):
            self.assertIsNone(precombat_choice(view, 'balanced', Config()))

    def test_no_strict_improvement_no_preemption(self):
        view = public_view(Board((), (), 30, 30))
        self.assertIsNone(precombat_choice(view, 'balanced', Config()))

    def test_projection_handles_damage_prevention_by_hand_calculation(self):
        armor = Unit(1, 175, 3, 1, 1, armor=True)
        dodge = Unit(2, 377, 3, 2, 2, dodge=1)
        normal = Unit(3, 196, 1, 1, 1)
        view = public_view(Board((), (armor, dodge, normal), 30, 20))
        projected = _project_plane(view, view.hand[0])
        self.assertEqual([(u.uid, u.h, u.dodge) for u in projected.board.foe],
                         [(1, 1, 0), (2, 2, 0)])
        self.assertEqual((projected.board.foe_hp, projected.cash, projected.hand),
                         (17, 0, ()))
        self.assertEqual((projected.deck_count, projected.fatigue), (10, 0))

    def test_only_current_legal_planes_and_immutable_input(self):
        view = public_view(Board((), (), 30, 3))
        saved = copy.deepcopy(view)
        self.assertEqual(precombat_choice(view, 'balanced', Config()), 100)
        self.assertEqual(view, saved)
        self.assertIsNone(precombat_choice(replace(view, cash=6), 'balanced', Config()))
        full = replace(view, board=replace(view.board, own=tuple(
            Unit(i, 2, 2, 3, 3) for i in range(4))))
        self.assertIsNone(precombat_choice(full, 'balanced', Config()))
        no_plane = replace(view, hand=(Held(100, 243),))
        self.assertIsNone(precombat_choice(no_plane, 'balanced', Config()))
        self.assertIsNone(precombat_choice(replace(view, board=replace(view.board, hp=0)),
                                          'balanced', Config()))

    def test_hidden_world_changes_do_not_change_public_choice(self):
        a = Match((MIDDLE, MIDDLE), ('INTEGRITY', 'KINDNESS'),
                  ('balanced', 'balanced'), 2)
        b = Match((MIDDLE, MIDDLE), ('INTEGRITY', 'KINDNESS'),
                  ('balanced', 'balanced'), 3)
        for match in (a, b):
            match.turn = 4
            match.players[0].field = (Unit(10, 196, 1, 1, 1, True),)
            match.players[0].hand = [Held(100, 21)]
            match.players[0].cash = 7
            match.players[1].field = (Unit(11, 44, 6, 1, 8, taunt=True),)
            match.players[1].hp = 4
        self.assertNotEqual(a.players[0].deck, b.players[0].deck)
        self.assertNotEqual(a.players[1].hand, b.players[1].hand)
        self.assertEqual(a.view(0), b.view(0))
        saved_a, saved_b = copy.deepcopy(a.players), copy.deepcopy(b.players)
        for policy in POLICIES:
            self.assertEqual(precombat_choice(a.view(0), policy, a.config), 100)
            self.assertEqual(precombat_choice(b.view(0), policy, b.config), 100)
        self.assertEqual(a.players, saved_a)
        self.assertEqual(b.players, saved_b)


if __name__ == '__main__':
    unittest.main()
