import unittest
from dataclasses import replace
from package_model import Body,Enemy,State,all_replies,kindness,justice,ledger,clip,score


class NewMechanismTests(unittest.TestCase):
    def test_income_and_integrity_sequence(self):
        self.assertEqual(ledger('first','KINDNESS',[0,0,0])['cash'],11)
        self.assertEqual(ledger('second','KINDNESS',[0,0,0])['cash'],13)
        self.assertEqual(ledger('second','JUSTICE',[1,0,0])['cash'],12)
        a=ledger('first','INTEGRITY',[2,0,4])
        b=ledger('first','INTEGRITY',[0,2,4])
        self.assertEqual((a['cash'],b['cash']),(6,7))
        self.assertEqual(a['history'][0]['end_bonus'],0)
        with self.assertRaises(ValueError):ledger('first','INTEGRITY',[3])

    def test_order_can_break_dodge_retention(self):
        ranger=Body(0,377,3,2,2,dodge=1)
        ends=all_replies(State((ranger,),(Enemy(0,1,1),Enemy(1,2,4)),30))
        # Both different physical witnesses must exist, not a fixed foe order.
        self.assertTrue(any(not s.own and [(e.a,e.h) for e in s.enemy]==[(2,1)] for s,p in ends))
        self.assertTrue(any(s.own and s.own[0].h==1 and [(e.a,e.h) for e in s.enemy]==[(2,1)] for s,p in ends))
        self.assertEqual(min(len(s.own) for s,p in ends),0)

    def test_taunt_and_kindness_position(self):
        guard=Body(0,38,7,10,10);dummy=Body(1,1,0,4,4,taunt=True)
        foe=(Enemy(0,4,1),)
        left,hp=kindness((guard,dummy),30,4)
        right,_=kindness((dummy,guard),30,4)
        self.assertEqual(min(len(s.own) for s,p in all_replies(State(left,foe,hp))),2)
        self.assertEqual(min(len(s.own) for s,p in all_replies(State(right,foe,hp))),1)
        self.assertEqual(min(s.hp for s,p in all_replies(State(left,foe,hp))),30)

    def test_kindness_heals_all_injured_without_bonus(self):
        a=Body(0,4,3,1,2);b=Body(1,4,3,1,2)
        team,hp=kindness((a,b),29,3)
        self.assertEqual([(u.h,u.max_h) for u in team],[(2,2),(2,2)])
        self.assertEqual(hp,30)

    def test_justice_tie_is_not_invented(self):
        with self.assertRaises(ValueError):justice((Enemy(0,6,1),Enemy(1,1,1)))
        self.assertEqual(len(justice((Enemy(0,4,1),Enemy(1,4,1)))),1)
        self.assertEqual(justice((Enemy(0,6,1),Enemy(1,1,2))),(Enemy(1,1,2),))

    def test_armor_per_instance_and_terminal_stop(self):
        charles=Body(0,175,3,1,1,armor=True)
        states=all_replies(State((charles,),tuple(Enemy(i,1,4) for i in range(3)),30))
        self.assertTrue(all(s.own and s.own[0].h==1 for s,p in states))
        lethal=all_replies(State((),(Enemy(0,10,2),Enemy(1,10,2)),5))
        self.assertTrue(all(len(p)<=1 for s,p in lethal))

    def test_price_region_and_unknown_hand_resource(self):
        # Split has gross +2, costs +1G and one extra card.
        p=clip([[0,0],[1,0],[1,3],[0,3]],2,-1,-1)
        self.assertTrue(all(x+y<=2+1e-9 for x,y in p))
        a=dict(feasible=True,intercept=7,net_paid=9,cards_used=1)
        b=dict(feasible=True,intercept=9,net_paid=10,cards_used=2)
        self.assertAlmostEqual(score(b,.5,1.5)-score(a,.5,1.5),0)
        self.assertIsNone(score(dict(feasible=False),.5,0))


if __name__=='__main__':unittest.main()
