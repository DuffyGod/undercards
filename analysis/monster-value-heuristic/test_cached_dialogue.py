import copy
import unittest
import batch_annotate as b
import cached_dialogue as c
from few_shots import examples
import knowledge_resolution as k


class CacheAndKnowledgeTests(unittest.TestCase):
    def test_exact_prefix_separate_final_payload(self):
        api = b.load_api()
        task = {'prompt':'Process these cards','system':'Shared rules', 'context':{'few_shots':examples(),'cards':[1]}}
        other = copy.deepcopy(task)
        other['context']['cards'] = [2,3,4]
        a, z = c.build_payload(api,task), c.build_payload(api,other)
        self.assertEqual(len(a['messages']),20)
        self.assertEqual(a['messages'][:-1],z['messages'][:-1])
        self.assertNotEqual(a['messages'][-1],z['messages'][-1])
        self.assertNotIn('few_shots',a['messages'][-1]['content'])

    def test_missing_cache_statistics_are_unknown(self):
        self.assertFalse(c.cache_metrics({})['reported'])
        self.assertIsNone(c.cache_metrics({})['cached_tokens'])
        self.assertEqual(c.cache_metrics({'prompt_tokens_details':{'cached_tokens':1024}})['cached_tokens'],1024)

    def test_only_precisely_known_single_question_is_resolved(self):
        known = 'target_metadata=ALL，但卡面未明确伤害目标为怪物还是玩家'
        row = {'card_id':20,'unresolved':[known]}
        new, changes = k.resolve(row,{'target':'ALL'},'K007: Single target scope known')
        self.assertFalse(new['unresolved'])
        self.assertEqual(row['unresolved'],[known])
        self.assertIn('premise_sha256',changes[0])
        for extra in ('；若同时击杀双方，Dust结算顺序是否按位置？', '；Transparency优先级如何？'):
            mixed = {'card_id':20,'unresolved':[known+extra]}
            kept, changes = k.resolve(mixed,{'target':'ALL'},'K007: Single target scope known')
            self.assertEqual(kept['unresolved'],mixed['unresolved'])
            self.assertFalse(changes)

    def test_new_unknowns_never_share_a_signature(self):
        from test_batch_annotate import row
        a, z = row(), row()
        a['unresolved']=['ALL目标范围与Transparency优先级如何？']
        z['unresolved']=['ALL目标范围与沉默后来源如何？']
        self.assertNotEqual(b.signature(a),b.signature(z))


if __name__ == '__main__':
    unittest.main()
