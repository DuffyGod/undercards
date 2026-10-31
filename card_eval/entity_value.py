"""Small learned entity-set value, with a frozen semantic V5 actor.

Nonlinear shared entity embeddings precede pooling. Hand order is ignored;
public board position is retained because callback order/Kindness can matter.
The aggregate MLP control has approximately the same parameter budget.
"""
from pathlib import Path
import hashlib,json
import numpy as np
from .legacy import features
from .relations import state_features
from .advantage_model import AdvantageNetwork

VERSION='semantic-entity-continuation-1'
GLOBAL=74;TOKEN=15+len(features.TRIGGERS)*len(features.OPS)*len(features.SCOPES)*3+2
SLOTS=15;STATE=GLOBAL+SLOTS*TOKEN+SLOTS
ZONES=(('hand',7,False),('own',4,True),('enemy',4,True))


def entity_state(obs):
    rows=[];masks=[]
    for zone,cap,board in ZONES:
        cards=obs[zone]
        if len(cards)>cap:raise ValueError('Public zone exceeds supported capacity')
        for i,card in enumerate(cards):
            position=[i/(cap-1),float(i==len(cards)-1)] if board else [0.,0.]
            # Preserve trigger/op/scope/amount binding. The older descriptor
            # separately pooled scopes and triggers and could alias effects.
            base=features.card_features(card,board)[:15]
            effects=np.zeros((len(features.TRIGGERS),len(features.OPS),len(features.SCOPES),3))
            if not (board and card['silenced']):
                for e in (card['spec'] if board else card)['effects']:
                    effects[features.TRIGGERS.index(e['trigger']),features.OPS.index(e['op']),features.SCOPES.index(e['scope'])]+=[1.,e['amount']/10,e['health']/10]
            rows.append(np.r_[base,effects.ravel(),position]);masks.append(1.)
        rows.extend([np.zeros(TOKEN)]*(cap-len(cards)));masks.extend([0.]*(cap-len(cards)))
    return np.r_[state_features(obs),np.asarray(rows).ravel(),masks]


class EntityValueNetwork:
    feature_version=VERSION
    # Protocol marker: PublicPlanner must call this encoder for value leaves.
    critic=np.zeros(1)

    def __init__(self,base=None,variant='entity',seed=2026103108):
        if variant not in ('entity','aggregate'):raise ValueError('Unknown value representation')
        self.base=base if base is not None else AdvantageNetwork();self.variant=variant
        rng=np.random.default_rng(seed);self.p={}
        if variant=='entity':
            self.p.update(Wphi=rng.normal(0,1/np.sqrt(TOKEN),(TOKEN,16)),bphi=np.zeros(16));size=GLOBAL+3*16;hidden=16
        else:size=GLOBAL;hidden=123
        self.p.update(Wvalue=rng.normal(0,1/np.sqrt(size),(size,hidden)),bvalue=np.zeros(hidden),
                      wout=rng.normal(0,1/np.sqrt(hidden),hidden),bout=np.zeros(1))

    @property
    def actor_fingerprint(self):return self.base.actor_fingerprint

    @property
    def fingerprint(self):
        return hashlib.sha256((VERSION+self.variant+self.base.fingerprint).encode()+b''.join(self.p[k].tobytes() for k in sorted(self.p))).hexdigest()

    @property
    def parameters(self):return sum(v.size for v in self.p.values())

    def value_encode(self,obs):return entity_state(obs) if self.variant=='entity' else state_features(obs)

    def encode(self,obs,actions):return self.value_encode(obs),self.base.encode(obs,actions)[1]
    def action_scores(self,state,actions):return self.base.action_scores(state[:GLOBAL],actions)

    def batch_forward(self,states):
        x=np.asarray(states,float);x=x[None,:] if x.ndim==1 else x;p=self.p
        if self.variant=='entity':
            if x.shape[1]!=STATE:raise ValueError('Missing entity inputs; no zero substitution')
            tokens=x[:,GLOBAL:GLOBAL+SLOTS*TOKEN].reshape(-1,SLOTS,TOKEN)
            mask=x[:,-SLOTS:,None];phi=np.tanh(tokens@p['Wphi']+p['bphi'])
            pooled=phi*mask
            v=np.c_[x[:,:GLOBAL],pooled[:,:7].sum(1)/7,pooled[:,7:11].sum(1)/4,pooled[:,11:].sum(1)/4]
            cache=dict(tokens=tokens,mask=mask,phi=phi)
        else:
            if x.shape[1]!=GLOBAL:raise ValueError('Aggregate feature mismatch')
            v=x;cache={}
        hidden=np.tanh(v@p['Wvalue']+p['bvalue']);logits=hidden@p['wout']+p['bout'][0]
        return logits,dict(cache,v=v,hidden=hidden)

    def predict_value(self,state):
        z=self.batch_forward(state)[0][0];return float(2/(1+np.exp(-np.clip(z,-40,40)))-1)

    def forward(self,state,actions):
        prob,_,cache=self.base.forward(state[:GLOBAL],actions)
        return prob,self.predict_value(state),cache

    def loss_grad(self,states,labels,weights,l2=.001,normalize=True):
        y=np.asarray(labels,float);w=np.asarray(weights,float);w=w/w.sum() if normalize else w
        z,c=self.batch_forward(states);p=self.p
        if y.shape!=z.shape or not np.isin(y,(0,1)).all() or not np.isfinite(w).all():raise ValueError('Complete terminal targets required')
        regularized=[k for k in p if k.startswith('W') or k=='wout']
        loss=float(w@(np.logaddexp(0,z)-y*z)+l2/2*sum(np.sum(p[k]**2) for k in regularized))
        dz=w*(1/(1+np.exp(-np.clip(z,-40,40)))-y)
        grads=dict(wout=c['hidden'].T@dz,bout=np.array([dz.sum()]))
        dh=dz[:,None]*p['wout']*(1-c['hidden']**2)
        grads.update(Wvalue=c['v'].T@dh,bvalue=dh.sum(0))
        if self.variant=='entity':
            dv=(dh@p['Wvalue'].T)[:,GLOBAL:].reshape(-1,3,16)
            dphi=np.concatenate((np.repeat(dv[:,0:1]/7,7,axis=1),np.repeat(dv[:,1:2]/4,4,axis=1),np.repeat(dv[:,2:3]/4,4,axis=1)),axis=1)
            dp=dphi*c['mask']*(1-c['phi']**2)
            grads.update(Wphi=c['tokens'].reshape(-1,TOKEN).T@dp.reshape(-1,16),bphi=dp.sum((0,1)))
        for k in regularized:grads[k]+=l2*p[k]
        return loss,grads

    def save(self,path,metadata):
        path=Path(path)
        if path.exists() or path.suffix!='.npz':raise ValueError('Preserve checkpoints; use a new .npz')
        np.savez_compressed(path,**self.p,base_actor=self.base.actor,base_critic=self.base.critic,
            base_advantage=self.base.advantage,metadata=json.dumps(dict(metadata,model_kind='entity_continuation',
                feature_version=VERSION,variant=self.variant,base_margin=self.base.margin,
                fingerprint=self.fingerprint,actor_fingerprint=self.actor_fingerprint,parameters=self.parameters)))

    @classmethod
    def load(cls,path):
        with np.load(path,allow_pickle=False) as data:
            meta=json.loads(str(data['metadata']))
            if meta['feature_version']!=VERSION:raise ValueError('Incompatible entity schema')
            base=AdvantageNetwork(data['base_actor'].copy(),data['base_critic'].copy(),data['base_advantage'].copy(),meta['base_margin'])
            net=cls(base,meta['variant'])
            for k in net.p:
                if data[k].shape!=net.p[k].shape:raise ValueError('Entity parameter shape mismatch')
                net.p[k]=data[k].copy()
        if net.fingerprint!=meta['fingerprint'] or net.actor_fingerprint!=meta['actor_fingerprint']:raise ValueError('Entity checkpoint checksum mismatch')
        return net,meta
