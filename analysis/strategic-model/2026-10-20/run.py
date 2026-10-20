"""Freeze/run a new, bounded strategic abstraction experiment.

Seed-level outputs are preserved in Git-compressible JSONL. No old experiment
is rerun, and no simulation number is interpreted as an accuracy percentage.
"""
from pathlib import Path
from dataclasses import asdict,replace
import argparse,gzip,json,subprocess,time
from model import *

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ROWS=[(s,p) for s in ('wide','anchor','refill','recovery') for p in ROW_POLICIES]
COLS=list(COL_POLICIES)


def worlds():
    ws={}
    for shape in ('sweep','focus'):
        for soul in ('INTEGRITY','KINDNESS'):
            for seat in (0,1):
                ws[f'{shape}_{soul.lower()}_seat{seat}']=Config(response_kind=shape,soul=soul,seat=seat)
    base=Config()
    ws.update(no_response=replace(base,responses_enabled=False),unfunded_response=replace(base,response_cost=1000),
        weak_packet=replace(base,response_damage=1),strong_packet=replace(base,response_damage=8),
        no_first_draw=replace(base,first_draw=False),longer_horizon=replace(base,rounds=16))
    return ws


def provenance():
    paths=[HERE/n for n in ('model.py','run.py','policy_game.py','PROTOCOL.md')]
    dirty=subprocess.check_output(['git','status','--porcelain','--',*map(str,paths)],cwd=ROOT,text=True).strip()
    if dirty:raise ValueError('Commit protocol and numeric source before formal execution; no overwrite/rerun workaround')
    return subprocess.check_output(['git','log','-1','--format=%H','--',*map(str,paths)],cwd=ROOT,text=True).strip()


def run(out,train=64,test=128,selected=None):
    source=provenance()
    if out.exists():raise ValueError('Frozen experiment directory exists; inspect/reuse it instead of rerunning')
    out.mkdir(parents=True)
    ws=worlds()
    if selected:ws={k:ws[k] for k in selected}
    manifest=dict(version=VERSION,source_commit=source,train_seeds=list(range(10000,10000+train)),
        test_seeds=list(range(20000,20000+test)),worlds={k:asdict(v) for k,v in ws.items()},
        rows=[dict(structure=s,policy=asdict(p)) for s,p in ROWS],columns=[asdict(p) for p in COLS],
        primary_objective='(max(0,A_HP)-max(0,B_HP))/30 at declared deadline; NOT eventual win probability',
        timing_columns=[0,1,2],expanded_columns=list(range(len(COLS))),
        hypotheses='PROTOCOL.md',status='running',new_api_calls=0,
        uncertainty='Within this abstract environment; seeds reused across rows/cols/worlds, not independent game samples')
    def save():(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    save();started=time.monotonic();n=0
    try:
        for name,cfg in ws.items():
            world_start=time.monotonic()
            with gzip.open(out/f'{name}.jsonl.gz','wt',encoding='utf8') as f:
                for split,seeds in (('train',manifest['train_seeds']),('test',manifest['test_seeds'])):
                    for seed in seeds:
                        for i,(s,row) in enumerate(ROWS):
                            for j,col in enumerate(COLS):
                                r=play(s,seed,cfg,row,col)
                                if r['a_cash']!=1+r['a_income']+r['a_bonus_gold']-r['a_total_spent']:raise ValueError('Cash accounting mismatch')
                                if r['a_deck']+r['a_hand']+r['a_played']+r['a_burned']!=25:raise ValueError('Card accounting mismatch')
                                # These identities reproduce the entire trajectory
                                # using committed source; omit repeated metadata.
                                for key in ('config','structure','row_policy','col_policy','trace'):r.pop(key)
                                r.update(split=split,row=i,column=j)
                                f.write(json.dumps(r,separators=(',',':'))+'\n');n+=1
            print(json.dumps(dict(world=name,completed=n,world_seconds=round(time.monotonic()-world_start,2))),flush=True)
        manifest.update(status='complete',trajectories=n,elapsed_seconds=time.monotonic()-started)
    except Exception as e:
        manifest.update(status='failed',completed_before_failure=n,error_type=type(e).__name__,error=str(e));save();raise
    save()
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=HERE/'experiment-v01')
    p.add_argument('--train',type=int,default=64);p.add_argument('--test',type=int,default=128)
    p.add_argument('--worlds',nargs='*');a=p.parse_args()
    run(a.out,a.train,a.test,a.worlds)
