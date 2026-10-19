import unittest
from response_window import frontier_after_reply,compare_reply_set,compare_reply
from slot_value import SlotSolver


class Scale:
    def value(self,a,h):return a+h if h>0 else 0


def card(i,c,a,h):return dict(id=i,cost=c,attack=a,health=h,card_type='monster',effect_readable='')


class StandingGoalTests(unittest.TestCase):
    def setUp(self):
        self.solver=SlotSolver({'43':card(43,6,5,5),'168':card(168,6,5,5),
            '9':card(9,3,3,1),'377':card(377,3,3,2),'187':card(187,3,2,6)},Scale(),.25)

    def test_dodge_can_enable_body_retention_when_plain_equal_stats_cannot(self):
        args=((),((5,5),),6,4,15)
        plain=frontier_after_reply(self.solver,43,*args,minimum_own_bodies=1)
        dodge=frontier_after_reply(self.solver,168,*args,minimum_own_bodies=1)
        removed=frontier_after_reply(self.solver,168,*args,minimum_own_bodies=1,remove_focal_defense=True)
        self.assertFalse(plain['guarantee_feasible']);self.assertTrue(dodge['guarantee_feasible'])
        self.assertFalse(removed['guarantee_feasible'])
        r=compare_reply_set({'s':{'a':dodge,'b':plain}},'a','b')
        self.assertEqual(r['status'],'shared_goal_feasibility_differs')
        self.assertIsNone(r['numeric_difference'])
        self.assertEqual(compare_reply(dodge,plain)['status'],'shared_goal_feasibility_differs')

    def test_immediate_clear_does_not_imply_leaving_a_body(self):
        args=((),((3,2),),3,4,15)
        charge=frontier_after_reply(self.solver,9,*args,minimum_own_bodies=1)
        dodge=frontier_after_reply(self.solver,377,*args,minimum_own_bodies=1)
        hp=frontier_after_reply(self.solver,187,*args,minimum_own_bodies=1)
        self.assertFalse(charge['guarantee_feasible'])
        self.assertTrue(dodge['guarantee_feasible']);self.assertTrue(hp['guarantee_feasible'])

    def test_board_goal_is_shared_and_not_convertible_to_a_scalar_loss(self):
        args=((),((5,5),),6,4,15)
        a=frontier_after_reply(self.solver,168,*args)
        b=frontier_after_reply(self.solver,168,*args,minimum_own_bodies=1)
        with self.assertRaises(ValueError):compare_reply_set({'s':{'a':a,'b':b}},'a','b')


if __name__=='__main__':unittest.main()
