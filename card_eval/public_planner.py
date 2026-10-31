"""Proof-first product planner; frozen V7 implementation is _planner_v1.

This variant has a distinct fingerprint and cannot inherit V7 qualification.
"""
import hashlib,json,time
from ._planner_v1 import PublicGame,UnknownDraw,signature,PublicPlanner as FrozenPlanner
from .policies import lethal,LearnedPolicy

VERSION='public-own-turn-proof-first-3'


class _CachedAttackPolicy(LearnedPolicy):
    """Reuse only the exact observation's causal, already computed search."""
    attack_observation=None
    attack_result=None
    def choose(self,obs,actions):
        cached=self.attack_result if self.attack_observation is obs else None
        return super().choose(obs,actions,attack_search=cached)


class PublicPlanner(FrozenPlanner):
    name='shared_policy_public_proof_first'

    def __init__(self,network,mode='proof',margin=.1,nodes=48,depth=3,width=4,seconds=.12):
        super().__init__(network,mode,margin,nodes,depth,width,seconds)
        self.base=_CachedAttackPolicy(network)
        self.config=dict(self.config,version=VERSION)
        self.fingerprint=hashlib.sha256((self.network.fingerprint+json.dumps(self.config,sort_keys=True)).encode()).hexdigest()

    def choose(self,obs,actions):
        started=time.perf_counter();plan,nodes=lethal(obs,self.base.search_nodes)
        if not plan:
            config=self.config;remaining=max(1e-9,config['seconds']-(time.perf_counter()-started))
            self.base.attack_observation=obs;self.base.attack_result=(plan,nodes)
            self.config=dict(config,seconds=remaining)
            try:result=super().choose(obs,actions)
            finally:
                self.config=config;self.base.attack_observation=None;self.base.attack_result=None
            result.update(planner=config,base_attack_search_reused=True,effective_expansion_seconds=remaining,seconds=time.perf_counter()-started)
            return result
        # A value estimate cannot improve on a deterministic terminal win.
        # Reprove at each decision, independently of stale pending sequences.
        self.pending=[];_,value,_=self.network.forward(*self.network.encode(obs,actions));selected=plan[0]
        return dict(action=selected,action_index=actions.index(selected),behavior_probability=1.,value=value,
            policy=self.fingerprint,base_policy=self.network.fingerprint,planner=self.config,
            planner_reason='base_attack_proof',planner_gain=0.,planner_nodes=0,unknown_draw_boundaries=0,
            proof_length=len(plan),proof_mismatch=False,search_override=True,search_nodes=nodes,
            base_attack_search_reused=False,
            value_target='Frozen base-policy continuation; not searched-policy value',seconds=time.perf_counter()-started)
