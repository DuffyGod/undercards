"""Shared action ranker with regret weights and a training-time baseline prior.

No post-hoc probability margin: deployment selects learned logits, with the
existing bounded attack-lethal proof in LearnedPolicy. Unknown action outcomes
remain NaN/masked; baseline cross entropy is a policy regularizer, not a zero
outcome label. Scores are preferences, not calibrated Q or optimal values.
"""
from pathlib import Path
import hashlib,json
import numpy as np
from .action_value import ActionValueNetwork,encode
from .advantage_model import AdvantageNetwork

VERSION='suffix-regret-policy-1'


class RegretNetwork(ActionValueNetwork):
    feature_version=VERSION

    def __init__(self,base=None,objective='regret',seed=2026103111,hidden=32,baseline_weight=.05,
                 target_description='V5 continuation after an own-future-order intervention'):
        if objective not in ('regret','centered'):raise ValueError('Unknown policy objective')
        super().__init__(base,'centered',seed,hidden,margin=0.)
        self.objective=objective;self.baseline_weight=float(baseline_weight);self.target_description=str(target_description)

    @property
    def actor_fingerprint(self):
        return hashlib.sha256((VERSION+self.objective+self.base.actor_fingerprint).encode()+
            np.float64(self.baseline_weight).tobytes()+b''.join(self.p[k].tobytes() for k in sorted(self.p))).hexdigest()

    def encode(self,obs,actions):return encode(obs,actions)

    def action_scores(self,state,actions):return self.batch(actions[0])[1][2]

    def forward(self,state,actions):
        z=self.action_scores(state,actions);chosen=int(z.argmax());prob=np.zeros(len(z));prob[chosen]=1.
        return prob,self.predict_value(state),dict(chosen=chosen,target=self.target_description,scores_are_calibrated_q=False)

    def loss_grad(self,x,y,groups,anchors,group_weights,l2=.0001):
        y=np.asarray(y,float);groups=np.asarray(groups,int)
        if len(y)!=len(x) or np.any((y[np.isfinite(y)]<0)|(y[np.isfinite(y)]>1)):
            raise ValueError('Complete probabilities or masked unknowns required')
        q,(x,h,z)=self.batch(x);dz=np.zeros(len(z));loss=0.
        for group,weight in group_weights.items():
            ix=np.where(groups==group)[0];known=ix[np.isfinite(y[ix])]
            if not len(known) or anchors[group] not in ix or weight<=0:raise ValueError('Known targets and legal baseline anchor required')
            zz=z[ix];ex=np.exp(zz-zz.max());p=ex/ex.sum();anchor=np.where(ix==anchors[group])[0][0]
            loss+=weight*self.baseline_weight*(np.log(ex.sum())+zz.max()-z[anchors[group]])
            grad=p.copy();grad[anchor]-=1;dz[ix]+=weight*self.baseline_weight*grad
            if self.objective=='centered':
                residual=q[known]-y[known];residual-=residual.mean()
                loss+=weight*2*np.mean(residual**2)
                dz[known]+=weight*4/len(known)*residual*q[known]*(1-q[known])
            else:
                pairs=max(1,len(known)*(len(known)-1)//2)
                for j,i in enumerate(known):
                    for k in known[j+1:]:
                        delta=y[i]-y[k]
                        if delta==0:continue
                        sign=np.sign(delta);gap=abs(delta);t=-sign*(z[i]-z[k])
                        loss+=weight*gap*np.logaddexp(0,t)/pairs
                        derivative=-weight*gap*sign/(1+np.exp(-np.clip(t,-40,40)))/pairs
                        dz[i]+=derivative;dz[k]-=derivative
        dh=dz[:,None]*self.p['w']*(1-h*h)
        grads=dict(W=x.T@dh,b=dh.sum(0),w=h.T@dz,c=np.array([dz.sum()]))
        for name in ('W','w'):
            loss+=l2/2*np.sum(self.p[name]**2);grads[name]+=l2*self.p[name]
        return float(loss),grads

    def save(self,path,metadata):
        path=Path(path)
        if path.exists() or path.suffix!='.npz':raise ValueError('Preserve policy checkpoint')
        np.savez_compressed(path,**self.p,critic=self.critic,base_actor=self.base.actor,base_critic=self.base.critic,base_advantage=self.base.advantage,
            metadata=json.dumps(dict(metadata,model_kind='suffix_regret',feature_version=VERSION,objective=self.objective,
                hidden=self.hidden,baseline_weight=self.baseline_weight,base_margin=self.base.margin,target_description=self.target_description,
                actor_fingerprint=self.actor_fingerprint,fingerprint=self.fingerprint,parameters=self.parameters)))

    @classmethod
    def load(cls,path):
        with np.load(path,allow_pickle=False) as data:
            meta=json.loads(str(data['metadata']))
            if meta['feature_version']!=VERSION:raise ValueError('Incompatible policy schema')
            base=AdvantageNetwork(data['base_actor'].copy(),data['base_critic'].copy(),data['base_advantage'].copy(),meta['base_margin'])
            net=cls(base,meta['objective'],hidden=meta['hidden'],baseline_weight=meta['baseline_weight'],
                target_description=meta.get('target_description','V5 continuation after an own-future-order intervention'))
            for name in net.p:
                if data[name].shape!=net.p[name].shape:raise ValueError('Policy parameter shape mismatch')
                net.p[name]=data[name].copy()
            net.critic=data['critic'].copy()
        if net.critic.shape!=(74,) or net.fingerprint!=meta['fingerprint']:raise ValueError('Policy checksum mismatch')
        return net,meta
