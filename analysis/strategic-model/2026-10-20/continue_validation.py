"""Continue the SAME objective-validation trajectories to real termination.

Prefixes must be replayed to recover hidden state; exact saved results are
checked. They are NOT new independent samples or reruns of older experiments.
No policy is refit and no life/body proxy supplies an unfinished winner.
"""
from pathlib import Path
import gzip,json,subprocess,time
import numpy as np
from model import *
from run import HERE,ROOT,ROWS,COLS
from analyze import paired

DEST=HERE/'objective-validation-v01'


def dump(path,x):path.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')


def run():
    output=DEST/'continuation'
    if output.exists():raise ValueError('Do not overwrite a continuation')
    plan=json.loads((DEST/'plan.json').read_text())
    manifest=json.loads((DEST/'manifest.json').read_text())
    if manifest['status']!='complete':raise ValueError('Complete validated prefixes required')
    paths=[HERE/'continue_validation.py',HERE/'model.py',DEST/'plan.json']
    if subprocess.check_output(['git','status','--porcelain','--',*map(str,paths)],cwd=ROOT,text=True).strip():raise ValueError('Commit the continuation procedure before running')
    commit=subprocess.check_output(['git','log','-1','--format=%H','--',*map(str,paths)],cwd=ROOT,text=True).strip()
    output.mkdir();started=time.monotonic();total=0;summaries=[]
    status=dict(source_commit=commit,prefix_source_commit=manifest['source_commit'],status='running',
        purpose='Resolve unknown tails under unchanged frozen causal policies, without treating finite deadline as the game end',
        independent_new_seeds=0,maximum_own_rounds=40,old_experiments_rerun=0)
    dump(output/'manifest.json',status)
    for world,w in plan['worlds'].items():
        cfg=Config(**w['config']);seeds=plan['seeds'];indices={seed:i for i,seed in enumerate(seeds)}
        data=np.zeros((len(seeds),len(ROWS),3,5));checked=0
        with gzip.open(DEST/f'{world}.jsonl.gz','rt') as src,gzip.open(output/f'{world}.jsonl.gz','wt') as out:
            for line in src:
                prefix=json.loads(line);i,j,seed=prefix['row'],prefix['column'],prefix['seed']
                structure,p=ROWS[i];g=Game(structure,seed,cfg,(p,COLS[j]));r=g.run()
                for k,original in [('a_hp',r['a_hp']),('b_hp',r['b_hp']),('won',r['won']),('lost',r['lost']),('unfinished',r['unfinished']),('life',r['deadline_life_margin'])]:
                    if prefix[k]!=original:raise ValueError(f'Frozen prefix mismatch: {world}/{seed}/{i}/{j}/{k}')
                checked+=1;order=(0,1) if cfg.seat==0 else (1,0)
                n=r['round']
                while min(x.hp for x in g.players)>0 and n<40:
                    n+=1
                    for actor in order:
                        g.act_turn(actor)
                        if min(x.hp for x in g.players)<=0:break
                a,b=g.players;won=b.hp<=0<a.hp;lost=a.hp<=0<b.hp;unresolved=min(a.hp,b.hp)>0
                last_actor=order[0] if g.players[order[0]].turn>g.players[order[1]].turn else order[1]
                loser=0 if a.hp<=0 else 1 if b.hp<=0 else None
                # Under these exact primitive rules own-turn hero death can
                # only be fatigue; opponent-turn death is an attack. This is
                # not a generic Undercards death-cause detector.
                fatigue=loser is not None and loser==last_actor
                data[indices[seed],i,j]=[won,lost,unresolved,fatigue,n]
                row=dict(seed=seed,row=i,column=j,won=won,lost=lost,unfinished=unresolved,
                    round=n,a_hp=a.hp,b_hp=b.hp,cause='unresolved' if unresolved else 'fatigue' if fatigue else 'attack',
                    terminal_at_prefix=not prefix['unfinished'])
                out.write(json.dumps(row,separators=(',',':'))+'\n')
        goals={};samples={}
        for goal,fit in w['fits'].items():
            p=np.asarray(fit['row_mixture']);sample=np.einsum('r,nrck->nck',p,data);samples[goal]=sample
            goals[goal]=[dict(column=COLS[j].name,win=float(v[0]),loss=float(v[1]),unfinished=float(v[2]),fatigue_ending=float(v[3]),mean_round=float(v[4])) for j,v in enumerate(sample.mean(axis=0))]
        effects=[dict(column=COLS[j].name,
            eventual_win_gain=paired(samples['win_by_deadline'][:,j,0]-samples['life'][:,j,0]),
            survival_policy_eventual_win_gain=paired(samples['survive_deadline'][:,j,0]-samples['life'][:,j,0])) for j in range(3)]
        summaries.append(dict(world=world,goals=goals,effects=effects));total+=checked
        print(json.dumps(dict(world=world,checked_prefixes=total,unresolved=int(data[:,:, :,2].sum()),
            win_gain=[round(e['eventual_win_gain']['mean'],3) for e in effects])),flush=True)
    status.update(status='complete',checked_prefixes=total,independent_trajectories=total,elapsed_seconds=time.monotonic()-started)
    dump(output/'manifest.json',status)
    dump(output/'summary.json',dict(source_commit=commit,prefix_source_commit=manifest['source_commit'],results=summaries,
        interpretation='Actual termination under this abstract mechanism set and frozen policy supports. No real-card or full-policy-pool claim; ending mainly by fatigue is an adequacy warning, not an Undercards metagame finding.'))


if __name__=='__main__':run()
