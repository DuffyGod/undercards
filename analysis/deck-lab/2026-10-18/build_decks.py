"""Root-owned deck decisions and deterministic structural comparisons.

LLM votes and rankings are deliberately not inputs to this producer.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import deck_metrics as dm

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SNAPSHOT=ROOT/'skills/undercards/references/snapshot.json'

A={932:2,373:1,869:1,602:1,111:2,436:2,225:2,20:2,468:1,54:1,
   148:1,291:1,469:1,509:1,951:1,466:2,984:1,391:1,530:1}
B={185:2,932:1,373:1,869:1,602:1,166:1,111:1,436:1,225:1,22:1,
   53:1,20:1,468:1,54:1,148:1,291:1,13:1,469:1,509:1,951:1,
   466:1,984:1,391:1,530:1}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def swap(counts,outgoing,incoming):
    counts=dict(counts);counts[outgoing]-=1
    if not counts[outgoing]:del counts[outgoing]
    counts[incoming]=counts.get(incoming,0)+1
    return counts

def certify(counts,cards,artifacts):
    assert sum(counts.values())==25
    limits={'BASE':3,'COMMON':3,'RARE':3,'EPIC':2,'LEGENDARY':1,'DETERMINATION':1}
    for cid,n in counts.items():
        c=cards[str(cid)]
        assert type(n) is int and 1<=n<=limits[c['rarity']],(cid,n,c['rarity'])
        assert c['pool_category']=='ordinary_non_token' and c['card_type']=='monster'
    assert sum(n for cid,n in counts.items() if cards[str(cid)]['rarity']=='DETERMINATION')<=1
    assert len(artifacts)==2 and all(a['selectable_by_observed_flags'] and not a['metadata']['legendary'] for a in artifacts)
    return {'physical_copies':25,'ordinary_monsters_only':True,'rarity_limits_pass':True,
        'ranked_dt_limit_pass':True,'two_selectable_regular_artifacts':True}

def produce():
    snapshot=json.loads(SNAPSHOT.read_text(encoding='utf8'));cards={str(c['id']):c for c in snapshot['cards']}
    artifacts=[a for a in snapshot['artifacts'] if a['id'] in (1,4)]
    drafts=HERE/'drafts';drafts.mkdir(exist_ok=True)
    for name in ['A_quality_bookshelf','B_library_singletons']:
        previous=HERE/(name+'.json')
        if previous.exists() and not (drafts/(name+'_v0.json')).exists():
            previous_data=json.loads(previous.read_text(encoding='utf8'))
            if previous_data.get('status')=='root_draft_pending_review':dump(drafts/(name+'_v0.json'),previous_data)
    decisions=[('A_quality_bookshelf',A,'JUSTICE','Primary quality baseline; one Archer replaced by Piranhas to diversify low-hand failure.'),
        ('B_library_singletons',B,'JUSTICE','Only Librarian duplicated; complete alternate package, not a causal estimate of Librarian alone.'),
        ('A_safe_slots',swap(A,951,509),'JUSTICE','Controlled same-cost swap: Fire Fountain out, second Long Sink in; loses the 5-ATK immediate threshold.'),
        ('A_early',swap(A,951,373),'JUSTICE','Controlled early-pressure swap: Fire Fountain out, second Worm in; adds one 2G answer and loses the 5-ATK immediate threshold.'),
        ('A_kindness',swap(A,951,373),'KINDNESS','Identical 25 cards to A_early and the same artifacts; SOUL change tests passive healing and Bookshelf draw-three at total 8G.')]
    summaries={}
    for name,counts,soul,note in decisions:
        legality=certify(counts,cards,artifacts)
        deck={'id':name,'status':'root_reviewed_research_list_not_match_validated','snapshot':'2026-10-05',
            'soul':soul,'artifacts':[1,4],'counts':{str(i):n for i,n in counts.items()},'decision':note,
            'legality':legality,'source_sha256':sha(SNAPSHOT)}
        dump(HERE/(name+'.json'),deck)
        report=dm.structural_report(deck['counts'],cards,seen_counts=[4,5,6,7,8,10],
            hand_sizes=[4,5,6],turns=[1,2,3,4,5],spending=[2,2,3,4,5])
        report['notes']=['Printed-cost probes omit extra gold/artifact gains; these four decks use no gold-altering SOUL in the probe.',
            'Payment prefix [2,2,3,4,5] is feasible but exogenous, not guaranteed by a sampled hand.',
            'Uniform current hands are a separate experiment, not conditioned leftovers of that payment prefix.']
        report['source_sha256']={'snapshot':sha(SNAPSHOT),'deck':sha(HERE/(name+'.json')),'producer':sha(Path(__file__)),'deck_metrics':sha(HERE/'deck_metrics.py')}
        dump(HERE/(name+'.metrics.json'),report)
        cost_counts=Counter()
        for cid,n in deck['counts'].items():cost_counts[cards[cid]['cost']]+=n
        low=sum(n for c,n in cost_counts.items() if c<=3);two=cost_counts[2]
        summaries[name]={'soul':soul,'count':25,'cost_counts':dict(sorted(cost_counts.items())),
            'average_cost':sum(c*n for c,n in cost_counts.items())/25,'unique_names':len(counts),
            'two_cost_copies':two,'cost_le3_copies':low,
            'p_seen_two_cost_n4':dm.probability_at_least(25,two,4),
            'p_seen_cost_le3_n4':dm.probability_at_least(25,low,4),
            'uniform_h5_two_plays':{str(g):dm.hand_budget_probabilities(cost_counts,5,g)['p_affordable_two'] for g in [3,4,5,6,7,8,9]},
            'ceiling_access':[]}
        for n in [4,6,8,10]:
            engine=sum(deck['counts'].get(str(i),0) for i in [185,466])
            summaries[name]['ceiling_access'].append({'seen':n,
                'p_any_book_or_library':dm.probability_at_least(25,engine,n),
                'bookshelf':dm.bookshelf_metrics(deck['counts'],n,set()),
                'librarian':dm.librarian_need(deck['counts'],n)})
    # Isolate just the duplicate-barrier cost, independent of full deck strength.
    singleton={'185':2,**{str(i):1 for i in range(10000,10023)}}
    double_pair={'185':2,'466':2,**{str(i):1 for i in range(10000,10021)}}
    summaries['duplicate_barrier_only']={str(n):{'only_two_lib':dm.librarian_need(singleton,n),
        'lib_plus_book_pair':dm.librarian_need(double_pair,n)} for n in [4,5,6,7,8,10]}
    summaries['gold_path_exogenous']={str(first):dm.gold_path(5,first,[2,2,3,4,5]) for first in [True,False]}
    dump(HERE/'structural-comparison.json',summaries)
    ids={str(i) for _,counts,_,_ in decisions for i in counts}
    refs={str(r) for i in ids for r in cards[i].get('card_references',[]) if str(r) in cards}
    dump(HERE/'selected-source.json',{'snapshot_provenance':snapshot['provenance'],
        'cards':[cards[i] for i in sorted(ids,key=int)],'referenced_cards':[cards[i] for i in sorted(refs-ids,key=int)],
        'soul_spells':[c for c in snapshot['cards'] if c.get('soul') in ['JUSTICE','KINDNESS'] and c.get('card_type')=='spell' and c.get('pool_category')=='ordinary_non_token'],
        'artifacts':[a for a in snapshot['artifacts'] if a['id'] in [1,2,4,12,53,61]],'mechanics':snapshot['mechanics']})
    print(json.dumps(summaries,ensure_ascii=False,indent=2))
if __name__=='__main__':produce()
