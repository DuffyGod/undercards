"""Death-timing anchors for the shared joint-price stress experiment."""
import json
from pathlib import Path
import unittest

from statistical_value import Prices, best_value, deployment_plans


HERE = Path(__file__).resolve().parent


class DeathTimingAnchors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = json.loads((HERE/'statistical_inputs.json').read_text(encoding='utf-8'))
        cls.cards = cls.inputs['cards']
        cls.card = cls.cards['469']
        cls.enemy = ((4,3),(1,1),(2,1))
        cls.prices = Prices(cls.inputs,face_share=.35,threshold=.6,tail=0.,face=.15)

    def test_one_extra_hp_prevents_current_dust_without_erasing_its_future_trigger(self):
        old = dict(deployment_plans(self.card,self.cards,self.enemy,2))
        new = dict(deployment_plans(self.card,self.cards,self.enemy,2,h_delta=1))
        _, old_team, old_enemy, *_ = old['deploy:attack_0'][0]
        _, new_team, new_enemy, *_ = new['deploy:attack_0'][0]
        self.assertEqual(old_enemy,((1,1),(2,1)))
        self.assertEqual(new_enemy,old_enemy)
        self.assertEqual([(u.a,u.h,u.taunt,u.dust,u.root) for u in old_team],
                         [(4,3,True,'',False)])
        self.assertEqual([(u.a,u.h,u.taunt,u.dust,u.root) for u in new_team],
                         [(3,1,False,'child',True)])

    def test_tail_zero_can_value_extra_hp_negatively_because_child_arrives_later(self):
        old,old_plan = best_value(self.card,self.cards,self.enemy,2,self.prices,
                                  'damage2',.1,0.)
        new,new_plan = best_value(self.card,self.cards,self.enemy,2,self.prices,
                                  'damage2',.1,0.,h_delta=1)
        f = self.prices.scale.value
        self.assertEqual(old_plan,'deploy:attack_0')
        self.assertEqual(new_plan,'deploy:attack_0')
        self.assertAlmostEqual(old,.9*(2*f(4,3))+.1*(f(4,3)+f(4,1)))
        # Killing the injured B would upgrade its current stock to O. The
        # opponent can decline this reply, so the increased reply opportunity
        # must not force that advantageous death.
        self.assertAlmostEqual(new,f(4,3)+f(3,1))
        certain_reply,_ = best_value(self.card,self.cards,self.enemy,2,self.prices,
                                     'damage2',1.,0.,h_delta=1)
        self.assertAlmostEqual(certain_reply,new)
        self.assertGreater(f(3,5),f(3,4))
        self.assertLess(new,old)


if __name__ == '__main__':
    unittest.main()
