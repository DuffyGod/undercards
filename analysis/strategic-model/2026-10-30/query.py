"""Read-only conditional body comparison; no default global scalar ranking."""
from pathlib import Path
import argparse,json

HERE=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--world',default='sweep_integrity_seat0');p.add_argument('--host',choices=['wide','anchor'],default='wide')
    p.add_argument('--body');p.add_argument('--against',choices=['trade_hold_two','face_hold_two','frontier_defender'])
    p.add_argument('--counterfactuals',action='store_true');p.add_argument('--compare',nargs=2,metavar=('A','B'))
    a=p.parse_args();dest=HERE/'experiment-v01';summary=json.loads((dest/'summary.json').read_text())
    m=json.loads((dest/'manifest.json').read_text())
    if a.world not in m['worlds']:raise ValueError('No saved result for requested condition; no interpolation')
    output=dict(scope=summary['interpretation'],world=a.world,host=a.host,
        note='Rates are abstract-host outcomes, not actual Undercards win rates. Policies frozen on training; test differences exploratory, not new policy fitting.')
    if a.compare:
        x,y=a.compare
        if x not in m['bodies'] or y not in m['bodies']:raise ValueError('Unknown exact body name')
        effects=[r for r in summary['comparisons'] if r['world']==a.world and r['structure']==a.host and r['a']==x and r['b']==y and (not a.against or r['column']==a.against)]
        if not effects:raise ValueError('No predeclared saved comparison in this order; inspect profiles instead')
        output['comparisons']=effects
    else:
        rows=[r for r in summary['results'] if r['world']==a.world and r['structure']==a.host and
              (not a.body or r['body']==a.body) and (a.counterfactuals or not m['bodies'][r['body']]['counterfactual'])]
        if not rows:raise ValueError('Unknown or excluded body; fictional parameters require --counterfactuals')
        opp=json.loads((dest/'opportunity.json').read_text())['results']
        profile=[]
        for r in rows:
            r=dict(r);r['body_parameters']=m['bodies'][r['body']]
            r['against']=[c for c in r['against'] if not a.against or c['column']==a.against]
            o=next(o for o in opp if o['world']==a.world and o['structure']==a.host and o['body']==r['body'])
            r['opportunity']=[v for v in o['against'] if not a.against or v['column']==a.against];profile.append(r)
        output['profiles']=profile
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
