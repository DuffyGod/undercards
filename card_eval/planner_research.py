"""Frozen V7 experiment: public multiaction planning and continuation values."""
from collections import Counter,defaultdict
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import argparse,gzip,hashlib,json,time
import numpy as np
from .network import Network
from ._planner_v1 import PublicGame,PublicPlanner,UnknownDraw
from .policies import LearnedPolicy,ReferencePolicy
from .relations import state_features
from .catalog import Spec,Effect,resolve,semantic_key
from .profiles import base_deck,opponents,training_pool
from .memory_research import read_rows,opponent
from .counterfactual_research import collect,run
from .relational_research import small_result
from .statistics import interval
from .training import dump,commit

BASE=Path('artifacts/card_eval/v5/primary-value.npz')
SOURCE=Path('artifacts/card_eval/v6')


def cases(final=False):
    own=base_deck();opp=opponents()
    standard=[('pressure',own,opp['pressure'],('INTEGRITY','INTEGRITY'),'race'),
              ('defense',own,opp['defense'],('INTEGRITY','KINDNESS'),'race'),
              ('refill',own,opp['refill'],('KINDNESS','INTEGRITY'),'race')]
    if not final:return standard+[
        ('known_role_failure',opp['pressure'],opp['refill'],('KINDNESS','INTEGRITY'),'guard'),
        ('role_defense',opp['defense'],opp['pressure'],('INTEGRITY','KINDNESS'),'board')]
    param=Spec('heldout_5G_8_10_charge',5,8,10,(('charge',1),),())
    combo=Spec('heldout_taunt_start_growth',5,3,7,(('taunt',1),),(Effect('start','buff','self',1,1),))
    if any(semantic_key(s) in {semantic_key(p) for p in training_pool()} for s in (param,combo)):raise ValueError('Overlapping semantics')
    a=list(own);a[:3]=[param]*3;b=list(own);b[:3]=[combo]*3
    mixed_a=tuple(resolve('Ice Cap') if s.name=='Vegetoid' else resolve('Bench') if s.name=='Scarf Mouse' else s for s in opp['defense'])
    mixed_b=tuple(resolve('Fishing Rod') if s.name=='Ice Cap' else resolve('Sad Dragon') if s.name=='Charles' else s for s in opp['pressure'])
    sweep=Spec('synthetic_sweeper',5,0,5,(),(Effect('play','damage','all_enemy',3),));counter=list(opp['defense']);counter[:3]=[sweep]*3
    return standard+[
        ('new_parameters',tuple(a),opp['pressure'],('INTEGRITY','INTEGRITY'),'race'),
        ('new_composition',tuple(b),opp['pressure'],('INTEGRITY','INTEGRITY'),'race'),
        ('new_mixed_decks',mixed_a,mixed_b,('KINDNESS','KINDNESS'),'race'),
        ('known_delayed_sweep',own,tuple(counter),('INTEGRITY','KINDNESS'),'delayed'),
        ('unseen_learned_opponent',own,opp['pressure'],('INTEGRITY','KINDNESS'),'v5')]


def prepare(folder):
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'design.json').exists():raise ValueError('Preserve frozen experiment')
    inputs=sorted(SOURCE.glob('train-targets-*.jsonl.gz'))+sorted(SOURCE.glob('diagnostic-targets-*.jsonl.gz'))
    dump(folder/'design.json',dict(source_commit=commit(),baseline=str(BASE),rng_seed=2026103107,
        source_files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        train='Reuse V6 current-V5-continuation labels only, no new old roll-outs. Root control vs root plus deterministic own-action successor states.',
        target='Terminal win by V5 continuation, under sampled reference opponent. Not planner-policy V, Q*, or after hidden chance.',
        weights='Equal source opening; equal state weight within each opening.',l2=.01,iterations=160,
        planner=dict(nodes=48,depth=3,width=4,seconds=.18),primary='afterstate_value',margins=[.1,.2,.3],
        development_seeds=list(range(1950000,1950008)),final_seeds=list(range(2050000,2050032)),
        diagnostic_seeds=list(range(2030000,2030096)),max_actions=6,continuations=['baseline'],
        final_value='Fresh worlds and terminal interventions, used once after all weights/configurations frozen. Existing collect routine alternates V5/race roll-in; exactly V5 continuation. Draw/end successors excluded with explicit reasons.',
        selection='Only primary afterstate value margin selected by development mean win; tie larger. Old-value diagnostic uses same margin. Root-control not a final policy selection candidate.',
        final_policies=['primary','proof','old_value','v5','race','board','guard'],
        final_cases=[g for g,*_ in cases(True)],acceptance='Primary paired95%lower positive against V5 and each reference in every context, no unresolved. Report 8-context Bonferroni sensitivity too.',
        decision_seconds=.25,partial='Observation-only current-turn deterministic actions. Unknown draw and nonterminal end stop expansion. No opponent private deck, hand, seed, hidden chance sampling or opponent-turn search.',
        retired_final_ranges=[1210000,1310000,1330000,1610000,1630000,1810000,1830000],
        limitations=['One trained actor','Value is for base continuation, not planner continuation','No learned belief distribution','Fixed nonadaptive reference opponents plus heldout V5 opponent, not a best response','Model rules not server certified']))


def rows(folder,stage,reused=True):
    pattern=f'{stage}-targets-*.jsonl.gz' if reused else f'{stage}-forks-*.jsonl.gz'
    for path in sorted(folder.glob(pattern)):
        yield from read_rows(path)


def samples(source):
    data=[];counts=Counter()
    for row in source:
        counts['forks']+=1;obs=row['observation'];actions=list(map(tuple,row['legal_actions']))
        current={b['action_index']:b for b in row['branches'] if b['continuation'] in ('current','baseline')}
        base=current.get(row['baseline_action'])
        if base is not None and not base['unfinished']:
            data.append((row['seed'],'root',state_features(obs),int(base['won'])))
        else:counts['unknown_root']+=1
        for index,branch in current.items():
            if branch['unfinished']:counts['unknown_terminal_label']+=1;continue
            action=actions[index]
            if action[0]=='end':counts['end_boundary']+=1;continue
            try:child=PublicGame(obs).child(action)
            except UnknownDraw:counts['unknown_draw']+=1;continue
            terminal=child.terminal()
            if terminal is not None:
                counts['exact_terminal']+=1
                if terminal!=bool(branch['won']):raise ValueError('Public terminal and replay disagree')
                continue
            data.append((row['seed'],'after',state_features(child.observation()),int(branch['won'])))
    counts['root_states']=sum(k=='root' for _,k,_,_ in data);counts['after_states']=sum(k=='after' for _,k,_,_ in data)
    counts['opening_clusters']=len(set(s for s,*_ in data))
    return data,dict(counts)


def fit(folder):
    d=json.loads((folder/'design.json').read_text())
    for path,digest in d['source_files'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Changed source evidence')
    data,counts=samples(rows(SOURCE,'train'));base=Network.load(BASE)[0];fits={}
    for name,selected in [('root', [r for r in data if r[1]=='root']),('afterstate',data)]:
        net=deepcopy(base);sizes=Counter(s for s,*_ in selected)
        report=net.fit_value([s for _,_,s,_ in selected],[y for *_,y in selected],
            [1/sizes[seed] for seed,*_ in selected],d['l2'],d['iterations'])
        if net.actor_fingerprint!=base.actor_fingerprint:raise ValueError('Changed base actor')
        net.save(folder/(name+'-value.npz'),dict(source_commit=commit(),validation=dict(qualified=False),
            target=d['target'],value_fit=report,model_name='afterstate-v7' if name=='afterstate' else 'root-control-v7'))
        fits[name]=dict(report=report,fingerprint=net.fingerprint,actor_fingerprint=net.actor_fingerprint)
    diagnostic,dc=samples(rows(SOURCE,'diagnostic'))
    models={n:Network.load(folder/(n+'-value.npz'))[0] for n in fits};models['old']=base
    dump(folder/'fit.json',dict(source_commit=commit(),counts=counts,fits=fits,diagnostic_counts=dc,
        diagnostic_metrics=metrics(models,diagnostic),limits='Diagnostic is reused, not a new independent final; target belongs to base actor.'))


def metrics(models,data):
    output={}
    for kind in ('root','after'):
        selected=[r for r in data if r[1]==kind];by={}
        for name,net in models.items():
            per=defaultdict(list)
            for seed,_,state,label in selected:
                prob=(net.predict_value(state)+1)/2;per[seed].append((prob-label)**2)
            by[name]={s:float(np.mean(a)) for s,a in per.items()}
        seeds=sorted(set.intersection(*(set(x) for x in by.values()))) if by else []
        if not seeds:output[kind]=None;continue
        scores={n:interval([v[s] for s in seeds]) for n,v in by.items()}
        gains={n:interval([by[n][s]-by['afterstate'][s] for s in seeds]) for n in by if n!='afterstate'}
        output[kind]=dict(states=len(selected),opening_clusters=len(seeds),brier=scores,afterstate_error_reduction=gains)
    return output


def make(name,models,d,margin):
    if name=='v5':return LearnedPolicy(models['old'])
    if name=='proof':return PublicPlanner(models['old'],'proof',margin,**d['planner'])
    if name in ('primary','old_value'):return PublicPlanner(models['afterstate'] if name=='primary' else models['old'],'value',margin,**d['planner'])
    return ReferencePolicy(name)


def development(folder):
    if (folder/'development.json').exists():raise ValueError('Preserve development')
    d=json.loads((folder/'design.json').read_text());models={'afterstate':Network.load(folder/'afterstate-value.npz')[0],'old':Network.load(BASE)[0]}
    results=[]
    with gzip.open(folder/'development-games.jsonl.gz','wt',encoding='utf-8') as sink:
        for margin in d['margins']:
            score=[];unknown=0
            for group,a,b,souls,style in cases():
                for seed in d['development_seeds']:
                    for seat in (0,1):
                        r=run((a,b),seed,(make('primary',models,d,margin),opponent(style)),seat,souls)
                        sink.write(json.dumps(dict(group=group,seed=seed,seat=seat,margin=margin,result=small_result(r)),separators=(',',':'))+'\n')
                        score.append(0 if r['unfinished'] else float(r['won']));unknown+=r['unfinished']
            results.append(dict(margin=margin,mean_win_lower=float(np.mean(score)),unfinished=unknown,games=len(score)))
            print(json.dumps(results[-1]),flush=True);dump(folder/'development-progress.json',results)
    selected=max(results,key=lambda r:(r['mean_win_lower'],r['margin']))['margin']
    policies={name:make(name,models,d,selected) for name in ('primary','proof','old_value')}
    dump(folder/'development.json',dict(results=results,selected_margin=selected,frozen_policies={n:p.fingerprint for n,p in policies.items()},source_commit=commit()))


class PlannerRecorder:
    def __init__(self):self.events=Counter()
    def record(self,obs,actions,selection):
        if obs['player']!=0:return
        self.events[selection.get('planner_reason','base')]+=1
        for key in ('planner_nodes','unknown_draw_boundaries','proof_mismatch'):
            self.events[key]+=selection.get(key,0)
    def finish(self,result):pass


def final(folder):
    if (folder/'final.json').exists() or (folder/'final-games.jsonl.gz').exists():raise ValueError('Final used once')
    d=json.loads((folder/'design.json').read_text());dev=json.loads((folder/'development.json').read_text());margin=dev['selected_margin']
    models={'afterstate':Network.load(folder/'afterstate-value.npz')[0],'old':Network.load(BASE)[0]}
    names=d['final_policies'];groups=[];failures=[];started=time.monotonic()
    dump(folder/'final-plan.json',dict(source_commit=commit(),frozen_policies=dev['frozen_policies'],margin=margin,seeds=d['final_seeds'],
        cases=[dict(group=g,decks=[[asdict(s) for s in deck0] for deck0 in (a,b)],souls=s,opponent=p) for g,a,b,s,p in cases(True)]))
    with gzip.open(folder/'final-games.jsonl.gz','wt',encoding='utf-8') as sink:
        for group,a,b,souls,style in cases(True):
            scores={n:[] for n in names};times={n:[] for n in names};events={n:Counter() for n in names}
            for seed in d['final_seeds']:
                seats={n:[] for n in names}
                for seat in (0,1):
                    for name in names:
                        rec=PlannerRecorder();enemy=LearnedPolicy(models['old']) if style=='v5' else opponent(style)
                        r=run((a,b),seed,(make(name,models,d,margin),enemy),seat,souls,rec)
                        sink.write(json.dumps(dict(group=group,seed=seed,seat=seat,policy=name,result=small_result(r),planner=dict(rec.events)),separators=(',',':'))+'\n')
                        seats[name].append(None if r['unfinished'] else float(r['won']));times[name].extend(r['decision_seconds'][0]);events[name].update(rec.events)
                        if r['unfinished']:failures.append(dict(group=group,seed=seed,seat=seat,policy=name,error=r.get('error')))
                for name in names:scores[name].append((np.mean([0 if x is None else x for x in seats[name]]),np.mean([1 if x is None else x for x in seats[name]])))
            lo,hi=np.asarray(scores['primary']).T;comparisons=[]
            for name in names:
                a0,b0=np.asarray(scores[name]).T
                comparisons.append(dict(policy=name,win=interval(a0,b0),primary_gain=interval(lo-b0,hi-a0),
                    family_gain=interval(lo-b0,hi-a0,alpha=.05/len(cases(True)))))
            groups.append(dict(group=group,policies=comparisons,planner={n:dict(e) for n,e in events.items()},
                timings={n:dict(decisions=len(t),p95=float(np.quantile(t,.95)) if t else None,maximum=max(t) if t else None) for n,t in times.items()}))
            print(json.dumps(dict(group=group,wins={r['policy']:r['win']['completion_range'] for r in comparisons},elapsed=time.monotonic()-started)),flush=True)
            dump(folder/'final-progress.json',dict(groups=groups,failures=failures))
    qualified=not failures and all(c['primary_gain']['low']>0 for g in groups for c in g['policies'] if c['policy'] in ('v5','race','board','guard'))
    dump(folder/'final.json',dict(source_commit=commit(),qualified=qualified,groups=groups,failures=failures,no_final_selection=True,elapsed_seconds=time.monotonic()-started))
    net=models['afterstate']
    dump(folder/'validation.json',dict(qualified=False,status='not_qualified',frozen_policy=net.fingerprint,
        reason='Checkpoint alone retains V5 actor; planner has a separate configuration and qualification.',source='final.json'))
    dump(folder/'planner-validation.json',dict(qualified=qualified,status='qualified' if qualified else 'not_qualified',
        frozen_policy=dev['frozen_policies']['primary'],base_checkpoint=net.fingerprint,config=dict(d['planner'],mode='value',margin=margin),source='final.json'))


def final_value(folder):
    if (folder/'final-value.json').exists():raise ValueError('Preserve final value')
    collect(folder,'diagnostic')
    data,counts=samples(rows(folder,'diagnostic',reused=False))
    models={n:Network.load(folder/(n+'-value.npz'))[0] for n in ('root','afterstate')};models['old']=Network.load(BASE)[0]
    dump(folder/'final-value.json',dict(source_commit=commit(),counts=counts,metrics=metrics(models,data),no_selection=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','fit','development','final','final-value']);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    {'prepare':prepare,'fit':fit,'development':development,'final':final,'final-value':final_value}[args.mode](args.output)
