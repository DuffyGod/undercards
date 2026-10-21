"""A new, small validation after the deadline-life proxy failed adequacy.

prepare uses ONLY original training seeds. Commit the resulting plan and code
before run uses fresh30000+ evaluation seeds. No card/transition model changes.
"""
from pathlib import Path
from dataclasses import asdict
import argparse,gzip,json,subprocess,time
import numpy as np
from model import *
from run import HERE,ROOT,ROWS,COLS
from policy_game import solve
from analyze import paired

BASE=HERE/'experiment-v01'
DEST=HERE/'objective-validation-v01'


def dump(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def prepare(dest=DEST):
    if dest.exists():raise ValueError('Do not overwrite a frozen plan')
    m=json.loads((BASE/'manifest.json').read_text());dest.mkdir()
    plan=dict(base_source_commit=m['source_commit'],reason='Deadline-life proxy can prefer an unresolved trajectory over an actual win; test purpose-specific policies on NEW draws',
        seeds=list(range(30000,30128)),worlds={},goals=['life','win_by_deadline','survive_deadline'],
        scope='Internal validation of an objective revision, not a real-game ranking. Eventual-win default remains completion bounds.',
        hypothesis='A single deadline-life proxy is not interchangeable with winning/surviving; changes must generalize to unused seeds. No gain is guaranteed.',
        protocol='Only original train seeds fit mixtures; commit plan and numerical procedure before new draws; evaluate ONLY fixed supports against three timing policies')
    for world,cfg in m['worlds'].items():
        if not(world.startswith('sweep_') or world.startswith('focus_')):continue
        matrices={k:np.zeros((len(ROWS),3)) for k in plan['goals']}
        n=0
        with gzip.open(BASE/f'{world}.jsonl.gz','rt') as f:
            for line in f:
                r=json.loads(line)
                if r['split']!='train' or r['column']>=3:continue
                i,j=r['row'],r['column'];n+=1
                matrices['life'][i,j]+=r['deadline_life_margin']
                matrices['win_by_deadline'][i,j]+=r['won']
                matrices['survive_deadline'][i,j]+=not r['lost']
        if n!=len(m['train_seeds'])*len(ROWS)*3:raise ValueError('Incomplete original training slice')
        fits={k:solve(a/len(m['train_seeds'])) for k,a in matrices.items()}
        support=sorted({i for fit in fits.values() for i,p in enumerate(fit['row_mixture']) if p>1e-9})
        plan['worlds'][world]=dict(config=cfg,fits=fits,support_rows=support)
    dump(dest/'plan.json',plan)
    print(json.dumps(dict(worlds=len(plan['worlds']),new_games=sum(len(w['support_rows'])*3*len(plan['seeds']) for w in plan['worlds'].values()))))


def run(dest=DEST):
    plan=json.loads((dest/'plan.json').read_text())
    if (dest/'manifest.json').exists():raise ValueError('Inspect existing validation; never overwrite/repeat it')
    sources=[HERE/'objective_validation.py',HERE/'model.py',HERE/'policy_game.py',dest/'plan.json']
    if subprocess.check_output(['git','status','--porcelain','--',*map(str,sources)],cwd=ROOT,text=True).strip():raise ValueError('Commit new objective procedure and plan first')
    commit=subprocess.check_output(['git','log','-1','--format=%H','--',*map(str,sources)],cwd=ROOT,text=True).strip()
    manifest=dict(source_commit=commit,base_source_commit=plan['base_source_commit'],status='running',new_games=0,new_api_calls=0)
    dump(dest/'manifest.json',manifest);summaries=[];started=time.monotonic()
    for world,w in plan['worlds'].items():
        cfg=Config(**w['config']);n=len(plan['seeds'])
        data=np.zeros((n,len(ROWS),3,4))
        with gzip.open(dest/f'{world}.jsonl.gz','wt') as f:
            for z,seed in enumerate(plan['seeds']):
                for i in w['support_rows']:
                    s,p=ROWS[i]
                    for j in range(3):
                        r=play(s,seed,cfg,p,COLS[j]);data[z,i,j]=[r['won'],r['lost'],r['unfinished'],r['deadline_life_margin']]
                        f.write(json.dumps(dict(seed=seed,row=i,column=j,won=r['won'],lost=r['lost'],unfinished=r['unfinished'],life=r['deadline_life_margin'],a_hp=r['a_hp'],b_hp=r['b_hp']),separators=(',',':'))+'\n')
                        manifest['new_games']+=1
        results={};samples={}
        for goal,fit in w['fits'].items():
            p=np.asarray(fit['row_mixture']);sample=np.einsum('r,nrck->nck',p,data);samples[goal]=sample
            mean=sample.mean(axis=0)
            results[goal]=dict(mixture=[dict(structure=ROWS[i][0],policy=ROWS[i][1].name,weight=float(x)) for i,x in enumerate(p) if x>1e-9],
                against_timing_policies=[dict(column=COLS[j].name,win=float(v[0]),loss=float(v[1]),unfinished=float(v[2]),life=float(v[3])) for j,v in enumerate(mean)])
        effects=[dict(column=COLS[j].name,win_gain=paired(samples['win_by_deadline'][:,j,0]-samples['life'][:,j,0]),
            loss_change=paired(samples['win_by_deadline'][:,j,1]-samples['life'][:,j,1]),
            survival_gain=paired(samples['life'][:,j,1]-samples['survive_deadline'][:,j,1])) for j in range(3)]
        summaries.append(dict(world=world,goals=results,effects=effects))
        print(json.dumps(dict(world=world,done=manifest['new_games'],effects=[dict(col=e['column'],win_gain=round(e['win_gain']['mean'],3),loss_change=round(e['loss_change']['mean'],3)) for e in effects])),flush=True)
    manifest.update(status='complete',elapsed_seconds=time.monotonic()-started);dump(dest/'manifest.json',manifest)
    dump(dest/'summary.json',dict(source_commit=commit,base_source_commit=plan['base_source_commit'],results=summaries,
        interpretation='Each policy mixture fit before new seeds. Win and survival are different finite-deadline goals; no scalar optimum for eventual real-game strength inferred.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','run']);a=p.parse_args()
    prepare() if a.mode=='prepare' else run()
