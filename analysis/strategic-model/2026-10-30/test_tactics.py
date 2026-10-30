"""Discriminative new checks; no historical official runs are repeated."""
import unittest
from dataclasses import replace
from engine import *
from tactics import choose,frontier


class TacticsChecks(unittest.TestCase):
    def test_two_chips_clear_a_threat_old_policy_misses(self):
        g=BridgeGame('wide',910001,Config(),(ROWS[1],COLS[0]),bodies()['Froggit'])
        a,b=g.players;a.hp=5;b.hp=10;a.hand=[]
        a.units=[Unit(1,'small',2,2,2,True),Unit(2,'small',2,2,2,True)]
        b.units=[Unit(5,'anchor',5,4,7)]
        self.assertEqual(old_decide(g.view(0),Policy('old')),('attack',1,-1))
        for _ in range(2):
            action,uid,target=decision(g.view(0),ROWS[1],g.candidate)
            self.assertEqual((action,target),('attack',5));g.attack(0,uid,target)
        self.assertFalse(b.units)

    def test_joint_order_leaves_the_only_big_attack_available(self):
        own=((5,7,True),(2,2,True));enemy=((5,6),(2,2))
        leaf,score=choose(own,enemy,5,20)
        # Greedy big-into-small leaves a5ATK threat; chip + big clears it.
        self.assertEqual(leaf[1][0],0)
        self.assertLess(sum(e[0] for e,h in zip(enemy,leaf[1]) if h>0),5)
        self.assertEqual(score[0],2)

    def test_no_trade_can_overrule_current_legal_lethal(self):
        leaf,score=choose(((5,7,True),(2,2,True)),((8,4),),1,7)
        self.assertGreaterEqual(leaf[2],7);self.assertEqual(score[0],3)
        self.assertTrue(all(p[2]==-1 for p in leaf[-1]))

    def test_response_and_attack_can_combine_to_kill(self):
        leaf,_=choose(((5,7,True),),((5,7),),5,30,response_kind='sweep')
        self.assertTrue(leaf[3]);self.assertEqual(leaf[1],(0,))
        self.assertEqual(sum(p[0]=='response' for p in leaf[-1]),1)

    def test_sick_bodies_cannot_act_and_response_is_optional(self):
        leaf,_=choose(((5,7,False),),((2,2),),30,30)
        self.assertFalse(leaf[-1]);self.assertEqual(leaf[1],(2,))
        leaf,_=choose(((5,7,True),),((2,2),),30,30,response_kind='sweep')
        # Spending the response to retain a5ATK face hit is a legitimate
        # competing plan; a no-cast endpoint must still remain available.
        self.assertTrue(any(not x[3] for x in frontier(((5,7,True),),((2,2),),'sweep')))

    def test_candidate_payment_and_real_health_used(self):
        g=BridgeGame('wide',910002,Config(),(ROWS[1],COLS[0]),bodies()['Candy Dish'])
        a=g.players[0];a.hand=[Card(0,'candidate')];a.units=[];a.cash=2
        self.assertEqual(decision(g.view(0),ROWS[1],g.candidate)[0],'end')
        with self.assertRaises(ValueError):g.play(0,0)
        a.cash=3;g.play(0,0)
        self.assertEqual((a.cash,a.units[0].a,a.units[0].h,a.units[0].ready),(0,2,6,False))

    def test_entry_policy_can_save_for_a_held_body_without_future_draws(self):
        g=BridgeGame('wide',910005,Config(),(ROWS[-1],COLS[0]),bodies()['Aaron'])
        a,b=g.players;a.hand=[Card(0,'candidate'),Card(5,'small')];a.units=[];a.cash=4;a.turn=2
        b.units=[]
        self.assertEqual(decision(g.view(0),ROWS[-1],g.candidate),('end',-1,-1))
        self.assertEqual(decision(g.view(0),ROWS[2],g.candidate),('play',5,-1))
        a.cash=5
        self.assertEqual(decision(g.view(0),ROWS[-1],g.candidate),('play',0,-1))

    def test_swaps_preserve_entity_order_and_opponent(self):
        a=BridgeGame('wide',910003,Config(),(ROWS[1],COLS[0]),bodies()['Froggit'])
        b=BridgeGame('wide',910003,Config(),(ROWS[1],COLS[0]),bodies()['Aaron'])
        for p,q in zip(a.players,b.players):
            self.assertEqual(p.deck,q.deck);self.assertEqual(p.hand,q.hand)
        self.assertEqual(sum(h.kind=='candidate' for h in a.players[0].deck+a.players[0].hand),3)

    def test_no_hidden_information_enters_new_decision(self):
        g=BridgeGame('wide',910004,Config(),(ROWS[1],COLS[0]),bodies()['Rock Pet'])
        v=g.view(0);d=decision(v,ROWS[1],g.candidate)
        g.players[0].deck.reverse();g.players[1].deck.reverse()
        g.players[1].hand=[Card(99,'response')]
        self.assertEqual(g.view(0),v);self.assertEqual(decision(g.view(0),ROWS[1],g.candidate),d)

    def test_unchanged_role_and_greedy_matches_original_new_seed(self):
        # Compatibility on new probe seeds only, not a repeat of old data.
        for seat in (0,1):
            cfg=Config(rounds=5,seat=seat)
            a=BridgeGame('wide',910010+seat,cfg,(ROWS[0],COLS[0]),bodies()['role_2_2'],trace=True).run()
            b=Game('wide',910010+seat,cfg,(ROWS[0],COLS[0]),trace=True).run()
            for key in ('won','lost','unfinished','a_hp','b_hp','a_cash','a_spent','a_total_spent','a_played','a_burned','snapshots'):
                if key in a:self.assertEqual(a[key],b[key],key)
            def normalize(trace):
                def visit(item):
                    if isinstance(item,list):return [visit(x) for x in item]
                    if isinstance(item,dict):
                        return {k:('small' if k=='kind' and v=='candidate' else visit(v)) for k,v in item.items() if k!='body'}
                    return item
                return visit(trace)
            self.assertEqual(normalize(a['trace']),normalize(b['trace']))


if __name__=='__main__':unittest.main(verbosity=2)
