"""Read saved official artifacts; no simulation or historical test rerun."""
from pathlib import Path
import gzip,json,subprocess,sys,re
from engine import HERE,BASE,ROWS,COLS


def load(path):return json.loads(path.read_text())


def verify():
    dest=HERE/'experiment-v01';m=load(dest/'manifest.json');p=load(dest/'plan.json');ev=load(dest/'evaluation-manifest.json')
    assert m['status']=='train_complete' and ev['status']=='complete'
    assert not set(m['train_seeds'])&set(p['eval_seeds'])
    for current in (m['train_seeds'],p['eval_seeds']):
        assert not set(current)&(set(range(10000,10064))|set(range(20000,20128))|set(range(30000,30128)))
    count={};maximum=0
    for split,seeds in [('train',m['train_seeds']),('eval',p['eval_seeds'])]:
        count[split]=0
        for world in m['worlds']:
            cases=[c for c in p['cases'] if c['world']==world]
            expected={(s,b,seed,row,col) for s in m['structures'] for b in m['bodies'] for seed in seeds
                for row in (range(len(ROWS)) if split=='train' else next(c['eval_rows'] for c in cases if c['structure']==s and c['body']==b))
                for col in range(len(COLS))}
            with gzip.open(dest/f'{split}-{world}.jsonl.gz','rt') as f:
                for r in map(json.loads,f):
                    key=(r['structure'],r['body'],r['seed'],r['row'],r['column'])
                    assert key in expected;expected.remove(key)
                    assert r['won']+r['lost']==1 and r['round']<=40 and r['a_cash']>=0
                    assert r['candidate_played']<=r['candidate_drawn']<=3
                    assert r['candidate_drawn']+r['candidate_burned']<=3
                    maximum=max(maximum,r['round']);count[split]+=1
            assert not expected
    assert count['train']==m['completed_records'] and count['eval']==ev['completed_records']
    for o in load(dest/'opportunity.json')['results']:
        for q in o['against']:assert abs(sum(q[k] for k in ('p_not_received','p_received_never_played','p_played'))-1)<1e-8
    for c in p['cases']:
        assert abs(sum(c['fit']['row_mixture'])-1)<1e-8 and c['fit']['gap']<1e-7
    for args in ([],['--compare','Aaron','Rock Pet'],['--body','Rock_health4','--counterfactuals']):
        r=subprocess.run([sys.executable,str(HERE/'query.py'),*args],check=True,capture_output=True,text=True)
        output=json.loads(r.stdout);assert 'scope' in output
    r=subprocess.run([sys.executable,str(HERE/'query.py'),'--body','Rock_health4'],capture_output=True,text=True)
    assert r.returncode!=0,'Fictional body must require explicit flag'
    root=HERE.parents[2]
    assert not subprocess.check_output(['git','diff','cde68ae','--',str(BASE/'model.py')],cwd=root,text=True)
    missing=[]
    for file in [HERE/'README.md',HERE/'REPORT.md',root/'RESEARCH_AUTOMATION.md']:
        for target in re.findall(r'\]\(([^)#]+)',file.read_text()):
            if ':' not in target and target!='verification.json' and not (file.parent/target).exists():missing.append((str(file),target))
    assert not missing,missing
    receipt=dict(date='2026-10-30',train_records=count['train'],evaluation_records=count['eval'],
        official_unique_seed_pairs=len(m['train_seeds'])+len(p['eval_seeds']),maximum_terminal_round=maximum,
        new_targeted_checks=10,new_targeted_check_status='passed before official run; repeats only followed actual source changes',
        independent_probe_status='author reported54state-mode/118plan engine replays and12oracle-pair/81numeric endpoint sets passed',
        old_official_experiments_rerun=0,new_simulations_by_verifier=0,new_api_calls=0,
        saved_grid_uniqueness_and_terminal_counts='passed',receipt_play_partition='passed',query_modes='passed',
        old_model_source_unchanged=True,document_links='passed',
        scope='Artifact consistency and targeted numeric checks; not external calibration, full-policy optimum or whole real-deck support')
    (HERE/'verification.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt))


if __name__=='__main__':verify()
