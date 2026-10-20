"""Frozen-policy evaluation of new abstract trajectories, not old reruns."""
from pathlib import Path
from dataclasses import asdict
import argparse,csv,gzip,json,math
import numpy as np
from model import *
from policy_game import solve
from run import ROWS,COLS,HERE


def paired(xs):
    xs=np.asarray(xs,dtype=float);mean=float(xs.mean())
    se=float(xs.std(ddof=1)/math.sqrt(len(xs))) if len(xs)>1 else 0.
    return dict(mean=mean,approx95=[mean-1.96*se,mean+1.96*se],n=len(xs),
        scope='Paired independent evaluation seeds in this abstract world; exploratory normal interval, no external/model/multiple-selection coverage')


def analyze(path):
    m=json.loads((path/'manifest.json').read_text())
    if m['status']!='complete':raise ValueError('Refuse partial experiment')
    derived=path/'derived';derived.mkdir(exist_ok=True)
    results=[];cells=[];witness_candidates=[]
    for world,config in m['worlds'].items():
        ns={split:len(m[split+'_seeds']) for split in ('train','test')}
        metrics=('life','won','lost','unfinished','punished','wipe','eligible','redeploy2','attack3','burned','held','cash','spent')
        arrays={s:{k:np.zeros((n,len(ROWS),len(COLS))) for k in metrics} for s,n in ns.items()}
        indices={s:{seed:i for i,seed in enumerate(m[s+'_seeds'])} for s in ns}
        snapshots={h:{s:np.zeros((n,len(ROWS),len(COLS))) for s,n in ns.items()} for h in (8,12,16) if h<=config['rounds']}
        seen=set()
        with gzip.open(path/f'{world}.jsonl.gz','rt') as f:
            for line in f:
                r=json.loads(line);split=r['split'];key=(split,r['seed'],r['row'],r['column'])
                if key in seen:raise ValueError('Duplicate seed/row/column')
                seen.add(key);ix=(indices[split][r['seed']],r['row'],r['column'])
                x=arrays[split];t=r['first_punished'];eligible=t>0 and t+3<=config['rounds']
                values=dict(life=r['deadline_life_margin'],won=r['won'],lost=r['lost'],unfinished=r['unfinished'],
                    punished=t>0,wipe=r['first_penalty_wiped'],eligible=eligible,
                    redeploy2=eligible and 0<r['rebuild_deploy']<=t+2,
                    attack3=eligible and 0<r['rebuild_attack']<=t+3,
                    burned=r['a_burned'],held=r['b_held'],cash=r['a_cash'],spent=r['a_total_spent'])
                for k,v in values.items():x[k][ix]=v
                for h,parts in snapshots.items():
                    state=r['snapshots'][min(h,len(r['snapshots']))-1]
                    parts[split][ix]=(max(0,state['a_hp'])-max(0,state['b_hp']))/30
        if len(seen)!=(ns['train']+ns['test'])*len(ROWS)*len(COLS):raise ValueError('Missing matrix trajectories')
        train=arrays['train']['life'].mean(axis=0);test=arrays['test']['life'].mean(axis=0)
        fixed=int(np.argmax(train[:,0]));entry=dict(world=world,config=config,
            fixed_opponent_choice=dict(row=fixed,structure=ROWS[fixed][0],policy=ROWS[fixed][1].name),
            train_matrix=train.tolist(),test_matrix=test.tolist(),comparisons={})
        for pool,columns in (('timing',[0,1,2]),('expanded',list(range(len(COLS))))):
            fit=solve(train[:,columns]);p=np.asarray(fit['row_mixture']);q=np.asarray(fit['col_mixture'])
            counter=columns[int(np.argmin(train[fixed,columns]))]
            b=arrays['test']['life'];robust_samples=np.einsum('r,nrc->nc',p,b)
            expected_matrix=test[:,columns]
            lower=float(np.min(p@expected_matrix));upper=float(np.max(expected_matrix@q))
            effects=dict(
                fixed_vs_immediate=paired(b[:,fixed,0]),
                fixed_vs_frozen_counter=paired(b[:,fixed,counter]),
                counter_cost=paired(b[:,fixed,0]-b[:,fixed,counter]),
                robust_gain_same_counter=paired(robust_samples[:,counter]-b[:,fixed,counter]))
            outcomes={}
            for name,k in (('actual_win_by_deadline','won'),('actual_loss_by_deadline','lost'),('unfinished','unfinished'),
                           ('punished','punished'),('wiped','wipe'),('eligible_recovery_window','eligible'),
                           ('punished_and_redeployed2','redeploy2'),('punished_and_attacked3','attack3'),
                           ('burned_cards','burned'),('opponent_held_turns','held'),('remaining_gold','cash'),('paid_gold','spent')):
                outcomes[name]=float(np.mean(np.einsum('r,nr->n',p,arrays['test'][k][:,:,counter])))
            denom=outcomes['eligible_recovery_window']
            outcomes['redeploy_given_eligible']=None if denom==0 else outcomes['punished_and_redeployed2']/denom
            outcomes['recovery_scope']='All trajectories in joint numerator; conditional rate only eligible first punishment+3turn observation, not a carrying probability or whole-card value'
            info=dict(fit=fit,frozen_counter_column=counter,frozen_counter=COLS[counter].name,effects=effects,
                test_worst_value=lower,test_upper_from_frozen_opponent_mix=upper,test_gap=upper-lower,
                fixed_test_worst_value=float(np.min(test[fixed,columns])),outcomes=outcomes,
                nonzero_rows=[dict(row=i,structure=ROWS[i][0],policy=ROWS[i][1].name,weight=float(w)) for i,w in enumerate(p) if w>1e-9],
                interpretation='Train-selected, seed-independent mixed policy. Bounds/gap refer only to declared pool and empirical matrices, not real-game equilibrium.')
            entry['comparisons'][pool]=info
            # A complete paired witness isolates response timing while holding
            # A fixed. Store no future-aware policy as a valid recommendation.
            if pool=='timing' and counter!=0:
                delta=b[:,fixed,0]-b[:,fixed,counter]
                seed=m['test_seeds'][int(np.argmax(delta))]
                witness_candidates.append((float(delta.max()),world,fixed,counter,seed))
        for i,(s,p) in enumerate(ROWS):
            for j,col in enumerate(COLS):
                cell=dict(world=world,structure=s,row_policy=p.name,column=col.name)
                cell.update({k:float(v[:,i,j].mean()) for k,v in arrays['test'].items()});cells.append(cell)
        entry['horizon_checks']={}
        for h,parts in snapshots.items():
            tr,te=parts['train'].mean(0),parts['test'].mean(0)
            i=int(np.argmax(tr[:,0]));entry['horizon_checks'][h]=dict(fixed_row=i,structure=ROWS[i][0],policy=ROWS[i][1].name,
                test_values=te[i].tolist(),scope='Same trajectories at earlier deadline; earlier selection uses train prefix, not evaluation outcomes')
        # Diagnostic only: clairvoyant selection sees whole hidden outcomes.
        entry['illegal_oracle_diagnostic']=dict(valid_fixed_value=float(test[fixed,0]),
            hidden_world_best_row_value=float(arrays['test']['life'][:,:,0].max(axis=1).mean()),
            warning='Future-aware row choice, deliberately NOT an executable policy or research result recommendation')
        results.append(entry)
    # Full timelines can be replayed without saving millions of action objects.
    # The top timing-cost case is an explanatory witness, not another sample.
    witnesses=[]
    for _,world,i,j,seed in sorted(witness_candidates,reverse=True)[:3]:
        s,row=ROWS[i];cfg=Config(**m['worlds'][world])
        a=play(s,seed,cfg,row,COLS[0],trace=True);b=play(s,seed,cfg,row,COLS[j],trace=True)
        witnesses.append(dict(world=world,seed=seed,row=i,immediate=a,held=b,
            purpose='Selected explanatory paired trace; not an additional or representative probability sample'))
    summary=dict(source_commit=m['source_commit'],status='complete',primary_objective=m['primary_objective'],
        results=results,witnesses=witnesses,old_experiments_rerun=0,new_api_calls=0,
        evidence='Synthetic mechanism-role worlds; withheld shuffles are internal validation, not external Undercards matches')
    (derived/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    with (derived/'cells.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(cells[0]),lineterminator='\n');w.writeheader();w.writerows(cells)
    for r in results:
        c=r['comparisons']['timing'];e=c['effects']
        print(json.dumps(dict(world=r['world'],fixed=r['fixed_opponent_choice'],counter=c['frozen_counter'],
            counter_cost=round(e['counter_cost']['mean'],4),counter95=e['counter_cost']['approx95'],
            robust_gain=round(e['robust_gain_same_counter']['mean'],4),robust=c['nonzero_rows'],
            unfinished=round(c['outcomes']['unfinished'],3)),ensure_ascii=False),flush=True)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',type=Path,default=HERE/'experiment-v01')
    analyze(p.parse_args().experiment)
