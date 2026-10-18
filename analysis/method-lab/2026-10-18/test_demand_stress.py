"""Physical checks for shared source-board transformations, not price fitting."""
import unittest

from demand_stress import transform_panel


class SharedDemandTransforms(unittest.TestCase):
    def setUp(self):
        self.original = [dict(enemy=[[3,1],[4,2],[5,3]],weight=.25,source_ids=[1,2,3]),
                         dict(enemy=[[2,2],[1,1],[4,2]],weight=.75,source_ids=[4,5,6])]

    def test_true_aoe_removes_dead_monsters(self):
        result = transform_panel(self.original,'aoe2_survivors')
        self.assertEqual(result[0]['enemy'],((5,1),))

    def test_empty_outcome_keeps_its_original_mass(self):
        result = transform_panel(self.original,'aoe2_survivors')
        self.assertEqual(len(result),2)
        self.assertEqual(result[1]['enemy'],())
        self.assertEqual(result[1]['weight'],.75)
        self.assertEqual(sum(r['weight'] for r in result),1.)

    def test_clamp_and_deletion_share_exact_source_board_lineage(self):
        full=transform_panel(self.original,'full')
        clamp=transform_panel(self.original,'clamp2')
        survivors=transform_panel(self.original,'aoe2_survivors')
        for index,variants in enumerate(zip(full,clamp,survivors)):
            for row in variants:
                self.assertEqual(row['source_board_index'],index)
                self.assertEqual(row['original_enemy'],full[index]['enemy'])
                self.assertEqual(row['source_ids'],self.original[index]['source_ids'])
                self.assertEqual(row['weight'],self.original[index]['weight'])
        self.assertEqual(clamp[0]['enemy'],((3,1),(4,1),(5,1)))
        self.assertEqual(clamp[1]['enemy'],((2,1),(1,1),(4,1)))

    def test_transform_does_not_mutate_original_or_share_source_id_lists(self):
        result=transform_panel(self.original,'aoe2_survivors')
        result[0]['source_ids'].append(999)
        self.assertEqual(self.original[0]['enemy'],[[3,1],[4,2],[5,3]])
        self.assertEqual(self.original[0]['source_ids'],[1,2,3])


if __name__ == '__main__':
    unittest.main()
