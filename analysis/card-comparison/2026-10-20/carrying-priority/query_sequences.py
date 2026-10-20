"""Read saved short-sequence contrasts. No combat or old producer runs."""
import argparse,gzip,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
QUESTIONS=('timing','bridge-mid','bridge-heavy','self-draw','use-draw','mid-versus-heavy')


def load():
    all_data={};sources={}
    for folder in ('sequence-results','sequence-earliest'):
        design=json.loads((HERE/folder/'design.json').read_text())
        with gzip.open(HERE/folder/'sequences.json.gz','rt',encoding='utf-8') as f:data=json.load(f)
        for case,policies in data.items():
            for policy,record in policies.items():
                if policy in all_data.setdefault(case,{}):raise ValueError('Duplicate evidence, no silent overwrite')
                all_data[case][policy]=record;sources[(case,policy)]=dict(folder=folder,producer=design['producer_source_commit'])
    return all_data,sources


def policies(question,seat):
    if question=='timing':return 'staggered_three','late_same_three'
    if question=='bridge-mid':return 'bridge_5','save_5' if seat=='first' else 'save_5_at2'
    if question=='bridge-heavy':return 'bridge_9','save_9' if seat=='first' else 'save_9_at3'
    if question=='self-draw':return ('draw_5','save_5') if seat=='first' else ('draw_5_at2','save_5_at2')
    if question=='use-draw':
        if seat!='second':raise ValueError('This exact accelerated 12G script is second-only')
        return 'draw_accelerates_two','normal_two_later'
    if question=='mid-versus-heavy':return 'bridge_5','save_9' if seat=='first' else 'save_9_at3'
    raise ValueError('Unknown question')


def query(data,sources,question,seat,soul,enemy,horizon,hand_price=1,setting='all',trace=False):
    if setting=='all' and hand_price!=1:raise ValueError('All nine settings are saved only at hand price1; use central for0 or2')
    key=f'{seat}/{soul}/{enemy}/t{horizon}'
    a,b=policies(question,seat)
    if key not in data or a not in data[key] or b not in data[key]:raise ValueError('No complete paired evidence for the requested conditions')
    def selected(policy):
        return {r['setting']:r for r in data[key][policy]['results'] if r['hand_price']==hand_price and
                (setting=='all' or r['setting']==setting)}
    left,right=selected(a),selected(b)
    if not left or left.keys()!=right.keys():raise ValueError('Both scripts require identical saved prices')
    pairs=[]
    for name,r in left.items():
        s=right[name]
        if r['terminal_result']!=s['terminal_result']:
            pairs.append(dict(setting=name,left_result=r['terminal_result'],right_result=s['terminal_result'],difference=None))
        else:pairs.append(dict(setting=name,left_result=r['terminal_result'],right_result=s['terminal_result'],difference=r['value']-s['value']))
    central='central' if 'central' in left else next(iter(left))
    def physical(r):
        own,enemy=r['final']['players']
        out=dict(own_hp=own['hp'],enemy_hp=enemy['hp'],own_cash=own['cash'],remaining_hand=own['hand'],
                 own_field=own['field'],enemy_field=enemy['field'],own_played=own['played'],
                 own_bonus_draws=own['bonus_draws'],own_burned=own['burned'])
        if trace:out['witness']=r['witness']
        return out
    values=[p['difference'] for p in pairs if p['difference'] is not None]
    return dict(assessment_kind='heuristic',empirically_calibrated=False,question=question,case=key,
                left_policy=a,right_policy=b,cash_price=.5,hand_price=hand_price,
                common_setting_differences=pairs,range=[min(values),max(values)] if len(values)==len(pairs) else None,
                representative_setting=central,left=physical(left[central]),right=physical(right[central]),
                source_left=sources[(key,a)],source_right=sources[(key,b)],
                scope='Known-arrival fixed deployments; combat optimized, no metagame frequencies or deck proportions',
                deadline_warning='Ends after both players completed the named own-turn count; a second-player fresh body has not faced the NEXT first-player turn',
                life_price_warning='Base score requires survival only. Its witness HP is not a worst-HP guarantee; see separate safety probes for endpoint HP15/20 goals',
                witness_warning='A worst-value continuation, not separate worst HP/body bounds')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--question',choices=QUESTIONS,required=True)
    p.add_argument('--seat',choices=('first','second'),default='first')
    p.add_argument('--soul',choices=('INTEGRITY','KINDNESS'),default='INTEGRITY')
    p.add_argument('--enemy',choices=('empty','two_low','mid_pressure'),default='mid_pressure')
    p.add_argument('--horizon',type=int,choices=(4,5),default=4)
    p.add_argument('--hand-price',type=int,choices=(0,1,2),default=1)
    p.add_argument('--setting',default='all');p.add_argument('--trace',action='store_true')
    args=p.parse_args()
    try:
        data,sources=load()
        out=query(data,sources,args.question,args.seat,args.soul,args.enemy,args.horizon,args.hand_price,args.setting,args.trace)
    except (ValueError,KeyError,FileNotFoundError) as error:p.error(str(error))
    print(json.dumps(out,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
