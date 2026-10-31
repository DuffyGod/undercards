"""Offline own-future-order interventions with exactly unchanged observations.

Only the data generator owns a NativeGame. The learned policy never receives
this object, the suffix order, its RNG, or the opponent's hidden state.
This integrates one hidden component, not a full posterior belief.
"""
from collections import Counter
import hashlib, json, random, time
from .counterfactual_research import PrefixController, PrefixAgent, RollinRecorder
from .game import NativeGame, DecisionBudgetExceeded
from .policies import lethal
from .relational_research import small_result


def stable(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class OnlineForkRecorder(RollinRecorder):
    """First eligible decision after a preassigned turn: a stopping time.

    Unlike reservoir sampling over a completed trajectory, selection never
    uses how many later decisions happen or how the game ultimately ends.
    """
    def __init__(self,sink,seed,turns):
        super().__init__(sink,seed);self.turns=turns;self.forks={}

    def record(self,obs,actions,selected):
        index=len(self.rows);super().record(obs,actions,selected)
        if obs['player']!=0 or len(actions)<2 or lethal(obs)[0]:return
        for window,(start,stop) in enumerate(zip(self.turns,(5,12))):
            if window not in self.forks and start<=obs['turn']<=stop:
                self.forks[window]=index


class ReusedContinuation(Exception):
    def __init__(self,result):self.result=result


class SuffixController(PrefixController):
    def __init__(self,rows,fork,action,agents,suffix_seed,known=None,reference=None):
        super().__init__(rows,fork,action,agents)
        self.suffix_seed=suffix_seed;self.game=None;self.sampler=None
        self.known=known if known is not None else {};self.reference=reference or {};self.reused=False

    def choose(self,obs,actions):
        at_root=self.index==self.fork
        if at_root:
            if obs['player']!=0 or self.game is None:raise ValueError('Own causal fork required')
            before=[stable(self.game.observation(actor)) for actor in (0,1)]
            hidden=stable([[c.uid,c.kind] for c in self.game.players[1].hand]+[['deck']]+[[c.uid,c.kind] for c in self.game.players[1].deck])
            original=tuple(c.uid for c in self.game.players[0].deck)
            order=list(self.game.players[0].deck);random.Random(self.suffix_seed).shuffle(order)
            self.game.players[0].deck=order
            after=[stable(self.game.observation(actor)) for actor in (0,1)]
            if before!=after or self.game.legal_actions(0)!=actions:
                raise ValueError('Unobserved suffix changed present information or legality')
            now=stable([[c.uid,c.kind] for c in self.game.players[1].hand]+[['deck']]+[[c.uid,c.kind] for c in self.game.players[1].deck])
            if now!=hidden:raise ValueError('Opponent hidden state was modified')
            self.sampler=dict(own_future_uids=[c.uid for c in order],observation_hash=before[0],
                opponent_observation_hash=before[1],opponent_hidden_hash=hidden,
                suffix_seed=str(self.suffix_seed),information_unchanged=True,opponent_hidden_unchanged=True)
        selection=super().choose(obs,actions)
        if at_root:
            key=(tuple(c.uid for c in order),self.action)
            if tuple(c.uid for c in order)==original and self.action in self.reference:
                self.known.setdefault(key,self.reference[self.action])
            if key in self.known:
                self.reused=True;raise ReusedContinuation(self.known[key])
        return selection


def continuation(decks,seed,agents,seat,souls,rows,fork,action,suffix_seed,known=None,reference=None):
    control=SuffixController(rows,fork,action,agents,suffix_seed,known,reference)
    game=NativeGame(decks,seed,(PrefixAgent(control),PrefixAgent(control)),seats=seat,souls=souls)
    control.game=game
    try:result=small_result(game.run())
    except ReusedContinuation as reused:result=reused.result
    except DecisionBudgetExceeded as exc:
        result=dict(won=None,unfinished=True,error=str(exc),decision_seconds=[[],[]])
    if not control.checked and not result['unfinished']:raise ValueError('Intervention was never reached')
    if control.sampler is not None:
        control.known[(tuple(control.sampler['own_future_uids']),tuple(action))]=result
        control.sampler['reused_identical_continuation']=control.reused
    return result,control.sampler,control.checked
