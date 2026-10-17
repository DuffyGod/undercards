"""Joint survival/pressure guarantees under one legitimate information policy.

Binary search on a monotone enemy-HP constraint, then optimize own HP under
that same constraint. No HP exchange rate, hidden-hand frequencies, or oracle
future actions enter these points. Unknown queries never count as infeasible.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from finite_game import belief

VERSION='information-joint-pressure-0.1.0'


def sources():
    return {'information_pressure.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            **{'finite_game/'+name:value for name,value in belief.sources().items()}}


def evaluate(config, *, floors):
    binding=sources()
    if not isinstance(floors,list) or not floors or any(type(h) is not int or h<1 for h in floors) or len(set(floors))!=len(floors):
        raise ValueError('Explicit distinct positive integer survival floors required')
    if not isinstance(config,dict):raise ValueError('Information config must be an object')
    data=copy.deepcopy(config);data['report_oracle']=False
    task=data.get('task',{'kind':'hp'});belief.objective(task)
    upper=data['scenario'].get('enemy_player_max_hp',30)
    if type(upper) is not int or upper<1:raise ValueError('Explicit finite positive enemy HP ceiling required')
    maximum=belief.evaluate(data);calls=1;cache={}
    pending=sorted(floors)
    if maximum['known'] and maximum['common_policy']['feasible']:
        h=maximum['common_policy']['guaranteed_player_hp']
        if h not in pending:pending.append(h)
    def query(floor,cap):
        nonlocal calls
        bounds=copy.deepcopy(task.get('constraints',{}))
        bounds['min_own_player_hp']=max(floor,bounds.get('min_own_player_hp',1))
        bounds['max_enemy_player_hp']=min(cap,bounds.get('max_enemy_player_hp',upper))
        key=belief.canonical(bounds)
        if key not in cache:
            request=dict(data,task={'kind':'joint','constraints':bounds})
            cache[key]=belief.evaluate(request);calls+=1
        return cache[key]
    rows=[]
    for floor in pending:
        row=dict(requested_floor=floor,origin='requested' if floor in floors else 'maximum_survival_anchor',
                 known=None,feasible=None,own_hp=None,enemy_hp_cap=None,policy_certificate=None,unknown=[])
        test=query(floor,upper)
        if not test['known']:
            row.update(known=False,unknown=test['unknown'])
        elif not test['common_policy']['feasible']:
            row.update(known=True,feasible=False)
        else:
            lo,hi=-1,upper
            while hi-lo>1:
                mid=(lo+hi)//2; candidate=query(floor,mid)
                if not candidate['known']:
                    row.update(known=False,unknown=candidate['unknown']);break
                if candidate['common_policy']['feasible']:hi=mid;test=candidate
                else:lo=mid
            if row['known'] is None:
                test=query(floor,hi)
                row.update(known=True,feasible=True,own_hp=test['common_policy']['guaranteed_player_hp'],
                    enemy_hp_cap=hi,policy_certificate=test)
                assert row['own_hp']>=floor
        rows.append(row)
    points=sorted({(r['own_hp'],r['enemy_hp_cap']) for r in rows if r['known'] and r['feasible']},reverse=True)
    frontier=[dict(own_hp=h,enemy_hp_cap=e) for h,e in points if not any(h2>=h and e2<=e and (h2>h or e2<e) for h2,e2 in points)]
    if binding!=sources():raise RuntimeError('Source changed during information-pressure evaluation')
    return dict(version=VERSION,source_hashes=binding,input_sha256=hashlib.sha256(belief.canonical(config).encode()).hexdigest(),
                task=task,floors=floors,maximum_survival=maximum,rows=rows,frontier=frontier,
                complete_sampled_floors=all(r['known'] for r in rows),actual_information_evaluations=calls,
                semantics='Each point is a shared-policy own-HP lower bound and enemy-HP upper bound. '
                    'Different points may use different common policies. Exact at sampled floors only; '
                    'the declared hidden-world envelope and server rules are not externally calibrated.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();d=json.loads(Path(a.input).read_text());r=evaluate(d['information_config'],floors=d['survival_floors'])
    Path(a.output).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(frontier=r['frontier'],complete_sampled_floors=r['complete_sampled_floors'],actual_information_evaluations=r['actual_information_evaluations'])))


if __name__=='__main__':main()
