"""Read-only V13 audit of coupled targets, stopping roots and development."""
from collections import Counter,defaultdict
from pathlib import Path
import argparse,json
import numpy as np
from .policy_iteration import (BASE,INITIAL,design,read_rows,donor_episodes,root_turns,stopping_indices,
                               collection_summary,dataset,target_metrics)
from .network import Network
from .policies import LearnedPolicy
from .regret_model import RegretNetwork
from .suffix_research import cases
from .action_value import encode
from .statistics import interval
from .training import dump,commit


def audit(folder):
    d=design(folder);base=Network.load(BASE)[0];initial=Network.load(INITIAL)[0];checks=Counter();failures=[]
    for phase in (0,1):
        if not (folder/f'phase{phase}-fit.json').exists():continue
        current=initial if phase==0 else Network.load(folder/'phase0-selected.npz')[0]
        targets={'initial':initial} if phase==0 else {'updated':current,'frozen':initial}
        for stage in ('train','diagnostic'):
            donors={m['seed']:(m,rows,r) for m,rows,r in donor_episodes(stage,d['donor_'+stage+'_seeds'])} if phase==0 else {}
            seeds=[]
            for path in sorted((folder/f'p{phase}-{stage}').glob('episode-*.jsonl.gz')):
                records=list(read_rows(path));meta=records[0];seeds.append(meta['seed'])
                assert meta['actor_fingerprint']==current.actor_fingerprint
                if phase==0:
                    old,rows,result=donors[meta['seed']]
                    assert old['decks']==meta['decks'] and old['souls']==meta['souls']
                else:
                    rows=[r for r in records if r['record_type']=='decision']
                    result=next(r['result'] for r in records if r['record_type']=='outcome')
                roots=[r for r in records if r['record_type']=='root']
                assert [r['decision'] for r in roots]==stopping_indices(rows,root_turns(meta['seed'],d['rng_seed']))
                selection=next(r for r in records if r['record_type']=='root_selection')
                assert selection['forks']==[r['decision'] for r in roots] and selection['rollin_unknown']==result['unfinished']
                for r in roots:
                    obs=r['observation'];actions=list(map(tuple,r['legal_actions']));source=rows[r['decision']]
                    assert source['observation']==obs and list(map(tuple,source['legal_actions']))==actions
                    assert r['rollin_choice']==source['selection']['action_index']==LearnedPolicy(current).choose(obs,actions)['action_index']
                    assert r['anchor']==LearnedPolicy(base).choose(obs,actions)['action_index']
                    assert {0,r['anchor'],r['rollin_choice']}<=set(r['sampled_actions'])
                    assert len(r['sampled_actions'])<=6 and len(set(r['sampled_actions']))==len(r['sampled_actions'])
                    assert {(c['target'],c['action_index']) for c in r['cells']}=={(t,i) for t in targets for i in r['sampled_actions']}
                    for c in r['cells']:
                        assert c['continuation_actor']==targets[c['target']].actor_fingerprint
                        assert c['reused']==(targets[c['target']].actor_fingerprint==current.actor_fingerprint and c['action_index']==r['rollin_choice'])
                        assert c['prefix_checked'] or c['result']['unfinished']
                        if c['reused']:
                            assert all(c['result'].get(k)==v for k,v in result.items())
                            assert set(c['result'])-set(result)<={'souls'}
                        if c['result']['unfinished']:
                            assert c['result']['won'] is None
                            failures.append(dict(phase=phase,stage=stage,file=str(path),seed=meta['seed'],decision=r['decision'],
                                action_index=c['action_index'],target=c['target'],reused=c['reused'],error=c['result'].get('error')))
                        checks['cells']+=1
                    checks['roots']+=1
                checks['openings']+=1
            assert seeds==d[('donor_' if phase==0 else '')+stage+'_seeds']
            summary=collection_summary(folder/f'p{phase}-{stage}');saved=json.loads((folder/f'p{phase}-{stage}-collection.json').read_text())
            assert all(saved[k]==v for k,v in summary.items())
        fit=json.loads((folder/f'phase{phase}-fit.json').read_text())
        assert fit['selection']==d['selection']
        for target in targets:
            arm=fit['arms'][target]
            assert arm['epochs']==64 and arm['optimizer_steps']==64*int(np.ceil(arm['training_roots']/d['batch']))
            if phase==1:assert arm['warm_start_actor']==Network.load(folder/'phase0-selected.npz')[0].actor_fingerprint
            train=dataset(folder,phase,'train',target);diagnostic=dataset(folder,phase,'diagnostic',target)
            for point in arm['curve']:
                net,meta=Network.load(folder/f"phase{phase}-{target}-epoch-{point['epoch']:03}.npz")
                assert meta['value_unfitted'] and not meta['validation']['qualified']
                assert point['train']==target_metrics(net,train) and point['diagnostic']==target_metrics(net,diagnostic)
            file='phase0-selected.npz' if phase==0 else f'{target}-selected.npz'
            selected=Network.load(folder/file)[0];last=Network.load(folder/f'phase{phase}-{target}-epoch-064.npz')[0]
            assert selected.fingerprint==last.fingerprint==net.fingerprint
            assert selected.actor_fingerprint==arm['actor_fingerprint']
            checks['fixed_checkpoints']+=len(arm['curve'])
    if (folder/'phase1-fit.json').exists():
        fit=json.loads((folder/'phase1-fit.json').read_text());a=fit['arms']['updated'];b=fit['arms']['frozen']
        assert (a['warm_start_actor'],a['parameters'],a['optimizer_steps'],a['training_roots'])==(b['warm_start_actor'],b['parameters'],b['optimizer_steps'],b['training_roots'])
        for stage in ('train','diagnostic'):
            a=dataset(folder,1,stage,'updated');b=dataset(folder,1,stage,'frozen')
            assert np.array_equal(a['x'],b['x']) and np.array_equal(a['groups'],b['groups']) and a['anchors']==b['anchors'] and a['weights']==b['weights']
        common=dataset(folder,1,'diagnostic','updated')
        for name,file in (('updated','updated-selected.npz'),('frozen','frozen-selected.npz'),('phase0','phase0-selected.npz')):
            assert fit['arms']['common_current_target_diagnostic'][name]==target_metrics(Network.load(folder/file)[0],common)
        signal={}
        for stage in ('train','diagnostic'):
            counter=Counter()
            for path in sorted((folder/f'p1-{stage}').glob('episode-*.jsonl.gz')):
                for root in read_rows(path):
                    if root['record_type']!='root':continue
                    labels={target:{c['action_index']:int(c['result']['won']) for c in root['cells']
                        if c['target']==target and not c['result']['unfinished']} for target in ('updated','frozen')}
                    both=sorted(set(labels['updated'])&set(labels['frozen']));changed=False
                    for j,i in enumerate(both):
                        for k in both[j+1:]:
                            a=labels['updated'][i]-labels['updated'][k];b=labels['frozen'][i]-labels['frozen'][k]
                            counter['known_action_pairs']+=1;counter['changed_contrasts']+=a!=b;changed|=a!=b
                    counter['roots']+=1;counter['roots_with_changed_contrasts']+=changed
            signal[stage]=dict(counter)
        a=dataset(folder,1,'train','updated');b=dataset(folder,1,'train','frozen');mask=np.isfinite(a['y'])&np.isfinite(b['y'])
        ya=np.where(mask,a['y'],np.nan);yb=np.where(mask,b['y'],np.nan)
        weights={g:w for g,w in a['weights'].items() if np.any(mask[a['groups']==g])};total=sum(weights.values())
        weights={g:w/total for g,w in weights.items()};warm=Network.load(folder/'phase0-selected.npz')[0]
        ga=warm.loss_grad(a['x'],ya,a['groups'],a['anchors'],weights,d['l2'])[1]
        gb=warm.loss_grad(b['x'],yb,b['groups'],b['anchors'],weights,d['l2'])[1]
        updated=Network.load(folder/'updated-selected.npz')[0];frozen=Network.load(folder/'frozen-selected.npz')[0]
        signal.update(common_known_mask_gradient_difference_l2=float(np.sqrt(sum(np.sum((ga[k]-gb[k])**2) for k in ga))),
            missing_label_mask_disagreements=int(np.sum(np.isfinite(a['y'])!=np.isfinite(b['y']))),
            fitted_parameter_distance_l2=float(np.sqrt(sum(np.sum((updated.p[k]-frozen.p[k])**2) for k in updated.p))),
            interpretation='Terminal-label shifts alone do not activate the regret loss. Counts here test actual within-root contrast changes and gradients under an identical known-label mask; no policy qualification or model selection.')
        dump(folder/'target-activation-audit.json',dict(source_commit=commit(),**signal))
    if (folder/'development.json').exists():
        dev=json.loads((folder/'development.json').read_text());games=list(read_rows(folder/'development-games.jsonl.gz'));outcomes={};behavior=defaultdict(Counter)
        models={n:Network.load(folder/f'{n}-selected.npz')[0] for n in ('updated','frozen','phase0')};models.update(v12=initial,v5=base)
        control_changes=control_decisions=0
        for row in read_rows(folder/'development-decisions.jsonl.gz'):
            meta=row['metadata'];name=meta['policy'];key=(name,meta['group'],meta['seed'],meta['seat'])
            if row['record_type']=='outcome':
                assert key not in outcomes;outcomes[key]=row['result'];behavior[name]['unknown']+=row['result']['unfinished'];continue
            actions=list(map(tuple,row['legal_actions']));s=row['selection'];obs=row['observation']
            assert tuple(s['action'])==actions[s['action_index']]
            if obs['player']!=0:continue
            assert s['policy']==models[name].fingerprint
            b=row['baseline']['action_index'];a=s['action_index'];assert tuple(row['baseline']['action'])==actions[b]
            behavior[name]['decisions']+=1
            if name=='updated':
                alternative=LearnedPolicy(models['frozen']).choose(obs,actions)['action_index'];control_decisions+=1
                x=encode(obs,actions)[1][0];control_changes+=not np.array_equal(x[s['action_index']],x[alternative])
            if a!=b:
                behavior[name]['raw_changed']+=1;x=encode(obs,actions)[1][0];behavior[name]['changed']+=not np.array_equal(x[a],x[b])
        souls={g:list(ss) for g,_,_,ss,_ in cases()};assert len(games)==len(outcomes)==600
        perseed={}
        for r in games:
            result=r['result'];recorded=outcomes[r['policy'],r['group'],r['seed'],r['seat']]
            assert all(result.get(k)==v for k,v in recorded.items()) and set(result)-set(recorded)<={'souls'}
            if 'souls' in result:assert result['souls']==souls[r['group']]
            if result['unfinished']:failures.append(dict(stage='development',metadata={k:v for k,v in r.items() if k!='result'},error=result.get('error')))
        for name in models:
            clusters=[[r['result'] for r in games if r['policy']==name and r['seed']==seed] for seed in d['development_seeds']]
            assert all(len(rs)==10 for rs in clusters)
            perseed[name]=(np.array([np.mean([0 if r['unfinished'] else int(r['won']) for r in rs]) for rs in clusters]),
                           np.array([np.mean([1 if r['unfinished'] else int(r['won']) for r in rs]) for rs in clusters]))
        lo,hi=perseed['updated']
        for name,(a,b) in perseed.items():
            assert dev['metrics'][name]['win']==interval(a,b) and dev['metrics'][name]['primary_gain']==interval(lo-b,hi-a)
            for key in ('decisions','changed','raw_changed','unknown'):
                assert dev['metrics'][name]['behavior'][key]==behavior[name][key]
        activation=behavior['updated']['changed']/max(1,behavior['updated']['decisions'])
        gate=bool(lo.mean()>max(perseed['v5'][1].mean(),perseed['v12'][1].mean()) and dev['metrics']['v5']['primary_gain']['low']>=-.05 and activation>=.01 and not behavior['updated']['unknown'])
        assert activation==dev['activation'] and gate==dev['proceed_to_final']
        if not gate:
            status=json.loads((folder/'final-status.json').read_text());assert status['status']=='not_executed' and status['final_seeds_unread'] and status['value_final_unread']
            assert not list(folder.glob('final-games*')) and not list(folder.glob('value-*'))
        checks['development_slots']=600
        checks['primary_decisions_compared_with_frozen']=control_decisions
        checks['primary_semantic_changes_vs_frozen']=control_changes
    if (folder/'posthoc-prior-fit.json').exists():
        plan=json.loads((folder/'posthoc-prior-plan.json').read_text());fit=json.loads((folder/'posthoc-prior-fit.json').read_text())
        control,meta=Network.load(folder/'prior-only-selected.npz')
        assert plan['declared_after_initial_development'] and fit['primary_status_unchanged']
        assert fit['warm_start_actor']==Network.load(folder/'phase0-selected.npz')[0].actor_fingerprint
        assert fit['optimizer_steps']==192 and fit['training_roots']==90 and fit['epochs']==64
        assert meta['terminal_cost_weight']==0 and meta['not_eligible_for_reselection'] and meta['value_unfitted']
        assert not json.loads((folder/'development.json').read_text())['proceed_to_final']
        assert not set(plan['fresh_seeds'])&set(d['development_seeds'])
        checks['posthoc_prior_optimizer_steps']=fit['optimizer_steps']
    if (folder/'posthoc-prior-development.json').exists():
        report=json.loads((folder/'posthoc-prior-development.json').read_text());games=list(read_rows(folder/'posthoc-prior-games.jsonl.gz'))
        assert len(games)==320 and report['finals_still_unread'] and report['no_reselection']
        models={n:Network.load(folder/f'{n}-selected.npz')[0] for n in ('updated','frozen')};models.update(prior_only=control,v5=base)
        outcomes={};behavior=defaultdict(Counter)
        for row in read_rows(folder/'posthoc-prior-decisions.jsonl.gz'):
            m=row['metadata'];name=m['policy'];key=(name,m['group'],m['seed'],m['seat'])
            if row['record_type']=='outcome':
                assert key not in outcomes;outcomes[key]=row['result'];behavior[name]['unknown']+=row['result']['unfinished'];continue
            actions=list(map(tuple,row['legal_actions']));s=row['selection'];o=row['observation']
            assert tuple(s['action'])==actions[s['action_index']]
            if o['player']!=0:continue
            assert s['policy']==models[name].fingerprint;behavior[name]['decisions']+=1
            a=s['action_index'];b=row['baseline']['action_index']
            if a!=b:
                behavior[name]['raw_changed']+=1;x=encode(o,actions)[1][0];behavior[name]['changed']+=not np.array_equal(x[a],x[b])
        souls={g:list(ss) for g,_,_,ss,_ in cases()};assert len(outcomes)==320
        expected={(n,g,seed,seat) for n in models for g,_,_,_,_ in cases() for seed in plan['fresh_seeds'] for seat in (0,1)}
        assert set(outcomes)==expected
        for r in games:
            key=(r['policy'],r['group'],r['seed'],r['seat']);recorded=outcomes[key]
            assert all(r['result'].get(k)==v for k,v in recorded.items()) and set(r['result'])-set(recorded)<={'souls'}
            if 'souls' in r['result']:assert r['result']['souls']==souls[r['group']]
            if r['result']['unfinished']:failures.append(dict(stage='posthoc_prior_development',metadata={k:v for k,v in r.items() if k!='result'},error=r['result'].get('error')))
        scores={}
        for name in models:
            clusters=[[r['result'] for r in games if r['policy']==name and r['seed']==seed] for seed in plan['fresh_seeds']]
            assert all(len(rs)==10 for rs in clusters)
            scores[name]=(np.array([np.mean([0 if r['unfinished'] else int(r['won']) for r in rs]) for rs in clusters]),
                          np.array([np.mean([1 if r['unfinished'] else int(r['won']) for r in rs]) for rs in clusters]))
        lo,hi=scores['updated']
        for name,(a,b) in scores.items():
            assert report['metrics'][name]['win']==interval(a,b) and report['metrics'][name]['updated_gain']==interval(lo-b,hi-a)
            for key in ('decisions','changed','raw_changed','unknown'):assert report['metrics'][name]['behavior'][key]==behavior[name][key]
        assert json.loads((folder/'final-status.json').read_text())['final_seeds_unread']
        checks['posthoc_fresh_development_slots']=320
    if (folder/'off-action-order-probe.json').exists():
        probe=json.loads((folder/'off-action-order-probe.json').read_text());a,b=probe['observations'];actions=list(map(tuple,probe['legal_actions']))
        assert np.array_equal(encode(a,actions)[1][0],encode(b,actions)[1][0])
        assert probe['outcomes_end_or_heal_then_end']==[[True,True],[False,True]] and not probe['fitting_or_selection_use']
        assert np.var(probe['heal_vs_end_terminal_contrasts'])==probe['identical_pair_contrast_minimum_equal_weight_mse']==.25
        assert probe['independent_random_openings']==0 and not probe['distinct_optimal_actions_required']
        checks['constructed_current_input_alias_verified']=1
    if (folder/'interface/verification.json').exists():
        interface=json.loads((folder/'interface/verification.json').read_text())
        assert interface['status']=='passed' and interface['slots']==8 and interface['unresolved']==0
        assert interface['frozen_policy']==Network.load(folder/'updated-selected.npz')[0].fingerprint
        assert interface['quality_gate'] and interface['unfitted_value_rejected'] and interface['unknown_not_zero']
        checks['engineering_actor_slots']=8
    dump(folder/'evidence-audit.json',dict(source_commit=commit(),status='passed',checks=dict(checks),no_replays=True,no_label_repairs=True,
        limitation='Record consistency, not simulator validity, predictive sufficiency, POMDP convergence or policy qualification.'))
    dump(folder/'failures.json',dict(unknown_cells_and_slots=failures,unknowns_not_retried=True,limits=d['limits']))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);audit(p.parse_args().output)
