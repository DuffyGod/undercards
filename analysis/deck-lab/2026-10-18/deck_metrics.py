"""Exact structural deck probes, never a match or spending-policy simulator.

The source deck contains non-Generated physical copies. Uniform removed-card
samples and uniform current-hand samples are DIFFERENT declared experiments.
No mulligan, hand-retention policy, generated-card dilution, or burn inference.
"""
from collections import Counter, defaultdict
import argparse
import hashlib
import json
from math import comb
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BOOKSHELF = '466'
LIBRARIAN = '185'


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(name+' must be an integer >= '+str(minimum))
    return value


def normalize_counts(counts):
    if not isinstance(counts,dict):raise ValueError('Physical card counts must be a mapping')
    out=Counter()
    for cid,count in counts.items():
        integer(count,'copy count')
        if count:out[str(cid)]+=count
    if not out:raise ValueError('Nonempty source deck required')
    return dict(out)


def choose(n,k):
    return comb(n,k) if 0 <= k <= n else 0


def sample_size(counts,seen):
    integer(seen,'sample size')
    n=sum(counts.values())
    if seen>n:raise ValueError('Sample exceeds the physical source deck')
    return n


def probability_at_least(population,successes,draws,minimum=1):
    for value,name in ((population,'population'),(successes,'successes'),(draws,'draws'),(minimum,'minimum')):
        integer(value,name)
    if successes>population or draws>population:raise ValueError('Invalid hypergeometric population/sample')
    denominator=choose(population,draws)
    return sum(choose(successes,k)*choose(population-successes,draws-k)
               for k in range(minimum,min(successes,draws)+1))/denominator


def removed_event_probability(counts,removed,minimum_removed):
    """Exact physical-subset count for simultaneously seeing specified copies."""
    counts=normalize_counts(counts);n=sample_size(counts,removed)
    required={str(k):integer(v,'required copies') for k,v in minimum_removed.items()}
    if any(v>counts.get(k,0) for k,v in required.items()):return 0.
    required={k:v for k,v in required.items() if v}
    dp={0:1}
    involved=sum(counts[k] for k in required)
    for cid,minimum in required.items():
        nxt=defaultdict(int);copies=counts[cid]
        for used,ways in dp.items():
            for take in range(minimum,min(copies,removed-used)+1):
                nxt[used+take]+=ways*choose(copies,take)
        dp=dict(nxt)
    favorable=sum(ways*choose(n-involved,removed-used) for used,ways in dp.items())
    return favorable/choose(n,removed)


def pair_access_probability(counts,removed,left,right):
    """Same-name pair requires TWO physical copies, never one counted twice."""
    left,right=str(left),str(right)
    required={left:2} if left==right else {left:1,right:1}
    return removed_event_probability(counts,removed,required)


def librarian_need(counts,removed,focal=LIBRARIAN):
    """Need concerns ONLY the remaining source deck, not initial singletonness.

    'seen' means in the uniformly removed subset, not still held/affordable.
    Generated additions and subsequent deck edits require a different source.
    """
    counts=normalize_counts(counts);n=sample_size(counts,removed);focal=str(focal)
    dp={(0,True,False):1}
    for cid,copies in counts.items():
        nxt=defaultdict(int)
        for (used,unique,seen),ways in dp.items():
            for take in range(min(copies,removed-used)+1):
                key=(used+take,unique and copies-take<=1,seen or (cid==focal and take>0))
                nxt[key]+=ways*choose(copies,take)
        dp=dict(nxt)
    denominator=choose(n,removed)
    need=sum(ways for (used,unique,seen),ways in dp.items() if used==removed and unique)
    focal_seen=sum(ways for (used,unique,seen),ways in dp.items() if used==removed and seen)
    joint=sum(ways for (used,unique,seen),ways in dp.items() if used==removed and unique and seen)
    return dict(removed=removed,p_need=need/denominator,p_focal_seen=focal_seen/denominator,
                p_seen_and_need=joint/denominator,
                p_need_given_focal_seen=joint/focal_seen if focal_seen else None,
                favorable_subsets=joint,total_subsets=denominator)


def bookshelf_metrics(counts,removed,spell_ids=(),focal=BOOKSHELF):
    """Bookshelf access/Need: all original non-Generated spells must be gone.

    Generated spells do not break the Need. Its chosen spell is ADDED, not
    drawn, and this module assigns no spell-choice or -2COST monetary value.
    """
    counts=normalize_counts(counts);n=sample_size(counts,removed);focal=str(focal)
    spells={str(cid) for cid in spell_ids}
    if focal in spells:raise ValueError('Bookshelf cannot also be a spell')
    required={cid:copies for cid,copies in counts.items() if cid in spells}
    p_need=removed_event_probability(counts,removed,required)
    p_seen=probability_at_least(n,counts.get(focal,0),removed)
    joint=removed_event_probability(counts,removed,dict(required,**{focal:1}))
    return dict(removed=removed,p_seen=p_seen,p_need=p_need,p_seen_and_need=joint,
                p_need_given_seen=joint/p_seen if p_seen else None)


def income(turn,first):
    integer(turn,'own-turn number',1)
    if type(first) is not bool:raise ValueError('first must explicitly be True/False')
    return min(turn,10)+int(not first and turn<=9 and turn%2==1)


def gold_path(horizon,first,spending=()):
    """Retained basic Gold with an EXOGENOUS declared payment prefix.

    Omitted payments are zero: that is a stated no-spend ceiling, not an
    assumed optimal curve. No Soul/artifact/card income or discounts included.
    """
    integer(horizon,'horizon',1)
    if len(spending)>horizon:raise ValueError('Payment prefix exceeds horizon')
    for paid in spending:integer(paid,'payment')
    gold=1;rows=[]
    for turn in range(1,horizon+1):
        gold+=income(turn,first)
        paid=spending[turn-1] if turn<=len(spending) else 0
        if paid>gold:raise ValueError('Infeasible payment at own turn '+str(turn))
        rows.append(dict(turn=turn,income=income(turn,first),gold_before=gold,
                         payment=paid,gold_after=gold-paid))
        gold-=paid
    return rows


def hand_budget_probabilities(cost_counts,hand,cash):
    """Uniform current physical hand, exact single/two-card payment events.

    This is NOT a post-spending hand distribution. It knows no board, targets,
    timing or combo rules. Two cheapest copies establish pair affordability.
    """
    integer(hand,'current hand size');integer(cash,'cash')
    if hand>7:raise ValueError('Current hand exceeds the seven-card limit')
    costs=Counter()
    for cost,copies in cost_counts.items():
        integer(cost,'printed cost');integer(copies,'cost multiplicity')
        if copies:costs[cost]+=copies
    n=sum(costs.values())
    if hand>n:raise ValueError('Hand exceeds the source multiset')
    dp={(0,()):1}
    for cost,copies in sorted(costs.items()):
        nxt=defaultdict(int)
        for (used,cheapest),ways in dp.items():
            for take in range(min(copies,hand-used)+1):
                low=tuple(sorted(cheapest+(cost,)*take)[:2])
                nxt[used+take,low]+=ways*choose(copies,take)
        dp=dict(nxt)
    denominator=choose(n,hand)
    single=pair=mass=0
    for (used,low),ways in dp.items():
        if used!=hand:continue
        mass+=ways
        if low and low[0]<=cash:single+=ways
        if len(low)==2 and sum(low)<=cash:pair+=ways
    if mass!=denominator:raise AssertionError('Physical hand probability mass lost')
    return dict(hand=hand,cash=cash,p_affordable_single=single/denominator,
                p_affordable_two=pair/denominator,
                expected_affordable_copies=hand*sum(c for cost,c in costs.items() if cost<=cash)/n if n else 0.)


def interaction_metrics(counts,removed,interaction_ids):
    counts=normalize_counts(counts);n=sample_size(counts,removed)
    chosen={str(cid) for cid in interaction_ids}
    k=sum(copies for cid,copies in counts.items() if cid in chosen)
    return dict(interaction_copies=k,interaction_density=k/n,removed=removed,
                p_seen_at_least_one=probability_at_least(n,k,removed),
                p_seen_at_least_two=probability_at_least(n,k,removed,2),
                expected_seen=removed*k/n)


def structural_report(counts,cards,*,seen_counts,hand_sizes,turns,interaction_ids=(),spending=()):
    """One declared grid, no default starting-hand/mulligan assumption."""
    counts=normalize_counts(counts)
    if sum(counts.values())!=25:raise ValueError('Undercards constructed source must contain 25 physical cards')
    if any(cid not in cards for cid in counts):raise ValueError('Unknown source-card ID')
    if not turns:raise ValueError('Explicit own-turn grid required')
    for turn in turns:integer(turn,'own-turn number',1)
    cost_counts=Counter()
    for cid,copies in counts.items():cost_counts[cards[cid]['cost']]+=copies
    spells={cid for cid in counts if cards[cid]['card_type']=='spell'}
    draws=[dict(removed=n,bookshelf=bookshelf_metrics(counts,n,spells),
                librarian=librarian_need(counts,n),
                interactions=interaction_metrics(counts,n,interaction_ids)) for n in seen_counts]
    gold=[];budgets=[]
    for first in (True,False):
        rows=gold_path(max(turns),first,spending)
        for row in rows:
            if row['turn'] not in turns:continue
            gold.append(dict(first=first,**row))
            for hand in hand_sizes:
                budgets.append(dict(first=first,turn=row['turn'],
                    **hand_budget_probabilities(cost_counts,hand,row['gold_before'])))
    return dict(deck_counts=counts,cost_counts=dict(sorted(cost_counts.items())),
        unique_names=len(counts),extra_duplicate_copies=sum(c-1 for c in counts.values()),
        repeated_names={k:v for k,v in counts.items() if v>1},seen_grid=draws,
        gold_path=gold,uniform_hand_budget_grid=budgets,
        assumptions=['Initial 25 physical cards are non-Generated; exact random subsets without mulligan.',
            'Removed/seen copies are not guaranteed still held, unburned, or affordable.',
            'Current-hand cost samples are separate unconditioned structural probes, not leftovers after the payment prefix.',
            'Gold uses base income/retention and an explicit exogenous payment prefix; missing payments mean zero.',
            'Pair budgets need two physical cards and ordinary payment only; no target, board or survival feasibility.',
            'Need checks remaining deck; generated additions, extra draws and deck edits are not simulated.',
            'Interaction labels are caller declared, not empirical card quality; rarity/Soul/artifact legality is not certified.'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deck',type=Path,required=True,help='JSON {counts:{card_id:copies},interaction_ids:[...]}')
    parser.add_argument('--seen',type=int,nargs='+',required=True)
    parser.add_argument('--hands',type=int,nargs='+',required=True)
    parser.add_argument('--turns',type=int,nargs='+',required=True)
    parser.add_argument('--spending',type=int,nargs='*',default=[])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    source=ROOT/'skills/undercards/references/snapshot.json'
    snapshot=json.loads(source.read_text(encoding='utf-8'))
    cards={str(c['id']):c for c in snapshot['cards']}
    deck=json.loads(args.deck.read_text(encoding='utf-8'))
    report=structural_report(deck['counts'],cards,seen_counts=args.seen,hand_sizes=args.hands,
        turns=args.turns,interaction_ids=deck.get('interaction_ids',[]),spending=args.spending)
    report['source_sha256']={str(source):hashlib.sha256(source.read_bytes()).hexdigest(),
        str(args.deck):hashlib.sha256(args.deck.read_bytes()).hexdigest(),
        'deck_metrics.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    text=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(text,encoding='utf-8')
    else:print(text,end='')


if __name__=='__main__':main()
