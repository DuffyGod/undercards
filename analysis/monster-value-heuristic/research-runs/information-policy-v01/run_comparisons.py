"""Same-fee slot substitutions under a shared two-world opponent envelope."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from finite_game import belief
from finite_game.rules import compile_card,UnknownMechanic
P=Path(__file__).parent
CARDS=json.loads((ROOT.parents[1]/'skills/undercards/references/snapshot.json').read_text())['cards']
BY={c['id']:c for c in CARDS}
WORLDS=[dict(id='generated_penetration',opponent_hand_ids=[79],opponent_hand_generated=[True]),
        dict(id='generated_worsening',opponent_hand_ids=[86],opponent_hand_generated=[True])]
TASKS={'hp':dict(kind='hp'), 'standing':dict(kind='joint',constraints={'min_own_living_count':1})}


def scene(hand, fee, context, wallet, hp=15):
    def body(cid,key):
        c=BY[cid]
        return dict(card_id=cid,key=key,attack=c['attack'],health=c['health'],max_health=c['health'],
                    ready=True,printed_cost=c['cost'],base_cost=c['cost'],current_cost=c['cost'])
    board=[body(246,'enemy:old')] if context=='single' else [body(2,'enemy:left'),body(2,'enemy:right')]
    return dict(hand_ids=hand,hand_generated=[False]*len(hand),gold_before_play=fee,
                opponent_gold_before_response=wallet,own_player_hp=hp,own_player_max_hp=30,
                enemy_player_hp=30,enemy_player_max_hp=30,ally_bodies_before_play=[],enemy_bodies=board,
                own_deck_ids=[],opponent_deck_ids=[],next_own_gold_income=0,next_opponent_gold_income=0,
                next_natural_draw_count=0,next_opponent_natural_draw_count=0)


def configuration(data,task):
    return dict(scenario=data,worlds=WORLDS,task=task,node_limit=50000,audit_limit=150000,include_policy=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pilot',action='store_true');args=parser.parse_args()
    binding=belief.sources();inventory=[]
    for c in CARDS:
        if c['card_type']!='monster' or c['pool_category']!='ordinary_non_token' or not 1<=c['cost']<=10:continue
        try:compile_card(c);error=[]
        except UnknownMechanic as exc:error=[str(exc)]
        inventory.append(dict(card_id=c['id'],name=c['name'],cost=c['cost'],compile_supported=not error,unknown=error))
    (P/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n')
    selected=[r for r in inventory if r['compile_supported'] and (not args.pilot or r['card_id'] in [14,15,168,307])]
    out=P/('pilot-current' if args.pilot else 'main');out.mkdir(exist_ok=True)
    rows=[];baselines={};start=time.time();core_evaluations=0
    def measure(config,path):
        nonlocal core_evaluations
        result=belief.evaluate(config,CARDS);core_evaluations+=1
        with gzip.open(path,'wt') as f:json.dump(dict(config=config,result=result),f)
        return result
    for candidate in selected:
        cid=candidate['card_id'];fee=candidate['cost']
        for context in ('single','wide'):
            for wallet in (1,2):
                for purpose,task in TASKS.items():
                    key=(fee,context,wallet,purpose)
                    if key not in baselines:
                        basefile=f'baseline-{fee}G-{context}-{wallet}G-{purpose}.json.gz'
                        b=measure(configuration(scene([15],fee,context,wallet),task),out/basefile)
                        baselines[key]=dict(artifact=basefile,result=b)
                    config=configuration(scene([cid,15],fee,context,wallet),task)
                    file=f'card{cid}-{context}-{wallet}G-{purpose}.json.gz'
                    result=measure(config,out/file)
                    common=result['common_policy'];baseline=baselines[key]['result']['common_policy']
                    hp_delta=common['guaranteed_player_hp']-baseline['guaranteed_player_hp'] if common['guaranteed_player_hp'] is not None and baseline['guaranteed_player_hp'] is not None else None
                    row=dict(card_id=cid,name=candidate['name'],cost=fee,context=context,enemy_wallet=wallet,
                        purpose=purpose,known=result['known'],common=common,oracle=result.get('informed_world_upper_bound'),
                        information_gap_hp=result.get('information_gap_hp'),root_action=result.get('root_action'),
                        baseline_artifact=baselines[key]['artifact'],baseline=baseline,
                        same_cash_slot_hp_delta=hp_delta,artifact=file,unknown=result['unknown'],
                        information_sets=result.get('visited_information_sets'),physical_states=result.get('expanded_physical_states'))
                    rows.append(row);print(len(rows),cid,context,wallet,purpose,result['known'],common,row['information_gap_hp'],flush=True)
    assert binding==belief.sources()
    summary=dict(source_hashes=binding,rows=rows,baselines=[dict(key=list(k),artifact=v['artifact'],known=v['result']['known'],common=v['result']['common_policy']) for k,v in baselines.items()],
        actual_belief_evaluations=core_evaluations,measured_cards=len(selected),seconds=time.time()-start,
        scope='Candidate is one slot next to an identical Aaron background, same cash within each printed fee. '
            'Quotes concern the complete declared hand; baseline removes only candidate, retaining cash. '
            'All enemy attack/cast orders, holds and future deployment choices are included. '
            'Both hidden spells explicitly Generated; earlier Bone Box outcome privacy is a caller hypothesis, not server evidence.')
    (out/'index.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
