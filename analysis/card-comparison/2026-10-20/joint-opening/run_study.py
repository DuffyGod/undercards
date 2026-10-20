"""New randomized causal rollouts only. Append/checkpoint groups; never overwrite.

Each group uses the same seed range; immutable entity positions pair deck edits.
Rates apply only to the declared shuffle, composition and policy hypotheses.
"""
from dataclasses import asdict,replace
from itertools import product
from pathlib import Path
from collections import Counter
import argparse,gzip,json,time,subprocess
from model import *

OPPONENTS={'mid':('middle','INTEGRITY','balanced'),
           'large_reply':('heavy','KINDNESS','balanced'),
           'draw_reply':('middle_draw','KINDNESS','balanced')}

def dump(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def groups(stage):
    if stage=='pilot':
        return [dict(composition=c,policy=p,soul='KINDNESS',opponent=o,seat=s,intervention='base')
                for c,p,o,s in product(('small_draw','middle_draw','heavy'),('pressure','balanced'),('large_reply',),(0,1))]
    if stage=='main':
        return [dict(composition=c,policy=p,soul=so,opponent=o,seat=s,intervention='base')
                for c,p,so,o,s in product(('small','small_draw','middle','middle_draw','heavy'),
                    ('pressure','balanced'),('INTEGRITY','KINDNESS'),('mid','large_reply'),(0,1))]
    if stage=='counterfactual':
        # Intervention cells share exact deck entity order, not merely RNG seed.
        return [dict(composition=c,policy=p,soul='KINDNESS',opponent='large_reply',seat=s,intervention=i)
                for c,p,s,i in product(('small_draw','middle_draw'),('balanced','reserve_slot'),(0,1),
                    ('base','no_bonus_draw','extra_natural','hand10','slots6','no_foe_hero_heal','hp_loss','soul_first','no_t1_draw'))]
    if stage=='heal':
        return [dict(composition=c,policy='balanced',soul='KINDNESS',opponent=o,seat=s,intervention='base')
                for c,o,s in product(('middle_draw','middle_heal'),('mid','large_reply','draw_reply'),(0,1))]
    raise ValueError(stage)


def configuration(g,horizon):
    cfg=Config(horizon=horizon)
    i=g['intervention']
    kw={'base':{},'no_bonus_draw':dict(bonus_draw=False),'extra_natural':dict(extra_natural_draw=1),
        'hand10':dict(hand_cap=10),'slots6':dict(slots=6),
        'no_foe_hero_heal':dict(hero_healing=tuple(s==g['seat'] for s in (0,1))),
        'hp_loss':dict(knight_damage='hp_loss'),'soul_first':dict(end_order='soul_then_draw'),
        'no_t1_draw':dict(first_turn_draw=False)}[i]
    return replace(cfg,**kw)


def trial(g,seed,horizon,trace=False):
    other,other_soul,other_policy=OPPONENTS[g['opponent']];side=g['seat']
    decks=[COMPOSITIONS[other]]*2;souls=[other_soul]*2;policies=[other_policy]*2
    decks[side]=COMPOSITIONS[g['composition']];souls[side]=g['soul'];policies[side]=g['policy']
    r=Match(tuple(decks),tuple(souls),tuple(policies),seed,configuration(g,horizon),trace).run()
    return dict(seed=seed,**g,**r)


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--stage',choices=('pilot','main','counterfactual','heal'),required=True)
    a.add_argument('--output',type=Path,required=True);a.add_argument('--samples',type=int,default=128)
    a.add_argument('--horizon',type=int,default=8);a.add_argument('--seed-start',type=int,default=0)
    a.add_argument('--resume',action='store_true');args=a.parse_args()
    out=args.output
    if out.exists() and any(out.iterdir()) and not args.resume:raise ValueError('Refusing overwrite')
    out.mkdir(parents=True,exist_ok=True)
    gs=groups(args.stage)
    # Source must be committed before formal results claim a source revision.
    if args.stage!='pilot':
        source_paths=[str(HERE/x) for x in ('model.py','run_study.py')]
        for src in source_paths:
            subprocess.check_call(['git','ls-files','--error-unmatch',src],cwd=ROOT,stdout=subprocess.DEVNULL)
        if subprocess.check_output(['git','diff','HEAD','--',*source_paths],cwd=ROOT,text=True):
            raise ValueError('Commit model and runner before formal experiments')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    spec=dict(version=VERSION,source_commit=revision,stage=args.stage,samples=args.samples,
        horizon=args.horizon,seed_start=args.seed_start,groups=gs,
        compositions={k:[dict(slot=i,cid=cid,name=CARDS[cid]['name'],cost=CARDS[cid]['cost']) for i,cid in enumerate(v)] for k,v in COMPOSITIONS.items()},
        opponents=OPPONENTS,policy_parameters=dict(face_price_pressure=1,face_price_balanced=.25,
            gold_price_pressure=.25,gold_price_balanced=.5,hand_price_low=.5,hand_price_other=.1,draw_price=.6),
        default_config=asdict(Config(horizon=args.horizon)),
        interpretation='Uniform shuffles of these legal compositions and causal heuristics only; no real ladder frequencies, no optimized decks.',
        assumptions=['no mulligan','initial 3; t1 draw is unverified convention',
            'no artifacts','restricted implemented card pool','ordinary attacks chosen by declared one-turn heuristic, not future minimax',
            'Kindness/turn-end draw ordering unverified if fatigue occurs','Knight overkill packet default, alternate hp_loss',
            'global cutoff after both nth turns; seats must remain separate'])
    if (out/'design.json').exists():
        old=json.loads((out/'design.json').read_text())
        # A resume cannot silently change source/model/spec.
        if old!=spec:raise ValueError('Resume design mismatch')
    else:dump(out/'design.json',spec)
    started=time.time();done=[];fail=[]
    for idx,g in enumerate(gs):
        path=out/f'group-{idx:03d}.jsonl.gz'
        if path.exists():
            rows=[json.loads(line) for line in gzip.open(path,'rt')]
            if len(rows)!=args.samples:raise ValueError('Incomplete prior group; preserve and investigate')
            done.append(idx);continue
        rows=[]
        for seed in range(args.seed_start,args.seed_start+args.samples):
            try:rows.append(trial(g,seed,args.horizon))
            except Exception as e:
                failure=dict(group=idx,seed=seed,config=g,error=repr(e))
                fail.append(failure)
                dump(out/'failures.json',fail)
                raise
        with gzip.open(path,'wt',encoding='utf-8') as f:
            for row in rows:f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
        done.append(idx)
        dump(out/'receipt.json',dict(version=VERSION,source_commit=revision,completed_groups=done,
            trials=len(done)*args.samples,failed=fail,elapsed_seconds=time.time()-started,complete=len(done)==len(gs)))
        if idx%8==0 or len(done)==len(gs):print(f'{args.stage}: {len(done)}/{len(gs)} groups, {len(done)*args.samples} matches, {time.time()-started:.1f}s',flush=True)

if __name__=='__main__':main()
