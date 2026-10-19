import unittest
from dataclasses import replace

from response_window import frontier_after_reply,replies,compare_reply
from statistical_value import Unit
from slot_value import SlotSolver
from frontier import value


class SimpleScale:
    def value(self,a,h):return a+h if h>0 else 0


def card(cid,cost,a,h):
    return dict(id=cid,cost=cost,attack=a,health=h,effect_readable='',card_type='monster')


class ResponseWindowTests(unittest.TestCase):
    def setUp(self):
        cards={'2':card(2,2,2,3),'4':card(4,2,3,2),
               '9':card(9,3,3,1),'187':card(187,3,2,6),
               '13':card(13,4,3,5),'20':card(20,4,4,4), '168':card(168,6,5,5)}
        self.solver=SlotSolver(cards,SimpleScale(),.25)

    def test_haste_can_remove_the_only_lethal_ready_attacker(self):
        a=frontier_after_reply(self.solver,9,(2,4),((4,2),),3,4,3)
        b=frontier_after_reply(self.solver,187,(2,4),((4,2),),3,4,3)
        r=compare_reply(a,b)
        self.assertTrue(r['left_feasible']);self.assertFalse(r['right_feasible'])
        self.assertIsNone(r['numeric_difference'])
        self.assertTrue(a['enabled_survival_when_background_cannot'])

    def test_soft_body_value_cannot_compensate_for_a_lethal_face_attack(self):
        a=frontier_after_reply(self.solver,13,(2,4),((4,2),),4,4,3)
        b=frontier_after_reply(self.solver,20,(2,4),((4,2),),4,4,3)
        self.assertFalse(a['guarantee_feasible'])
        self.assertTrue(b['guarantee_feasible'])
        # Woshua reduces4ATK to3, still lethal at3HP; at4HP it is feasible.
        higher=frontier_after_reply(self.solver,13,(2,4),((4,2),),4,4,4)
        self.assertTrue(higher['guarantee_feasible'])

    def test_dodge_consumes_one_packet_and_retaliation_is_simultaneous(self):
        own=(Unit(5,5,5,5,5,dodge=1),)
        branches=replies(own,((5,5),),15)
        attack=next(r for r in branches if r['action']=='attack_body_0')
        self.assertEqual((attack['own'][0].h,attack['own'][0].dodge),(5,0))
        self.assertEqual(attack['enemy'],())
        plain=replies((replace(own[0],dodge=0),),((5,5),),15)
        trade=next(r for r in plain if r['action']=='attack_body_0')
        self.assertEqual(trade['own'],());self.assertEqual(trade['enemy'],())

    def test_dodge_does_not_protect_hero_when_enemy_can_choose_face(self):
        own=(Unit(5,5,5,5,5,dodge=1),)
        self.assertTrue(any(r['own_hp']==0 for r in replies(own,((5,8),),5)))

    def test_enemy_can_decline_and_cannot_attack_with_zero_atk(self):
        self.assertEqual([r['action'] for r in replies((),((0,5),),15)],['decline'])

    def test_more_than_one_attacker_or_unclosed_trigger_is_rejected(self):
        with self.assertRaises(ValueError):replies((),((2,3),(2,3)),15)
        with self.assertRaises(ValueError):
            frontier_after_reply(self.solver,530,(2,4),((2,3),),6,2)

    def test_opponent_choice_can_make_dodge_increment_zero_or_positive(self):
        def result(enemy,removed):
            return frontier_after_reply(self.solver,168,(),(enemy,),6,4,15,
                                        remove_focal_defense=removed)
        protected=result((5,5),False);plain=result((5,5),True)
        self.assertAlmostEqual(value(protected['curve'],0),8.75)
        self.assertAlmostEqual(value(plain['curve'],0),8.75)
        protected=result((5,8),False);plain=result((5,8),True)
        self.assertAlmostEqual(value(protected['curve'],0)-value(plain['curve'],0),3.75)

    def test_nonfinite_cash_cannot_bypass_the_payment_filter(self):
        for cash in (float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):
                frontier_after_reply(self.solver,168,(),((5,5),),cash,4)

    def test_occupied_slots_cannot_be_discarded_before_an_enemy_response(self):
        with self.assertRaises(ValueError):
            frontier_after_reply(self.solver,168,(),((5,5),),6,1)


if __name__=='__main__':unittest.main()
