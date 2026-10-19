import copy
import unittest

from response_window import compare_reply_set
from compare_cards import compare_saved_reply


def result(feasible=True):
    return dict(guarantee_feasible=feasible,condition=dict(own_hp=3,minimum_own_hp=1,cash=4,
        background_ids=[2,4],enemy_before=[[4,2]],face_price=.25,body_face_share=.2,body_threshold=.4),
        curve=[dict(low=0,high=1,intercept=2,slope=0)] if feasible else None,
        background_curve=None,enabled_survival_when_background_cannot=feasible)


class ReplyContractTests(unittest.TestCase):
    def test_an_infeasible_shared_goal_never_gets_a_numeric_fallback(self):
        s={'central':{'13':result(False),'20':result(True)}}
        r=compare_reply_set(s,13,20)
        self.assertIsNone(r['numeric_difference'])
        data={'probe':s};design=dict(candidate_ids=[13,20],cases={'probe':{}},names={'13':'Woshua','20':'Vulkin'})
        out=compare_saved_reply(data,design,[13,20],'probe')
        self.assertIsNone(out['cards'][1]['current_gain_over_feasible_background'])
        self.assertTrue(out['cards'][1]['enabled_survival_when_background_cannot'])

    def test_different_hp_goals_or_physical_states_cannot_be_compared(self):
        a=result();b=result();b['condition']['minimum_own_hp']=2
        with self.assertRaises(ValueError):compare_reply_set({'central':{'1':a,'2':b}},1,2)
        s={'central':{'1':result(),'2':result()},'corner':{'1':result(),'2':result()}}
        s['corner']['1']['condition']['cash']=5;s['corner']['2']['condition']['cash']=5
        with self.assertRaises(ValueError):compare_reply_set(s,1,2)

    def test_invalid_cash_price_is_rejected_even_when_survival_is_infeasible(self):
        for lam in (-.1,1.1,float('nan')):
            with self.assertRaises(ValueError):
                compare_reply_set({'central':{'1':result(False),'2':result(True)}},1,2,lam)


if __name__=='__main__':unittest.main()
