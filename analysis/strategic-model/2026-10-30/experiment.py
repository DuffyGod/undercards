"""Fit on new training deals; freeze mixtures before evaluating new deals.

This is a conditional real-body insertion in an abstract host, never a legal
whole-deck certification or an environment-averaged real-card ranking.
"""
from dataclasses import asdict
from pathlib import Path
import argparse,csv,gzip,json,subprocess,time,math
import numpy as np
from engine import *
from policy_game import solve

ROOT=HERE.parents[2]
OUT=HERE/'experiment-v01'


def dump(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def worlds():
    out={}
    for kind in ('sweep','focus'):
        for seat in (0,1):out[f'{kind}_integrity_seat{seat}']=Config(rounds=40,response_kind=kind,seat=seat)
        out[f'{kind}_kindness_seat0']=Config(rounds=40,response_kind=kind,soul='KINDNESS')
    return out


def provenance():
    sources=[HERE/n for n in ('engine.py','tactics.py','experiment.py','PROTOCOL.md','real-bodies.json')]+[BASE/'model.py',BASE/'policy_game.py']
    if subprocess.check_output(['git','status','--porcelain','--',*map(str,sources)],cwd=ROOT,text=True).strip():
        raise ValueError('Commit protocol and numeric source before official execution')
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def simulate(world,structure,body,seed,row,col,trace=False):
    g=BridgeGame(structure,seed,world,(ROWS[row],COLS[col]),body,trace=trace)
    r=g.run()
    for a in g.players:
        assert a.cash==1+a.income+a.bonus_gold-a.total_spent
        assert len(a.deck)+len(a.hand)+a.played+a.burned==25
    if r['unfinished']:raise ValueError('Unresolved at40; preserve failure, do not guess winner')
    if r['won']+r['lost']!=1:raise ValueError('Unexpected tied terminal; revise explicit utility before use')
    keep=('seed','won','lost','round','a_hp','b_hp','a_draws','a_burned','a_cash','a_units','a_hand',
          'candidate_drawn','candidate_played','candidate_first_turn','candidate_wait','candidate_burned',
          'candidate_unfunded_turns','candidate_slot_blocked_turns','candidate_held','first_punished')
    record={k:r[k] for k in keep};record.update(row=row,column=col)
    if trace:record['trace']=r['trace']
    return record


def pilot():
    dest=HERE/'pilot.json'
    if dest.exists():raise ValueError('Reuse pilot; no repeat for counter filling')
    start=time.monotonic();rows=[]
    for name,cfg in worlds().items():
        for body in ('Rock Pet','Aaron'):
            for seed in (920000,920001):
                for row in range(len(ROWS)):
                    for col in range(len(COLS)):
                        r=simulate(cfg,'wide',bodies()[body],seed,row,col)
                        rows.append(dict(world=name,body=body,**r))
    result=dict(base_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        numeric_source='uncommitted development source at pilot time; official source frozen separately',
        purpose='Runtime, legality/accounting and terminal checks only; no selection from pilot results',
        elapsed_seconds=time.monotonic()-start,records=rows)
    dump(dest,result);print(json.dumps(dict(records=len(rows),seconds=result['elapsed_seconds'])))


def train():
    source=provenance()
    if OUT.exists():raise ValueError('Existing experiment cannot be overwritten')
    OUT.mkdir()
    manifest=dict(status='running',source_commit=source,version=VERSION,worlds={k:asdict(v) for k,v in worlds().items()},
        structures=['wide','anchor'],bodies={k:asdict(v) for k,v in bodies().items()},copies=3,
        rows=[asdict(p) for p in ROWS],columns=[asdict(p) for p in COLS],
        train_seeds=list(range(40000,40048)),eval_seeds=list(range(50000,50128)),
        split_explanation='Never used in older experiments; same entity order across body/policy counterfactuals. 48 training and128 evaluation seed pairs, not raw-record count independent samples.',
        objective='Actual A win under abstract rules through HP terminal, max40; unresolved is hard failure, not imputed',
        new_api_calls=0,completed_records=0)
    dump(OUT/'manifest.json',manifest);started=time.monotonic()
    try:
        for name,world in worlds().items():
            with gzip.open(OUT/f'train-{name}.jsonl.gz','wt') as f:
                for structure in manifest['structures']:
                    for body in bodies().values():
                        for seed in manifest['train_seeds']:
                            for row in range(len(ROWS)):
                                for col in range(len(COLS)):
                                    r=simulate(world,structure,body,seed,row,col)
                                    r.update(structure=structure,body=body.name)
                                    f.write(json.dumps(r,separators=(',',':'))+'\n');manifest['completed_records']+=1
            dump(OUT/'manifest.json',manifest)
            print(json.dumps(dict(world=name,records=manifest['completed_records'],seconds=round(time.monotonic()-started,1))),flush=True)
        manifest.update(status='train_complete',elapsed_seconds=time.monotonic()-started)
    except Exception as e:
        manifest.update(status='failed',error=repr(e));dump(OUT/'manifest.json',manifest);raise
    dump(OUT/'manifest.json',manifest)


def prepare():
    m=json.loads((OUT/'manifest.json').read_text())
    if m['status']!='train_complete':raise ValueError('Need complete training')
    if (OUT/'plan.json').exists():raise ValueError('Do not replace frozen policy choices')
    cases=[]
    for name in m['worlds']:
        matrices={(s,b):np.zeros((len(ROWS),len(COLS))) for s in m['structures'] for b in m['bodies']}
        count=0
        with gzip.open(OUT/f'train-{name}.jsonl.gz','rt') as f:
            for r in map(json.loads,f):matrices[r['structure'],r['body']][r['row'],r['column']]+=r['won'];count+=1
        assert count==len(matrices)*len(m['train_seeds'])*len(ROWS)*len(COLS)
        for (s,b),matrix in matrices.items():
            matrix/=len(m['train_seeds']);fit=solve(matrix)
            support=sorted({0,1}|{i for i,p in enumerate(fit['row_mixture']) if p>1e-9})
            cases.append(dict(world=name,structure=s,body=b,train_matrix=matrix.tolist(),fit=fit,eval_rows=support))
    dump(OUT/'plan.json',dict(source_commit=m['source_commit'],cases=cases,eval_seeds=m['eval_seeds'],
        selection='Finite row/column maximin win-rate mixture fit ONLY on training; always evaluate greedy and attack-only frontier rows for matched policy adequacy diagnostics. No new-evaluation sorting as validation.'))
    print(json.dumps(dict(cases=len(cases),evaluation_records=sum(len(c['eval_rows'])*len(COLS)*len(m['eval_seeds']) for c in cases))))


def evaluate():
    source=provenance();plan_path=OUT/'plan.json'
    if subprocess.check_output(['git','status','--porcelain','--',str(plan_path)],cwd=ROOT,text=True).strip():raise ValueError('Commit plan before new evaluation')
    if (OUT/'evaluation-manifest.json').exists():raise ValueError('Never overwrite/repeat evaluation')
    plan=json.loads(plan_path.read_text());m=json.loads((OUT/'manifest.json').read_text())
    status=dict(status='running',source_commit=source,training_source_commit=m['source_commit'],completed_records=0)
    dump(OUT/'evaluation-manifest.json',status);started=time.monotonic()
    try:
        for name,config in m['worlds'].items():
            with gzip.open(OUT/f'eval-{name}.jsonl.gz','wt') as f:
                for case in (c for c in plan['cases'] if c['world']==name):
                    for seed in plan['eval_seeds']:
                        for row in case['eval_rows']:
                            for col in range(len(COLS)):
                                r=simulate(Config(**config),case['structure'],Body(**m['bodies'][case['body']]),seed,row,col)
                                r.update(structure=case['structure'],body=case['body'])
                                f.write(json.dumps(r,separators=(',',':'))+'\n');status['completed_records']+=1
            dump(OUT/'evaluation-manifest.json',status)
            print(json.dumps(dict(world=name,records=status['completed_records'],seconds=round(time.monotonic()-started,1))),flush=True)
        status.update(status='complete',elapsed_seconds=time.monotonic()-started)
    except Exception as e:
        status.update(status='failed',error=repr(e));dump(OUT/'evaluation-manifest.json',status);raise
    dump(OUT/'evaluation-manifest.json',status)


def paired(xs):
    a=np.asarray(xs,float);mean=float(a.mean());se=float(a.std(ddof=1)/math.sqrt(len(a)))
    return dict(mean=mean,approx95=[mean-1.96*se,mean+1.96*se],n=len(a),
        scope='Exploratory paired normal interval for frozen mixtures; does not cover model error, multiple comparisons, or environment frequencies')


def analyze():
    m=json.loads((OUT/'manifest.json').read_text());plan=json.loads((OUT/'plan.json').read_text())
    ev=json.loads((OUT/'evaluation-manifest.json').read_text())
    if ev['status']!='complete':raise ValueError('Incomplete evaluation')
    metrics=['won','candidate_drawn','candidate_played','candidate_wait','candidate_unfunded_turns',
             'candidate_slot_blocked_turns','candidate_burned','candidate_held','a_burned','round']
    results=[];effects=[];seed_samples={};n=len(plan['eval_seeds']);index={s:i for i,s in enumerate(plan['eval_seeds'])}
    for world in m['worlds']:
        cases=[c for c in plan['cases'] if c['world']==world]
        data={(c['structure'],c['body']):np.full((n,len(ROWS),len(COLS),len(metrics)),np.nan) for c in cases}
        with gzip.open(OUT/f'eval-{world}.jsonl.gz','rt') as f:
            for r in map(json.loads,f):
                z=(index[r['seed']],r['row'],r['column']);arr=data[r['structure'],r['body']]
                assert np.isnan(arr[z][0]),'Duplicate result';arr[z]=[r[k] for k in metrics]
        for c in cases:
            arr=data[c['structure'],c['body']];p=np.asarray(c['fit']['row_mixture']);support=np.flatnonzero(p>1e-9)
            assert not np.isnan(arr[:,c['eval_rows']]).any()
            mixed=np.einsum('r,nrcm->ncm',p[support],arr[:,support]);greedy=arr[:,0];attack_only=arr[:,1]
            seed_samples[world,c['structure'],c['body']]=mixed
            results.append(dict(world=world,structure=c['structure'],body=c['body'],
                mixture=[dict(policy=ROWS[i].name,weight=float(p[i])) for i in support],
                training_guarantee=c['fit']['value'],
                against=[dict(column=COLS[j].name,win=float(mixed[:,j,0].mean()),
                    win_interval=paired(mixed[:,j,0]),greedy_win=float(greedy[:,j,0].mean()),
                    policy_gain=paired(mixed[:,j,0]-greedy[:,j,0]),
                    attack_only_win=float(attack_only[:,j,0].mean()),attack_only_gain=paired(attack_only[:,j,0]-greedy[:,j,0]),
                    diagnostics={k:float(mixed[:,j,i].mean()) for i,k in enumerate(metrics) if i}) for j in range(len(COLS))]))
    comparisons=[('Rock Pet','Froggit'),('Rock Pet','Moldsmal'),('Candy Dish','Rock Pet'),('Aaron','Rock Pet'),
        ('Candy_cost2','Candy Dish'),('Aaron_cost2','Aaron'),('Rock_health4','Rock Pet')]
    for world in m['worlds']:
        for s in m['structures']:
            for a,b in comparisons:
                for j,col in enumerate(COLS):
                    effects.append(dict(world=world,structure=s,a=a,b=b,column=col.name,
                        win_difference=paired(seed_samples[world,s,a][:,j,0]-seed_samples[world,s,b][:,j,0])))
    result=dict(training_source=m['source_commit'],evaluation_source=ev['source_commit'],metrics=metrics,results=results,comparisons=effects,
        interpretation='Frozen policy comparisons of3 named ordinary bodies inserted into aggregate role hosts. All counts include no-draw, no-play and terminal failures. No tribal interactions, full actual deck, unmodeled common abilities, external calibration or universal card rank.')
    dump(OUT/'summary.json',result)
    with (OUT/'comparison.csv').open('w') as f:
        keys=['world','structure','a','b','column','difference','low','high']
        writer=csv.DictWriter(f,keys,lineterminator='\n');writer.writeheader()
        for e in effects:
            v=e['win_difference'];writer.writerow({k:e[k] for k in keys[:5]}|dict(difference=v['mean'],low=v['approx95'][0],high=v['approx95'][1]))
    print(json.dumps(dict(conditions=len(results),paired_comparisons=len(effects))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['pilot','train','prepare','evaluate','analyze']);args=p.parse_args()
    globals()[args.mode]()
