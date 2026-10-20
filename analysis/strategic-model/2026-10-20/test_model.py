"""New abstraction/causality checks; do not rerun historical card experiments."""
import unittest
from dataclasses import fields,replace
from model import *


class ModelChecks(unittest.TestCase):
    def test_first_cash_seat_and_draw(self):
        for seat,cash in ((0,2),(1,3)):
            g=Game('wide',1,Config(seat=seat),(ROW_POLICIES[0],COL_POLICIES[0]))
            g.players[0].hand=[];g.players[0].deck=[]
            g.act_turn(0)
            self.assertEqual(g.players[0].cash,cash)
            self.assertEqual(g.players[0].hp,29)

    def test_same_information_decision_independent_of_hidden_hands(self):
        g=Game('wide',9,Config(),(ROW_POLICIES[0],COL_POLICIES[0]))
        original=g.view(0);choice=decide(original,ROW_POLICIES[0])
        g.players[1].hand=[Card(25,'response')]*len(g.players[1].hand)
        g.players[0].deck.reverse();g.players[1].deck.reverse()
        self.assertEqual(g.view(0),original)
        self.assertEqual(decide(g.view(0),ROW_POLICIES[0]),choice)
        self.assertFalse({'seed','enemy_hand','deck','game'} & {x.name for x in fields(View)})

    def test_response_requires_both_hand_and_cash(self):
        g=Game('wide',1,Config(),(ROW_POLICIES[0],COL_POLICIES[0]))
        a,b=g.players;a.hand=[Card(0,'response')];a.cash=4
        b.units=[Unit(4,'small',2,2,2)]
        self.assertNotEqual(decide(g.view(0),COL_POLICIES[0])[0],'play')
        a.cash=5
        self.assertEqual(decide(g.view(0),COL_POLICIES[0]),('play',0,-1))
        a.hand=[]
        self.assertEqual(decide(g.view(0),COL_POLICIES[0])[0],'end')

    def test_holding_threshold_is_an_actual_choice(self):
        g=Game('wide',1,Config(),(ROW_POLICIES[0],COL_POLICIES[0]))
        a,b=g.players;a.hand=[Card(0,'response')];a.cash=5
        b.units=[Unit(4,'small',2,2,2),Unit(5,'small',2,2,2)]
        self.assertEqual(decide(g.view(0),COL_POLICIES[1])[0],'play')
        self.assertEqual(decide(g.view(0),COL_POLICIES[2])[0],'end')

    def test_mutual_trade_checks_actual_remaining_hp(self):
        g=Game('wide',1,Config(),(ROW_POLICIES[0],COL_POLICIES[0]))
        a,b=g.players;a.hand=[];a.units=[Unit(1,'anchor',5,2,7,True)]
        b.units=[Unit(2,'small',2,2,2)]
        self.assertEqual(decide(g.view(0),ROW_POLICIES[0]),('attack',1,2))
        g.attack(0,1,2)
        self.assertEqual(a.units,[]);self.assertEqual(b.units,[])

    def test_forecast_income_uses_same_late_integrity_rule(self):
        self.assertEqual(income(11,0,'INTEGRITY'),11)
        self.assertEqual(income(11,1,'KINDNESS'),10)

    def test_setup_packet_then_ready_attack_is_not_strategically_immune(self):
        g=Game('wide',1,Config(),(ROW_POLICIES[0],COL_POLICIES[0]))
        a,b=g.players;a.hand=[Card(0,'response')];a.cash=5
        a.units=[Unit(1,'anchor',5,7,7,True)];b.units=[Unit(2,'anchor',5,7,7)]
        self.assertEqual(decide(g.view(0),COL_POLICIES[0])[0],'attack')
        self.assertEqual(decide(g.view(0),COL_POLICIES[4]),('play',0,-1))
        g.play(0,0)
        self.assertEqual(decide(g.view(0),COL_POLICIES[4]),('attack',1,2))
        g.attack(0,1,2)
        self.assertEqual(b.units,[]);self.assertEqual(a.units[0].h,2)

    def test_zero_response_closes_guard_exactly(self):
        cfg=Config(responses_enabled=False)
        for seed in range(5):
            a=play('wide',seed,cfg,ROW_POLICIES[0],COL_POLICIES[1],trace=True)
            b=play('wide',seed,cfg,ROW_POLICIES[1],COL_POLICIES[1],trace=True)
            self.assertEqual(a['trace'],b['trace'])

    def test_impossible_response_cost_closes_guard_exactly(self):
        cfg=Config(response_cost=1000)
        for seed in range(5):
            a=play('wide',seed,cfg,ROW_POLICIES[0],COL_POLICIES[1],trace=True)
            b=play('wide',seed,cfg,ROW_POLICIES[1],COL_POLICIES[1],trace=True)
            self.assertEqual(a['trace'],b['trace'])

    def test_penalty_no_dead_body_or_unpaid_resource_reward(self):
        g=Game('wide',1,Config(),(ROW_POLICIES[0],COL_POLICIES[0]))
        a,b=g.players;a.turn=3;a.cash=6;a.hand=[Card(0,'response')]
        b.turn=3;b.units=[Unit(2,'small',2,2,2),Unit(3,'anchor',5,7,7)]
        g.play(0,0)
        self.assertEqual(a.cash,1);self.assertEqual(a.total_spent,5)
        self.assertEqual([(u.kind,u.h) for u in b.units],[('anchor',4)])
        self.assertEqual((b.first_effective_penalty_turn,b.first_penalty_killed,b.first_penalty_wiped),(3,1,False))

    def test_summoning_sickness_then_actual_recovery(self):
        g=Game('wide',1,Config(),(ROW_POLICIES[0],COL_POLICIES[0]))
        a,b=g.players;a.turn=4;a.first_effective_penalty_turn=3;a.cash=2;a.hand=[Card(0,'small')]
        g.play(0,0)
        self.assertFalse(a.units[0].ready)
        with self.assertRaises(ValueError):g.attack(0,0,-1)
        self.assertEqual(a.rebuilt_deploy_turn,4)
        a.turn=5;a.units=[replace(a.units[0],ready=True)];g.attack(0,0,-1)
        self.assertEqual(a.rebuilt_attack_turn,5)

    def test_cash_inventory_and_outcome_accounting_on_new_trajectories(self):
        for structure in ('wide','anchor','refill','recovery'):
            for i in range(3):
                r=play(structure,700+i,Config(),ROW_POLICIES[i],COL_POLICIES[i])
                self.assertEqual(r['a_cash'],1+r['a_income']+r['a_bonus_gold']-r['a_total_spent'])
                self.assertEqual(r['a_deck']+r['a_hand']+r['a_played']+r['a_burned'],25)
                self.assertEqual(sum(r[k] for k in ('won','lost','unfinished')),1)
                self.assertAlmostEqual(r['deadline_life_margin'],(max(0,r['a_hp'])-max(0,r['b_hp']))/30)


if __name__=='__main__':unittest.main(verbosity=2)
