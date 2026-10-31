"""Build a reviewed model registry from frozen evidence, never retrain weights."""
from pathlib import Path
import argparse,hashlib,json,shutil
from .network import Network
from .api import default_request
from .training import dump

ROOT=Path(__file__).resolve().parents[1]


def build(include_v6=False,include_v7=False):
    folder=ROOT/'card_eval/models';entries=[]
    for name,source,certificate,description in [
        ('legacy-v3',ROOT/'card_eval/models/shared-policy.npz',ROOT/'card_eval/models/validation.json','旧显式牌组MLP，保留作复核'),
        ('paired-v5',ROOT/'artifacts/card_eval/v5/primary-value.npz',ROOT/'artifacts/card_eval/v5/validation.json','配对终局行动差；补牌背景有局部证据')]+(
        [('memory-v6',ROOT/'artifacts/card_eval/v6/primary-value.npz',ROOT/'artifacts/card_eval/v6/validation.json','己方已知牌组与公开机制记忆；当前基线续局目标')] if include_v6 else [])+(
        [('afterstate-v7',ROOT/'artifacts/card_eval/v7/afterstate-value.npz',ROOT/'artifacts/card_eval/v7/validation.json','冻结V5行动器，动作后局面终局价值；公开搜索须单独实验验证')] if include_v7 else []):
        net,meta=Network.load(source);validation=json.loads(certificate.read_text())
        if validation.get('frozen_policy')!=net.fingerprint:raise ValueError('Certificate does not match frozen model: '+name)
        target=source if name=='legacy-v3' else folder/(name+'.npz')
        if target!=source:
            if target.exists():
                loaded,_=Network.load(target)
                if loaded.fingerprint!=net.fingerprint:raise ValueError('Preserve existing release model instead of replacing weights')
            else:net.save(target,dict(meta,model_name=name,validation=validation))
        entries.append(dict(name=name,file=target.name,description=description,qualified=bool(validation['qualified']),
            status=validation['status'],fingerprint=net.fingerprint,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            source=str(source.relative_to(ROOT)),feature_version=meta['feature_version'],scope='Declared simulator rules and evaluated distributions only; no global card rating.'))
    dump(folder/'registry.json',dict(models=entries,default_policy_mode='declared references',default_experimental_model='paired-v5',quality_gate='Unqualified models require explicit experimental mode.'))
    examples=ROOT/'card_eval/examples';examples.mkdir(exist_ok=True)
    request=default_request(['Bench','Fishing Rod'],samples=8);request['seed_start']=1911000
    dump(examples/'reference-request.json',dict(request,policies=['race','board','guard']))
    dump(examples/'learned-request.json',dict(request,policies=['learned']))
    return entries


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--include-v6',action='store_true');p.add_argument('--include-v7',action='store_true');args=p.parse_args()
    print(json.dumps(build(args.include_v6,args.include_v7),ensure_ascii=False))
