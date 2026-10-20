"""Read frozen per-match results. Never invokes the simulator or API."""
from pathlib import Path
from collections import defaultdict
from statistics import mean,stdev
from math import sqrt
from itertools import combinations
import argparse,csv,gzip,json
HERE=Path(__file__).resolve().parent
KEYS=('composition','policy','soul','opponent','seat','intervention')
METRICS=('killed','dead','hp','opponent_hp','pressure_15','pressure_10','damage','healed',
         'cash','hand','field_attack','bonus_draws','bonus_played','bonus_burned','burned',
         'slot_blocked_turns','slot_missed','reserve_withheld_turns','empty_hand_turns',
         'first_turn_no_opener','first_turn_available_but_no_play','first_turn_no_play',
         'small_countered_insufficient','small_killed_by_big','stalled_pressure','fatigue_damage')
BINARY={'killed','dead','pressure_15','pressure_10','first_turn_no_opener',
        'first_turn_available_but_no_play','first_turn_no_play','small_countered_insufficient','stalled_pressure',
        'dead_with_foe_le5','dead_with_foe_gt15','big_reply_seen','big_reply_above15','any_burn','any_slot_missed'}
EXTRA=('dead_with_foe_le5','dead_with_foe_gt15','big_reply_seen','big_reply_above15','any_burn','any_slot_missed','opponent_healed','bonus_held')

def wilson(k,n,z=1.96):
    if not n:return None
    p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;r=z*sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [c-r,c+r]

def interval(xs):
    m=mean(xs)
    se=stdev(xs)/sqrt(len(xs)) if len(xs)>1 else 0
    return dict(n=len(xs),mean=m,se=se,normal95=[m-1.96*se,m+1.96*se])

def metrics(r):
    s=r['players'][r['seat']];e=r['players'][1-r['seat']]
    out={k:s[k] for k in METRICS}
    out.update(dead_with_foe_le5=s['dead'] and s['opponent_hp']<=5,
        dead_with_foe_gt15=s['dead'] and s['opponent_hp']>15,
        big_reply_seen=s['big_reply'] is not None,
        big_reply_above15=s['big_reply'] is not None and s['big_reply']['opponent_hp']>15,
        any_burn=s['burned']>0,any_slot_missed=s['slot_missed']>0,
        opponent_healed=e['healed'],bonus_held=s['bonus_draws']-s['bonus_burned']-s['bonus_played'])
    return out


def load(directory,require_complete=True):
    directory=Path(directory)
    spec=json.loads((directory/'design.json').read_text())
    receipt=json.loads((directory/'receipt.json').read_text())
    if require_complete and not receipt['complete']:raise ValueError(f'Incomplete study {directory}; no fill')
    output=[]
    for i,g in enumerate(spec['groups']):
        path=directory/f'group-{i:03d}.jsonl.gz'
        if not path.exists():
            if require_complete:raise ValueError('Missing raw group')
            continue
        rows=[json.loads(line) for line in gzip.open(path,'rt')]
        if len(rows)!=spec['samples'] or len({r['seed'] for r in rows})!=spec['samples']:raise ValueError('Incomplete/duplicate seeds')
        if any(tuple(r[k] for k in KEYS)!=tuple(g[k] for k in KEYS) for r in rows):raise ValueError('Group metadata mismatch')
        output.append((g,rows))
    return spec,output


def summarize(rows):
    ms=[metrics(r) for r in rows];out={}
    for k in METRICS+EXTRA:
        xs=[m[k] for m in ms];a=interval(xs)
        if k in BINARY:a['count']=sum(xs);a['wilson95']=wilson(sum(xs),len(xs))
        out[k]=a
    for k in ('hp','opponent_hp','cash','hand','field_attack'):
        xs=sorted(m[k] for m in ms);out[k]['q10_q50_q90']=[xs[int((len(xs)-1)*q)] for q in (.1,.5,.9)]
    return out


def paired(left,right):
    ls={r['seed']:r for r in left};rs={r['seed']:r for r in right}
    if ls.keys()!=rs.keys():raise ValueError('Unpaired seeds')
    return {k:interval([metrics(ls[s])[k]-metrics(rs[s])[k] for s in ls]) for k in METRICS+EXTRA}


def write_derived(directories,out):
    out=Path(out);out.mkdir(exist_ok=True)
    allgroups=[];sources={}
    for directory in directories:
        spec,gs=load(directory);sources[str(directory)]=dict(version=spec['version'],source_commit=spec['source_commit'])
        allgroups.extend((Path(directory).name,g,rows) for g,rows in gs)
    unique_records={};duplicate_records=0
    for stage,g,rows in allgroups:
        for r in rows:
            key=(r['version'],tuple(g[k] for k in KEYS),r['seed'])
            if key in unique_records:
                old=unique_records[key]
                if old['players']!=r['players'] or old['snapshots']!=r['snapshots']:
                    raise ValueError('Repeated baseline differs; investigate')
                duplicate_records+=1
            else:unique_records[key]=r
    summ=[dict(stage=stage,**g,n=len(rows),metrics=summarize(rows)) for stage,g,rows in allgroups]
    pairs=[]
    # Only one declared input field differs within a comparison; no cross-stage
    # pooling, price tuning, or per-seed winner selection.
    for (sa,a,ra),(sb,b,rb) in combinations(allgroups,2):
        if sa!=sb:continue
        changed=[k for k in KEYS if a[k]!=b[k]]
        if len(changed)!=1 or changed[0] not in ('composition','policy','intervention'):continue
        field=changed[0]
        if field=='intervention' and a[field]!='base' and b[field]!='base':continue
        pairs.append(dict(stage=sa,field=field,left=a,right=b,difference='left minus right',metrics=paired(ra,rb)))
    stage_index={(stage,tuple(g[k] for k in KEYS)):(g,rows) for stage,g,rows in allgroups}
    # Explicit new-policy / new-composition / new-opponent-policy contrasts.
    # v0.2 -> v0.3 mechanics are unchanged when public_tactics=False; only this
    # newly enabled deterministic order correction changes these policy cells.
    for stage,g,rows in allgroups:
        reference=None;field=None
        if stage=='tactics':reference=('main',g|{'intervention':'base'});field='public_action_order_both_sides'
        elif stage in ('extension','stress_extension'):
            reference=('tactics' if stage=='extension' else 'stress',g|{'composition':'small_draw'});field='composition'
        elif stage=='stress':
            mapping={'pressure_mid':'mid','pressure_large':'large_reply'}
            reference=('tactics',g|{'opponent':mapping[g['opponent']]});field='opponent_policy'
        if reference:
            refstage,refg=reference;hit=stage_index.get((refstage,tuple(refg[k] for k in KEYS)))
            if hit is None:raise ValueError('Missing explicit contrast baseline')
            pairs.append(dict(stage=stage,reference_stage=refstage,field=field,left=g,right=refg,
                difference='left minus right',metrics=paired(rows,hit[1])))
    conditional=[]
    for stage,g,rows in allgroups:
        for missing in (True,False):
            subset=[r for r in rows if r['players'][r['seat']]['first_turn_no_opener']==missing]
            conditional.append(dict(stage=stage,**g,condition='no_opener' if missing else 'opener_present',
                denominator=len(subset),whole_sample=len(rows),metrics=summarize(subset) if subset else None,
                interpretation='Diagnostic conditional subset, not a matched causal treatment effect.'))
    obj=dict(sources=sources,record_count=sum(len(rs) for _,_,rs in allgroups),unique_evaluation_records=len(unique_records),repeated_saved_baselines=duplicate_records,conditional=conditional,interpretation='conditional shuffle outcomes; Wilson for binary levels, paired normal approximation for differences; not ladder win rates',summaries=summ,paired=pairs)
    (out/'summary.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    with (out/'summary.csv').open('w') as f:
        fields=['stage',*KEYS,'n',*METRICS,*EXTRA];w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader()
        for s in summ:w.writerow({k:v for k,v in s.items() if k!='metrics'}|{k:v['mean'] for k,v in s['metrics'].items()})
    return obj


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directories',nargs='+',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();obj=write_derived(args.directories,args.output)
    print(json.dumps(dict(groups=len(obj['summaries']),paired_comparisons=len(obj['paired'])),ensure_ascii=False))

if __name__=='__main__':main()
