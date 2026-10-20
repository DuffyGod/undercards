"""New joint-model counterexamples; does not rerun earlier experiment suites."""
import unittest
from dataclasses import replace
from model import *

class JointTests(unittest.TestCase):
    def test_decks_and_refuse_token(self):
        for key,d in COMPOSITIONS.items():validate_deck(d,'KINDNESS')
        with self.assertRaises(ValueError):validate_deck((842,)*25,'KINDNESS')
        with self.assertRaises(ValueError):validate_deck(COMPOSITIONS['middle_heal'],'INTEGRITY')

    def test_knight_active_only_and_no_resurrection(self):
        kk=Unit(0,17,5,9,9,True);small=Unit(1,2,3,5,5,True)
        result,event=attack(Board((kk,),(small,),30,30),0,1,Config())
        self.assertEqual(result.own[0].h,9);self.assertEqual(result.foe,())
        result,event=attack(Board((small,),(kk,),30,30),1,0,Config())
        self.assertEqual(result.foe[0].h,6)
        result,event=attack(Board((replace(kk,h=3),),(small,),30,30),0,1,Config())
        self.assertEqual(result.own,());self.assertEqual(result.foe,())
        target=Unit(1,196,0,2,2)
        for ruling,expected in [('packet',6),('hp_loss',3)]:
            result,_=attack(Board((replace(kk,h=1),),(target,),30,30),0,1,Config(knight_damage=ruling))
            self.assertEqual(result.own[0].h,expected)

    def test_haste_armor_and_dodge(self):
        plane=unit(Held(0,21));armor=unit(Held(1,175));dodge=unit(Held(2,377))
        with self.assertRaises(ValueError):attack(Board((plane,),(),30,30),0,None,Config())
        self.assertEqual(hurt(armor,1)[0].h,1)
        d,packet,actual=hurt(dodge,1);self.assertEqual((d.h,d.dodge,packet,actual),(2,0,0,0))
        self.assertEqual(hurt(d,1)[0].h,1)

    def test_hand_cap_bench_and_rod_delay(self):
        m=Match((MIDDLE,MIDDLE),('INTEGRITY','INTEGRITY'),('balanced','balanced'),4)
        p=m.players[0];p.hand=[Held(100,243)]+[Held(i,2) for i in range(6)];p.cash=5
        m.deploy(0,100)
        self.assertEqual(len(p.hand),7);self.assertEqual(m.stats[0]['burned'],0)
        p.hand=[Held(100,225)]+[Held(i,2) for i in range(6)];p.cash=3
        before=m.stats[0]['draws'];m.deploy(0,100)
        self.assertEqual(m.stats[0]['draws'],before)
        m.rod_end(0);self.assertEqual(len(p.hand),7)
        m.rod_end(0);self.assertEqual(m.stats[0]['burned'],1)

    def test_kindness_hp_cap_and_only_rightmost_grows(self):
        m=Match((MIDDLE,MIDDLE),('KINDNESS','INTEGRITY'),('balanced','balanced'),0)
        p=m.players[0];p.hp=29;p.field=(Unit(0,2,2,3,3),Unit(1,15,6,5,5))
        m.turn=3;m.soul_end(0)
        self.assertEqual(p.hp,30);self.assertEqual([u.h for u in p.field],[3,6])
        p.field=(replace(p.field[0],h=1),p.field[1]);m.soul_end(0)
        self.assertEqual([u.h for u in p.field],[2,6]);self.assertEqual(p.field[-1].max_h,6)

    def test_causal_policies_do_not_receive_hidden_world(self):
        a=Match((MIDDLE,MIDDLE),('INTEGRITY','KINDNESS'),('balanced','balanced'),2)
        b=Match((MIDDLE,MIDDLE),('INTEGRITY','KINDNESS'),('balanced','balanced'),3)
        b.players[0].hand=list(a.players[0].hand);b.players[0].cash=a.players[0].cash
        # Deck orders and enemy hands still differ, while own view is identical.
        self.assertNotEqual(a.players[0].deck,b.players[0].deck)
        self.assertNotEqual(a.players[1].hand,b.players[1].hand)
        self.assertEqual(a.view(0),b.view(0))
        for policy in POLICIES:
            self.assertEqual(choose_deployment(a.view(0),policy),choose_deployment(b.view(0),policy))
            self.assertEqual(choose_combat(a.view(0),policy,a.config),choose_combat(b.view(0),policy,b.config))

    def test_death_stops_before_draw_or_heal(self):
        m=Match((MIDDLE,MIDDLE),('KINDNESS','KINDNESS'),('pressure','pressure'),2)
        m.players[0].field=(Unit(100,15,6,5,5,True),);m.players[1].hp=1
        before=m.stats[1]['draws'];m.apply_attack(0,100,None)
        self.assertFalse(m.alive());self.assertEqual(m.stats[1]['draws'],before)

    def test_whole_match_resource_and_health_conservation(self):
        for seed in range(4):
            m=Match((COMPOSITIONS['small_draw'],COMPOSITIONS['heavy']),('KINDNESS','KINDNESS'),('pressure','balanced'),seed)
            r=m.run()['players']
            for side,p in enumerate(m.players):
                s=r[side];e=r[1-side]
                self.assertEqual(s['draws']+len(p.deck),25)
                self.assertEqual(s['played']+s['burned']+s['hand'],s['draws'])
                self.assertEqual(s['hp'],30+s['healed']-e['damage']-s['fatigue_damage'])
                self.assertLessEqual(len(p.field),4);self.assertLessEqual(len(p.hand),7)
                self.assertGreaterEqual(p.cash,0)

if __name__=='__main__':unittest.main()
