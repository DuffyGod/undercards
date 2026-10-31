"""Bounded same-turn planning from an observation, without hidden-state access.

Rules are the retained engine's methods. Unknown draws and nonterminal turn
ends are boundaries, never zero-valued transitions. A value leaf estimates
continuation by the frozen base actor, not by this new search policy.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib, json, time
import numpy as np
from .legacy import environment, model, features
from .training import decode
from .knowledge import summary, SCHEMA
from .policies import LearnedPolicy
from .relations import state_features

VERSION = 'public-own-turn-1'


class UnknownDraw(RuntimeError):
    """The next card is outside the policy's information set."""


class PublicGame(environment.LearningGame):
    """Own-turn adapter: construction accepts only the public observation."""
    def __init__(self, obs):
        self.root = deepcopy(obs); self.actor = obs['player']
        self.cfg = environment.Config(**obs['config']); self.silence_mode = obs['silence_mode']
        self.players = [model.Player(deck=None), model.Player(deck=None)]
        self.known = {}; self.public_events = []
        self.candidate_played = self.candidate_first_turn = 0
        for side, prefix, zone in ((self.actor, '', 'own'), (1-self.actor, 'enemy_', 'enemy')):
            p = self.players[side]
            for field in ('hp','cash','turn','fatigue','previous_spent'):
                setattr(p, field, obs[prefix+field])
            p.spent = obs['spent'] if side == self.actor else 0
            p.hand = [] if side == self.actor else None  # opaque, never treated as an empty hidden hand
            for raw in obs[zone]:
                raw = deepcopy(raw); raw['spec'] = decode(raw['spec'])
                p.units.append(environment.Unit(**raw))
        for raw in obs['hand']:
            self.players[self.actor].hand.append(model.Card(raw['uid'],raw['role']))
            self.known[self.actor,raw['uid']] = decode(raw)

    def spec(self, actor, card): return self.known[actor,card.uid]

    def draw(self, actor):
        if actor != self.actor or self.root['deck_count']:
            raise UnknownDraw('Unobserved card identity; search stops before drawing')
        p = self.players[actor]; p.draws += 1; p.fatigue += 1; p.hp -= p.fatigue
        self.event(actor,'fatigue',damage=p.fatigue)

    def event(self, actor, action, **kw):
        if action in ('play','attack','punishment','fatigue','start','end','effect'):
            self.public_events.append(dict(side=int(actor!=self.actor),action=action,
                amount=kw.get('damage',kw.get('attack',kw.get('income',kw.get('amount',0)))),cost=kw.get('cost',0)))
        if action == 'play' and self.root.get('knowledge_schema') == SCHEMA:
            spec = asdict(self.known[actor,kw['card']['uid']]); v = self.root['knowledge']
            full = features.card_features(spec)/25; small = summary(spec)/25; n = features.CARD_DIM
            for j,x in enumerate(full): v[n+j] += float(x)
            for j,x in enumerate(small): v[3*n+16+j] += float(x)
            v[-2] += 1/25

    def observation(self, actor=None):
        if actor is not None and actor != self.actor: raise ValueError('No hidden opponent observation')
        obs = deepcopy(self.root); a = self.players[self.actor]; b = self.players[1-self.actor]
        for field in ('hp','cash','turn','fatigue','previous_spent'):
            obs[field] = getattr(a,field); obs['enemy_'+field] = getattr(b,field)
        obs['spent'] = a.spent
        obs['hand'] = [dict(uid=h.uid,role=h.kind,candidate=h.kind=='candidate',**asdict(self.spec(self.actor,h))) for h in a.hand]
        obs['own'] = [asdict(u) for u in a.units]; obs['enemy'] = [asdict(u) for u in b.units]
        obs['history'] = (obs['history']+self.public_events)[-8:]
        return obs

    def child(self, action):
        child = deepcopy(self)
        if tuple(action)[0] == 'end':
            # Only callbacks can prove a win here. A nonterminal end is not an
            # own-turn decision state and must not be evaluated as one.
            for u in list(child.players[self.actor].units):
                if not u.silenced: child._effects(self.actor,u.uid,u.spec,'end')
        else: child.apply(self.actor,tuple(action))
        return child

    def terminal(self):
        a,b = self.players[self.actor],self.players[1-self.actor]
        if min(a.hp,b.hp)>0:return None
        return bool(a.hp>0 and b.hp<=0)


def signature(obs):
    # Known/seen bags use sorted addition in the game and incremental addition
    # here. Ignore only floating-point accumulation noise, not public fields.
    def clean(v):
        if isinstance(v,float):return round(v,12)
        if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
        if isinstance(v,(list,tuple)):return [clean(x) for x in v]
        return v
    return hashlib.sha256(json.dumps(clean(obs),sort_keys=True,separators=(',',':')).encode()).hexdigest()


class PublicPlanner:
    name = 'shared_policy_public_lookahead'
    def __init__(self,network,mode='proof',margin=.1,nodes=48,depth=3,width=4,seconds=.18):
        if not hasattr(network,'predict_value') or not hasattr(network,'critic'):
            raise ValueError('Public planning needs a supported relation/paired/memory value model')
        if mode not in ('proof','value'):raise ValueError('Unknown public planner mode')
        if nodes<1 or depth<1 or width<1 or not 0<seconds<.25 or not 0<=margin<=1:raise ValueError('Invalid planning budget')
        self.network=network;self.base=LearnedPolicy(network);self.pending=[]
        self.config=dict(version=VERSION,mode=mode,margin=margin,nodes=nodes,depth=depth,width=width,seconds=seconds)
        self.fingerprint=hashlib.sha256((network.fingerprint+json.dumps(self.config,sort_keys=True)).encode()).hexdigest()

    def ordered(self, obs, actions):
        state, af = self.network.encode(obs,actions); probs,_,_ = self.network.forward(state,af)
        # Ordering uses the actor only. Fitting the critic cannot alter which
        # nodes are expanded at a fixed node budget.
        scores=self.network.action_scores(state,af) if hasattr(self.network,'action_scores') else probs
        indices=sorted(range(len(actions)),key=lambda i:(i!=int(probs.argmax()),-float(scores[i]),i))
        return [actions[i] for i in indices[:self.config['width']]]

    def value_state(self, obs):
        if self.network.critic.shape==(74,):return state_features(obs)
        return self.network.encode(obs,[('end',-1,-1,-1)])[0]

    def choose(self,obs,actions):
        started=time.perf_counter(); selection=self.base.choose(obs,actions); self.pending=list(self.pending)
        config=self.config; nodes=barriers=0; reason='base'; gain=0.; mismatch=False
        selected=selection['action']; chosen_path=[]
        if self.pending:
            expected, action=self.pending.pop(0)
            if expected==signature(obs) and action in actions:selected=action;reason='committed_proof'
            else:self.pending=[];mismatch=True
        if reason=='base':
            root=PublicGame(obs); frontier=[(root,[],[])]
            rootvalue=(float(selection['value'])+1)/2;bestvalue=rootvalue
            bestpath=[];proof=None
            for _ in range(config['depth']):
                following=[]
                for game,path,signatures in frontier:
                    legal=game.legal_actions(game.actor)
                    if not legal:continue
                    current=game.observation();current_sig=signature(current)
                    for action in self.ordered(current,legal):
                        if nodes>=config['nodes'] or time.perf_counter()-started>=config['seconds']:break
                        nodes+=1
                        try:child=game.child(action)
                        except UnknownDraw:barriers+=1;continue
                        newpath=path+[action]; newsigs=signatures+[current_sig]
                        terminal=child.terminal()
                        if terminal is True:proof=(newpath,newsigs);break
                        if terminal is False or action[0]=='end':continue
                        observation=child.observation();state=self.value_state(observation)
                        value=(self.network.predict_value(state)+1)/2
                        if value>bestvalue:bestvalue=value;bestpath=newpath
                        following.append((child,newpath,newsigs))
                    if proof or nodes>=config['nodes'] or time.perf_counter()-started>=config['seconds']:break
                if proof:break
                # Beam selection is independent of critic, breadth first with
                # deterministic policy ordering. No hidden world is sampled.
                frontier=following[:config['width']]
                if not frontier or nodes>=config['nodes'] or time.perf_counter()-started>=config['seconds']:break
            if proof:
                chosen_path,sigs=proof;selected=chosen_path[0];reason='public_proof'
                self.pending=list(zip(sigs[1:],chosen_path[1:]))
            elif config['mode']=='value' and bestpath and bestvalue-rootvalue>config['margin']:
                selected=bestpath[0];reason='base_continuation_value';gain=bestvalue-rootvalue
        selection.update(action=selected,action_index=actions.index(selected),behavior_probability=1.,
            policy=self.fingerprint,base_policy=self.network.fingerprint,planner=config,
            planner_reason=reason,planner_gain=gain,planner_nodes=nodes,unknown_draw_boundaries=barriers,
            proof_length=len(chosen_path),proof_mismatch=mismatch,seconds=time.perf_counter()-started)
        selection['search_override']=bool(selection['search_override'] or reason!='base')
        selection['value_target']='Frozen base-policy continuation; not searched-policy value'
        return selection
