"""Proof-first product planner; frozen V7 implementation is _planner_v1.

This variant has a distinct fingerprint and cannot inherit V7 qualification.
"""
import hashlib,json,time
from ._planner_v1 import PublicGame,UnknownDraw,signature,PublicPlanner as FrozenPlanner
from .policies import lethal

VERSION='public-own-turn-proof-first-2'


class PublicPlanner(FrozenPlanner):
    name='shared_policy_public_proof_first'

    def __init__(self,network,mode='proof',margin=.1,nodes=48,depth=3,width=4,seconds=.12):
        super().__init__(network,mode,margin,nodes,depth,width,seconds)
        self.config=dict(self.config,version=VERSION)
        self.fingerprint=hashlib.sha256((self.network.fingerprint+json.dumps(self.config,sort_keys=True)).encode()).hexdigest()

    def choose(self,obs,actions):
        started=time.perf_counter();plan,nodes=lethal(obs,self.base.search_nodes)
        if not plan:
            result=super().choose(obs,actions);result['seconds']=time.perf_counter()-started;return result
        # A value estimate cannot improve on a deterministic terminal win.
        # Reprove at each decision, independently of stale pending sequences.
        self.pending=[];_,value,_=self.network.forward(*self.network.encode(obs,actions));selected=plan[0]
        return dict(action=selected,action_index=actions.index(selected),behavior_probability=1.,value=value,
            policy=self.fingerprint,base_policy=self.network.fingerprint,planner=self.config,
            planner_reason='base_attack_proof',planner_gain=0.,planner_nodes=0,unknown_draw_boundaries=0,
            proof_length=len(plan),proof_mismatch=False,search_override=True,search_nodes=nodes,
            value_target='Frozen base-policy continuation; not searched-policy value',seconds=time.perf_counter()-started)
