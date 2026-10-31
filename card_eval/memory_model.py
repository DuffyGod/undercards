"""A shared improvement head with explicit legal knowledge and a frozen V5 base."""
from pathlib import Path
import hashlib,json
import numpy as np
from .advantage_model import AdvantageNetwork, encode as action_encode, head_features as old_head, HEAD_DIM as OLD_HEAD_DIM
from .knowledge import vector, STATE_DIM, SUMMARY_DIM
from .legacy import features

VERSION='known-seen-action-improvement-1'
MEMORY_CONTEXT=3*SUMMARY_DIM+2
HEAD_DIM=OLD_HEAD_DIM+81*MEMORY_CONTEXT


def encode(obs,actions,use_memory=True):
    state,af=action_encode(obs,actions);known=vector(obs)
    return np.r_[state,known if use_memory else np.zeros_like(known)],af


def head_features(state,actions):
    memory=state[74+3*features.CARD_DIM:]
    return np.c_[old_head(state[:74],actions),
                 (actions[:,:81,None]*np.clip(memory,-3,3)[None,None,:]).reshape(len(actions),81*MEMORY_CONTEXT)]


class MemoryNetwork(AdvantageNetwork):
    feature_version=VERSION

    def __init__(self,base=None,advantage=None,critic=None,margin=.05,use_memory=True):
        self.base=base if base is not None else AdvantageNetwork()
        self.actor=self.base.actor
        self.advantage=np.asarray(advantage if advantage is not None else np.zeros(HEAD_DIM),float)
        self.critic=np.asarray(critic if critic is not None else np.zeros(STATE_DIM),float)
        self.margin=float(margin);self.use_memory=bool(use_memory)

    def encode(self,obs,actions):return encode(obs,actions,self.use_memory)

    @property
    def actor_fingerprint(self):
        return hashlib.sha256(VERSION.encode()+self.base.actor_fingerprint.encode()+self.advantage.tobytes()+
                              np.float64(self.margin).tobytes()+bytes([self.use_memory])).hexdigest()

    def action_scores(self,state,actions):return head_features(state,actions)@self.advantage

    def forward(self,state,actions):
        previous=int(self.base.forward(state[:74],actions)[0].argmax())
        scores=self.action_scores(state,actions);best=int(scores.argmax())
        chosen=best if scores[best]-scores[previous]>self.margin else previous
        prob=np.zeros(len(actions));prob[chosen]=1.
        return prob,self.predict_value(state),dict(base=previous,chosen=chosen,predicted_gain=float(scores[chosen]-scores[previous]))

    def save(self,path,metadata):
        path=Path(path)
        if path.exists() or path.suffix!='.npz':raise ValueError('Use a new .npz checkpoint')
        np.savez_compressed(path,base_actor=self.base.actor,base_advantage=self.base.advantage,base_critic=self.base.critic,
            advantage=self.advantage,critic=self.critic,metadata=json.dumps(dict(metadata,model_kind='known_seen_improvement',
            feature_version=VERSION,base_margin=self.base.margin,margin=self.margin,use_memory=self.use_memory,
            actor_fingerprint=self.actor_fingerprint,fingerprint=self.fingerprint)))

    @classmethod
    def load(cls,path):
        with np.load(path,allow_pickle=False) as data:
            meta=json.loads(str(data['metadata']))
            if meta['feature_version']!=VERSION:raise ValueError('Feature version mismatch')
            base=AdvantageNetwork(data['base_actor'].copy(),data['base_critic'].copy(),data['base_advantage'].copy(),meta['base_margin'])
            net=cls(base,data['advantage'].copy(),data['critic'].copy(),meta['margin'],meta['use_memory'])
        if net.advantage.shape!=(HEAD_DIM,) or net.critic.shape!=(STATE_DIM,):raise ValueError('Checkpoint shape mismatch')
        if net.fingerprint!=meta['fingerprint']:raise ValueError('Checkpoint checksum mismatch')
        return net,meta
