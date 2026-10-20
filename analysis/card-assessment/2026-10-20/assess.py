"""Read dossiers or value any Agent-authored ledger; no game implementation gate."""
import argparse,json
from pathlib import Path
from value_ledger import *

def load_dossiers():
    cards=json.loads((HERE/'results/dossiers.json').read_text())['cards']
    extension=HERE/'promising-tactics/results/dossiers.json'
    if extension.exists():
        extra=json.loads(extension.read_text())['cards']
        if {c['card_id'] for c in cards}&{c['card_id'] for c in extra}:
            raise ValueError('Overlapping dossier sources require explicit merge, not silent overwrite')
        cards+=extra
    return cards
def find_record(record_id):
    matches=[r for c in load_dossiers() for r in c['records'] if r['id']==record_id]
    if len(matches)!=1:raise ValueError('Unknown/ambiguous conditional record, no interpolation')
    return matches[0]

def load_catalog():
    catalog=json.loads((HERE/'results/catalog.json').read_text())
    modeled={c['card_id']:c for c in load_dossiers()}
    for c in catalog['cards']:
        if c['card_id'] in modeled:
            c['has_agent_conditional_dossier']=True
            c['assessment_status']=modeled[c['card_id']]['assessment_status']
            if 'inventory_convention' in modeled[c['card_id']]:
                c['dossier']=f"promising-tactics/results/dossiers.json#card-{c['card_id']}"
    catalog['conditional_dossier_count']=len(modeled)
    catalog['scope']='All755 ordinary cards; base catalog overlaid with curated extensions, not global ratings'
    return catalog

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    a=sub.add_parser('catalog');a.add_argument('--modeled-only',action='store_true')
    a=sub.add_parser('card');a.add_argument('id',type=int);a.add_argument('--root');a.add_argument('--record')
    a.add_argument('--face',type=float,default=.25);a.add_argument('--card-price',type=float,default=1);a.add_argument('--gold',type=float,default=1)
    a=sub.add_parser('ledger');a.add_argument('file',type=Path)
    a=sub.add_parser('compare');a.add_argument('left');a.add_argument('right')
    a=sub.add_parser('carry');a.add_argument('good');a.add_argument('--bad');a.add_argument('--q',type=float,nargs='+',default=[0,.25,.5,.75,1])
    a.add_argument('--holding-cost',type=float,required=True);a.add_argument('--replacement-surplus',type=float,default=0)
    a=sub.add_parser('holding');a.add_argument('--hand',type=int,required=True);a.add_argument('--draws',nargs='+',type=int,required=True);a.add_argument('--plays',nargs='+',type=int,required=True)
    args=p.parse_args()
    if args.mode=='catalog':
        out=load_catalog()
        if args.modeled_only:out['cards']=[c for c in out['cards'] if c['has_agent_conditional_dossier']]
    elif args.mode=='ledger':out=analyze(json.loads(args.file.read_text()))
    elif args.mode=='compare':
        left,right=find_record(args.left),find_record(args.right)
        if ('inventory' in left)!=('inventory' in right):raise ValueError('Different played-card accounting; normalize inventory before comparison')
        out=paired_difference(left['ledger'],right['ledger'])
    elif args.mode=='carry':
        good=find_record(args.good);bad=find_record(args.bad) if args.bad else None
        if 'inventory' in good or (bad and 'inventory' in bad):
            raise ValueError('Tactical J is not calibrated vs waiting; use matched action comparison, not max(0,J) carrying threshold')
        out=dict(good=good['id'],bad=None if bad is None else bad['id'],profiles=[carrying(good['ledger'],None if bad is None else bad['ledger'],q=q,holding_cost=args.holding_cost,replacement_surplus=args.replacement_surplus) for q in args.q])
    elif args.mode=='holding':out=extra_burns(args.hand,args.draws,args.plays)
    else:
        hits=[c for c in load_dossiers() if c['card_id']==args.id]
        if not hits:
            allcards=load_catalog()['cards']
            c=next((c for c in allcards if c['card_id']==args.id),None)
            if c is None:raise ValueError('Not in ordinary constructible snapshot')
            out=c  # Pending is a visible result, never a fake zero/plain grade.
        else:
            c=hits[0];rs=[r for r in c['records'] if (not args.root or r['root']==args.root) and (not args.record or r['id']==args.record)]
            if not rs:raise ValueError('Conditional root/record absent')
            prices=dict(face=args.face,card=args.card_price,gold=args.gold)
            out={k:v for k,v in c.items() if k!='records'}
            out['records']=[dict(id=r['id'],root=r['root'],condition=r['ledger'].get('condition','current action endpoint'),stage=r['ledger']['valuation_stage'],quote=quote(r['ledger'],prices)) for r in rs]
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
