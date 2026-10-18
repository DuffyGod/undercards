"""Exact answer-access rates over declared uniform hands and short lines.

This is not a deck score, win rate, optimal turn solver, or match simulator.
"""
from pathlib import Path
import gzip
import hashlib
import json
from math import comb
import deck_metrics as dm
import immediate_exchange as ie

HERE=Path(__file__).resolve().parent
NAMES=['A_early','A_quality_bookshelf','A_safe_slots','B_library_singletons']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def produce():
    cards=ie.source_cards();rows=[];sources={}
    for name in NAMES:
        path=HERE/(name+'.json');deck=json.loads(path.read_text(encoding='utf8'));sources[name]=sha(path)
        assert deck['soul']=='JUSTICE','Justice Bookshelf branch cannot be applied to another SOUL'
        assert all(int(i) in ie.CARD_IDS for i in deck['counts'])
        for hand in [3,5,7]:
            for power in [0,1]:
                for target,stats in ie.TARGETS.items():
                    for cash in [3,4,5,6,7,10]:
                        clear_ids=ie.clear_coverage(ie.target_body(*stats),cash=cash,hand_before=hand,power=power,cards=cards)
                        k=sum(n for i,n in deck['counts'].items() if int(i) in clear_ids)
                        favorable=comb(25,hand)-dm.choose(25-k,hand)
                        rows.append({'deck':name,'hand':hand,'power_counter_spent_on_source':power,
                            'target':target,'enemy':stats,'cash':cash,'clearing_physical_copies':k,
                            'clearing_source_ids':[int(i) for i in deck['counts'] if int(i) in clear_ids],
                            'favorable_uniform_hands':favorable,'all_uniform_hands':comb(25,hand),
                            'p_short_answer_in_uniform_original_hand':favorable/comb(25,hand)})
    report={'assumptions':[
        'Four empty own slots and ONE bare ordinary enemy; no other allies or enemies. Injured_large starts6/4 max7.',
        'Uniform current hand of h original physical copies from25, not an observed midgame hand distribution.',
        'Only one source Play, its Magic, optionally one Haste attack, own turn end; Bookshelf alone may also buy/cast its generated spell.',
        'No existing friendly attacker, other original hand plays, opponent response, face pressure, fatigue, or terminal life check.',
        'Need is met in the relevant deck, library has at least3 drawable cards, no deck edits except Generated source effects.',
        'Justice passive is NOT stacked on target bodies; this isolates the cards. Power0=no counter; Power1=one known counter, never a random proc.',
        'Clear means enemy gone this turn; friendly survival, health, death yields, and debts remain separate ledger fields, not an equal-quality win.',
        'Recorded paths are a restricted action subset; answer access is not full multi-card answer coverage or game success.'
    ],'sources':{'decks':sources,'snapshot':sha(ie.SOURCE),'immediate_exchange.py':sha(HERE/'immediate_exchange.py'),
        'deck_metrics.py':sha(HERE/'deck_metrics.py'),'producer':sha(Path(__file__))},'rows':rows}
    dump(HERE/'answer-access.json',report)
    matrix_bytes=(HERE/'answer-access.json').read_bytes()
    (HERE/'answer-access.json.gz').write_bytes(gzip.compress(matrix_bytes,mtime=0))
    ledgers=[]
    for target,stats in ie.TARGETS.items():
        for hand in [3,5,7]:
            for cid in ie.CARD_IDS:
                ledgers.append({'target':target,'hand_before':hand,'cash':10,'power':0,
                    'options':ie.exchange_options(cid,ie.target_body(*stats),hand_before=hand,cash=10,power=0,cards=cards)})
    payload=json.dumps({'assumptions':report['assumptions'],'sources':report['sources'],'ledgers':ledgers},ensure_ascii=False,separators=(',',':')).encode('utf8')
    (HERE/'exchange-ledgers.json.gz').write_bytes(gzip.compress(payload,mtime=0))
    # A legibility-oriented compact projection; never converted to an overall score.
    compact=[r for r in rows if r['hand']==5 and r['power_counter_spent_on_source']==0
        and ((r['cash']==3 and r['target']=='icecap') or (r['cash']==4 and r['target']=='vulkin')
            or (r['cash']==6 and r['target'] in ['vulkin','five','injured_large','large'])
            or (r['cash']==10 and r['target']=='large'))]
    dump(HERE/'answer-access-compact.json',compact)
    for r in compact:
        print(r['deck'],r['target'],'G'+str(r['cash']),r['clearing_physical_copies'],round(100*r['p_short_answer_in_uniform_original_hand'],2))

if __name__=='__main__':produce()
