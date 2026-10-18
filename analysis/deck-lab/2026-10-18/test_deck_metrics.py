import itertools
import unittest

from deck_metrics import (gold_path,hand_budget_probabilities,librarian_need,
    bookshelf_metrics,pair_access_probability,probability_at_least)


class StructuralMetricsChecks(unittest.TestCase):
    def test_retained_gold_and_second_player_parity(self):
        first=gold_path(11,True);second=gold_path(11,False)
        self.assertEqual([first[i-1]['gold_before'] for i in (1,3,10,11)],[2,7,56,66])
        self.assertEqual([second[i-1]['gold_before'] for i in (1,3,10,11)],[3,9,61,71])
        self.assertEqual(gold_path(3,True,[2,1])[-1]['gold_before'],4)
        with self.assertRaises(ValueError):gold_path(2,True,[3])

    def test_two_librarians_alone_need_always_ready_once_one_seen(self):
        counts={'185':2,**{str(1000+i):1 for i in range(23)}}
        for removed in (1,3,7,12,25):
            result=librarian_need(counts,removed)
            self.assertEqual(result['p_need_given_focal_seen'],1.)
            self.assertAlmostEqual(result['p_seen_and_need'],probability_at_least(25,2,removed))

    def test_extra_duplicate_pair_requires_its_own_copy_removed(self):
        counts={'185':2,'A':2,'B':1,'C':1}
        result=librarian_need(counts,2)
        self.assertAlmostEqual(result['p_need'],4/15)
        self.assertAlmostEqual(result['p_focal_seen'],9/15)
        self.assertAlmostEqual(result['p_need_given_focal_seen'],4/9)

    def test_three_librarians_need_two_removed_not_just_one(self):
        counts={'185':3,**{str(1000+i):1 for i in range(22)}}
        self.assertEqual(librarian_need(counts,1)['p_need_given_focal_seen'],0.)
        self.assertAlmostEqual(librarian_need(counts,2)['p_seen_and_need'],3/300)

    def test_bookshelf_need_spell_copies_are_in_remaining_deck(self):
        counts={'466':1,'S':2,'X':2}
        result=bookshelf_metrics(counts,3,['S'])
        self.assertAlmostEqual(result['p_seen'],.6)
        self.assertAlmostEqual(result['p_need'],.3)
        self.assertAlmostEqual(result['p_seen_and_need'],.1)
        self.assertEqual(bookshelf_metrics(counts,0,[])['p_need'],1.)

    def test_same_name_pair_needs_two_physical_copies(self):
        self.assertEqual(pair_access_probability({'A':1,'B':4},3,'A','A'),0.)
        self.assertAlmostEqual(pair_access_probability({'A':2,'B':3},2,'A','A'),1/10)
        self.assertAlmostEqual(pair_access_probability({'A':2,'B':3},2,'A','B'),6/10)

    def test_affordable_pair_multiset_matches_physical_hand_enumeration(self):
        costs=(1,1,4,6,6)
        for hand in (0,1,2,3,5):
            for cash in (0,2,5,7,12):
                samples=list(itertools.combinations(range(len(costs)),hand))
                single=sum(any(costs[i]<=cash for i in sample) for sample in samples)/len(samples)
                pair=sum(any(costs[a]+costs[b]<=cash for a,b in itertools.combinations(sample,2))
                         for sample in samples)/len(samples)
                result=hand_budget_probabilities({1:2,4:1,6:2},hand,cash)
                self.assertAlmostEqual(result['p_affordable_single'],single)
                self.assertAlmostEqual(result['p_affordable_two'],pair)

    def test_hand_limit_and_invalid_inputs_are_rejected(self):
        with self.assertRaises(ValueError):hand_budget_probabilities({1:25},8,5)
        with self.assertRaises(ValueError):librarian_need({'185':2},3)
        with self.assertRaises(ValueError):probability_at_least(25,26,3)
        with self.assertRaises(ValueError):gold_path(2,'first')


if __name__=='__main__':unittest.main()
