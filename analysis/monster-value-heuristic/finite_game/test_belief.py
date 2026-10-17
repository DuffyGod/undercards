"""Information timing counterexamples independent of the card engine."""
import unittest
from .belief import Solver, ProtocolError, SearchBudget, objective, pack, cell


class Tree:
    """Explicit finite payoff trees, no combat or production rules."""
    def __init__(self, rows, root='root', hide_actions=False):
        self.rows=rows; self.initial=root; self.hide_actions=hide_actions
    def root(self):return self.initial
    def row(self,s):return self.rows[s]
    def finished(self,s):return 'hp' in self.row(s)
    def owner(self,s):return self.row(s).get('owner','own')
    def hp(self,s):return self.row(s)['hp']
    def goal(self,s,constraints):return self.row(s).get('goal',True) and self.hp(s)>=constraints.get('min_own_player_hp',0)
    def observation(self,s):return (self.row(s).get('visible',s),self.owner(s),self.row(s).get('hp'))
    def actions(self,s):return self.row(s)['edges']
    def action_observation(self,a,s,child):return ('pass',) if self.hide_actions else a
    def describe_action(self,a):return list(a)


def matrix_game(left,right):
    return Tree(dict(root=dict(visible='same-root',owner='own',edges=[(('choose','A'),'A'),(('choose','B'),'B')]),
                     A=dict(visible='leaf',hp=left),B=dict(visible='leaf',hp=right)))


class BeliefTests(unittest.TestCase):
    def solve(self,games,task=None,**kwargs):
        solver=Solver(games,objective(task or {'kind':'hp'}),**kwargs)
        root=pack((w,g.root()) for w,g in games.items())
        return solver,root,solver.solve(root)

    def test_hidden_world_oracle_inflates_bound(self):
        games={'left':matrix_game(10,0),'right':matrix_game(0,10)}
        _,_,r=self.solve(games)
        oracle=min(self.solve({wid:g})[2].value for wid,g in games.items())
        self.assertEqual(r.value,(0,));self.assertEqual(oracle,(10,))
        self.assertTrue(r.policy_audit['passed'])

    def signals(self,reveal):
        games={}
        for name,correct in [('left','A'),('right','B')]:
            label=('signal',name) if reveal else ('pass',)
            games[name]=Tree(dict(root=dict(owner='enemy',visible='enemy-root',edges=[(label,'after')]),
                after=dict(owner='own',visible=name if reveal else 'still-hidden',edges=[(('choose','A'),'A'),(('choose','B'),'B')]),
                A=dict(visible='leaf',hp=10 if correct=='A' else 0),B=dict(visible='leaf',hp=10 if correct=='B' else 0)))
        return games

    def test_public_reveal_permits_future_adaptation(self):
        _,_,r=self.solve(self.signals(True))
        self.assertEqual(r.value,(10,));self.assertIsNone(r.root_action)
        self.assertEqual({tuple(n['action']) for n in r.public_nodes},{('choose','A'),('choose','B')})
        self.assertTrue(all(len(n['possible_worlds'])==1 for n in r.public_nodes))

    def test_identical_public_pass_does_not_reveal_private_hand(self):
        _,_,r=self.solve(self.signals(False))
        self.assertEqual(r.value,(0,))
        self.assertTrue(any(len(n['possible_worlds'])==2 for n in r.public_nodes))

    def test_one_world_can_have_two_indistinguishable_physical_states(self):
        game=Tree(dict(root=dict(owner='enemy',visible='root',edges=[(('private','L'),'L'),(('private','R'),'R')]),
            L=dict(owner='own',visible='shared',edges=[(('choose','A'),'LA'),(('choose','B'),'LB')]),
            R=dict(owner='own',visible='shared',edges=[(('choose','A'),'RA'),(('choose','B'),'RB')]),
            LA=dict(visible='leaf',hp=10),LB=dict(visible='leaf',hp=0),RA=dict(visible='leaf',hp=0),RB=dict(visible='leaf',hp=10)),hide_actions=True)
        _,_,r=self.solve({'w':game})
        self.assertEqual(r.value,(0,));self.assertEqual(r.public_nodes[0]['indistinguishable_physical_states'],2)

    def test_visible_root_difference_rejected(self):
        games={'a':matrix_game(1,2),'b':matrix_game(1,2)}
        games['b'].rows['root']['visible']='other visible cash'
        with self.assertRaises(ProtocolError):self.solve(games)

    def test_hidden_legality_oracle_is_rejected(self):
        games={'a':matrix_game(1,2),'b':matrix_game(1,2)}
        games['b'].rows['root']['edges']=[(('secret','only'),'A')]
        with self.assertRaisesRegex(ProtocolError,'menus differ'):self.solve(games)

    def test_duplicate_action_with_different_state_rejected(self):
        game=matrix_game(1,2);game.rows['root']['edges']=[(('A',),'A'),(('A',),'B')]
        with self.assertRaises(ProtocolError):self.solve({'w':game})

    def test_budget_exhaustion_does_not_become_zero(self):
        with self.assertRaises(SearchBudget):self.solve({'w':matrix_game(1,2)},node_limit=1)

    def test_actual_zero_hp_is_distinct_from_unknown(self):
        self.assertEqual(cell((0,),'hp')['guaranteed_player_hp'],0)
        self.assertIsNone(cell(None,'hp')['guaranteed_player_hp'])
        self.assertIsNone(cell((0,30),'joint')['guaranteed_player_hp'])

    def test_joint_goal_precedes_hp_without_adding_units(self):
        game=matrix_game(30,1);game.rows['A']['goal']=False
        _,_,r=self.solve({'w':game},{'kind':'joint','constraints':{}})
        self.assertEqual(r.value,(1,1));self.assertEqual(r.root_action,['choose','B'])

    def test_joint_goal_must_hold_in_every_world(self):
        games={'a':matrix_game(30,1),'b':matrix_game(30,1)}
        games['b'].rows['A']['goal']=False
        _,_,r=self.solve(games,{'kind':'joint','constraints':{}})
        self.assertEqual(r.value,(1,1))

    def test_stored_policy_is_replayed_not_trusted(self):
        solver,root,_=self.solve({'w':matrix_game(3,1)})
        solver.policy[root]=('illegal',)
        with self.assertRaises(ProtocolError):solver.audit(root)

    def test_reordering_or_duplicate_belief_states_has_no_weight(self):
        game=matrix_game(3,1);solver=Solver({'w':game},objective({'kind':'hp'}))
        result=solver.solve((('w','root'),('w','root')))
        self.assertEqual(result.value,(3,));self.assertEqual(len(result.policy),1)

    def test_physical_cycle_is_not_a_finite_result(self):
        game=Tree(dict(root=dict(owner='own',edges=[(('wait',),'root')])))
        with self.assertRaisesRegex(ProtocolError,'cycle'):self.solve({'w':game})

    def test_malformed_task_and_nonfinite_bound_rejected(self):
        for task in [{'kind':'expected_hp'},{'kind':'hp','constraints':{'min_hp':1}},
                     {'kind':'joint','constraints':{'min_own_player_hp':float('nan')}}]:
            with self.assertRaises(ProtocolError):objective(task)


if __name__=='__main__':unittest.main()
