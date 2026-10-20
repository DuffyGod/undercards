import json,unittest
from pathlib import Path
from opening_sequence import (OpeningGraph,BodyScale,Game,Player,Unit,attack_endpoints)

ROOT=Path(__file__).resolve().parents[4]
CARDS={str(c['id']):c for c in json.loads((ROOT/'skills/undercards/references/snapshot.json').read_text())['cards']}
INPUT=json.loads((ROOT/'analysis/method-lab/2026-10-18/statistical_inputs.json').read_text())
SCALE=BodyScale(INPUT['reference'],.2,.4)


class SequenceChecks(unittest.TestCase):
    def result(self,policy,horizon=4):
        return OpeningGraph(CARDS,policy,'empty',horizon=horizon).evaluate(SCALE,.25,.5,1.)

    def test_same_cards_same_cost_waiting_loses_fifteen_damage(self):
        early=self.result('staggered_three');late=self.result('late_same_three')
        a,b=early['final']['players'][0],late['final']['players'][0]
        self.assertEqual((a['cash'],a['hand']),(b['cash'],b['hand']))
        self.assertEqual([(u['a'],u['h']) for u in a['field']],[(u['a'],u['h']) for u in b['field']])
        self.assertEqual(early['final']['players'][1]['hp'],15)
        self.assertEqual(late['final']['players'][1]['hp'],30)
        self.assertAlmostEqual(early['value']-late['value'],15*.25)

    def test_two_gold_bridge_does_not_delay_nine_gold(self):
        for policy in ('save_9','bridge_9'):
            r=self.result(policy)
            casts=[event['own_turn'] for event in r['witness'] if event['actor']==0
                   for play in event['plays'] if play['cid']==38]
            self.assertEqual(casts,[4])

    def test_self_replacement_can_overdraw_when_not_used(self):
        bench4=self.result('draw_5');aaron4=self.result('save_5')
        b,a=bench4['final']['players'][0],aaron4['final']['players'][0]
        self.assertEqual(len(b['hand'])-len(a['hand']),1)
        self.assertEqual(b['bonus_draws'],1)
        # One lost ATK on the first attack is real, alongside the body loss.
        expected=SCALE.value(5,5)-SCALE.value(6,5)-.25+1
        self.assertAlmostEqual(bench4['value']-aaron4['value'],expected)
        bench5=self.result('draw_5',5);aaron5=self.result('save_5',5)
        b,a=bench5['final']['players'][0],aaron5['final']['players'][0]
        self.assertEqual((len(b['hand']),len(a['hand'])),(7,7))
        self.assertEqual(b['burned'],1)

    def test_attack_is_symmetric_and_terminal(self):
        attacker=Player(field=(Unit(0,377,3,2,2,ready=True,dodge=1),))
        defender=Player(field=(Unit(0,175,3,1,1,armor=True),))
        ends=attack_endpoints(Game((attacker,defender)),0)
        self.assertTrue(any(g.players[0].field and g.players[0].field[0].dodge==0 and
                            not g.players[1].field for g,path in ends))
        lethal=Game((Player(field=(Unit(0,15,6,5,5,ready=True),Unit(1,15,6,5,5,ready=True))),Player(hp=3)))
        self.assertTrue(all(len(path)<=1 for g,path in attack_endpoints(lethal,0)))

    def test_draw_can_enable_a_real_earlier_deployment(self):
        early=OpeningGraph(CARDS,'draw_accelerates_two','empty',seat='second').evaluate(SCALE,.25,.5,1.)
        later=OpeningGraph(CARDS,'normal_two_later','empty',seat='second').evaluate(SCALE,.25,.5,1.)
        frog_turns=[]
        for r in (early,later):
            frog_turns.append([event['own_turn'] for event in r['witness'] if event['actor']==0
                               for play in event['plays'] if play['cid']==2])
        self.assertEqual(frog_turns,[[3],[4]])
        self.assertEqual(early['final']['players'][0]['cash'],later['final']['players'][0]['cash'])
        self.assertEqual(early['final']['players'][1]['hp'],later['final']['players'][1]['hp']-1)
        self.assertAlmostEqual(early['value']-later['value'],SCALE.value(5,5)-SCALE.value(6,5)+.25+1.)

    def test_second_can_skip_bridge_to_reach_anchor_earlier(self):
        for policy,cid,turn in (('save_9_at3',38,3),('save_5_at2',15,2),('draw_5_at2',243,2)):
            r=OpeningGraph(CARDS,policy,'empty',seat='second').evaluate(SCALE,.25,.5,1.)
            actual=[event['own_turn'] for event in r['witness'] if event['actor']==0
                    for play in event['plays'] if play['cid']==cid]
            self.assertEqual(actual,[turn])


if __name__=='__main__':unittest.main()
