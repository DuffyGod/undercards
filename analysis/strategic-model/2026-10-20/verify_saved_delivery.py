"""Read-only delivery verification; no simulation or historical test rerun."""
from pathlib import Path
import gzip,json,re,subprocess,sys
from run import HERE,ROOT


def load(path):return json.loads(path.read_text())


def verify():
    original=HERE/'experiment-v01';fresh=HERE/'objective-validation-v01';tail=fresh/'continuation'
    a,b,c=load(original/'manifest.json'),load(fresh/'manifest.json'),load(tail/'manifest.json')
    assert all(m['status']=='complete' for m in (a,b,c))
    assert a['trajectories']==322560 and b['new_games']==9984 and c['checked_prefixes']==9984
    assert c['independent_new_seeds']==0 and 'independent_trajectories' not in c
    plan=load(fresh/'plan.json')
    seed_sets=[set(a['train_seeds']),set(a['test_seeds']),set(plan['seeds'])]
    assert all(not x&y for i,x in enumerate(seed_sets) for y in seed_sets[i+1:])
    completed=0;terminal_preserved=0;maximum_round=0
    for world in plan['worlds']:
        with gzip.open(fresh/f'{world}.jsonl.gz','rt') as f:
            before={(r['seed'],r['row'],r['column']):r for r in map(json.loads,f)}
        with gzip.open(tail/f'{world}.jsonl.gz','rt') as f:
            for r in map(json.loads,f):
                p=before.pop((r['seed'],r['row'],r['column']))
                assert r['won']+r['lost']+r['unfinished']==1
                assert not r['unfinished'] and r['round']<=40
                if not p['unfinished']:
                    assert r['won']==p['won'] and r['lost']==p['lost'];terminal_preserved+=1
                completed+=1;maximum_round=max(maximum_round,r['round'])
        assert not before
    assert completed==9984
    for file,keys in [(fresh/'summary.json',None),(tail/'summary.json',None)]:
        for world in load(file)['results']:
            for goal,info in world['goals'].items():
                points=info['against_timing_policies'] if isinstance(info,dict) else info
                for p in points:assert abs(sum(p[k] for k in ('win','loss','unfinished'))-1)<1e-8
    audit=load(original/'derived/saved-audit.json')
    assert audit['exact_horizon_prefixes']==23040
    assert sum(x['exact_seed_policy_pairs'] for x in audit['controls'])==15360
    for goal in ('profile','eventual_bounds','final_outcomes'):
        result=subprocess.run([sys.executable,str(HERE/'query.py'),'--goal',goal],capture_output=True,text=True,check=True)
        result=json.loads(result.stdout)
        if goal=='profile':assert result['goal']=='profile' and len(result['rows'])==24
    missing=[]
    for file in (HERE/'README.md',HERE/'REPORT.md',ROOT/'RESEARCH_PRINCIPLES.md'):
        for target in re.findall(r'\]\(([^)#]+)',file.read_text()):
            resolved=file.parent/target
            if resolved==HERE/'verification.json':continue  # emitted below
            if ':' not in target and not resolved.exists():missing.append((str(file),target))
    assert not missing,missing
    receipt=dict(date='2026-10-21',new_simulations_by_this_verifier=0,
        observed_new_model_tests=dict(unique_cases=12,status='passed before formal run',source_commit=a['source_commit']),
        observed_completion_tests=dict(unique_cases=4,status='passed'),
        independent_matrix_self_checks=dict(unique_cases=4,status='reported passed by independent author; finite numerical cases only'),
        original_records=a['trajectories'],new_goal_records=b['new_games'],continued_same_records=completed,
        unique_official_seed_pairs=sum(map(len,seed_sets)),new_seeds_for_continuation=0,
        terminal_prefix_outcomes_preserved=terminal_preserved,maximum_terminal_round=maximum_round,
        previously_saved_control_pairs=15360,previously_saved_horizon_prefixes=23040,
        read_only_query_modes=['profile','eventual_bounds','final_outcomes'],local_document_links='passed',
        old_experiments_rerun=0,new_api_calls=0,
        scope='New abstract research receipts and saved outcome consistency; not current-server rules proof, complete strategy search, or externally calibrated card/deck strength')
    (HERE/'verification.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False,indent=2));return receipt


if __name__=='__main__':verify()
