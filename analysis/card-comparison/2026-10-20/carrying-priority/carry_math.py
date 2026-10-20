"""Analytical carrying constraints, without a deck proposal or meta prior."""
from math import comb
from pathlib import Path
import argparse,json,sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from package_model import income,integer


def natural_total(turn,seat):
    return 1+sum(income(n,seat) for n in range(1,turn+1))


def anchor_margin(cost,seat):
    integer(cost,'actual anchor cost',1,30)
    turn=next(n for n in range(1,11) if natural_total(n,seat)>=cost)
    return dict(cost=cost,seat=seat,earliest_own_turn=turn,
                gross_gold=natural_total(turn,seat),
                earlier_net_spend_without_delaying=natural_total(turn,seat)-cost,
                limitation='Funds only: card must have arrived and board/targets must permit its use; no extra income')


def choose(n,k):return comb(n,k) if n>=k>=0 else 0


def opener_probability(effective_cards,seen,total=25):
    integer(effective_cards,'effective opener count',0,total);integer(seen,'cards seen',0,total)
    return 1-choose(total-effective_cards,seen)/choose(total,seen)


def blocked_probability(blocked_cards,seen,at_least=3,total=25):
    integer(blocked_cards,'blocked card count',0,total);integer(seen,'cards seen',0,total)
    integer(at_least,'blocked threshold',0,seen)
    return sum(choose(blocked_cards,k)*choose(total-blocked_cards,seen-k)
               for k in range(at_least,seen+1))/choose(total,seen)


def flow_bound(cost_cap,turn,seat,extra_cards=0):
    integer(cost_cap,'actual cost cap',0,30);integer(extra_cards,'extra arriving usable cards',0,25)
    seen=min(25,3+turn+extra_cards)
    gross=natural_total(turn,seat)
    return dict(actual_cost_cap=cost_cap,turn=turn,seat=seat,maximum_seen_cards=seen,
                maximum_possible_spending=min(gross,cost_cap*seen),
                minimum_unspent_gold=max(0,gross-cost_cap*seen),
                limitation='Excludes extra draws/additions/replay/Program/other expenditure; ignores board crowding, so this spending ceiling is generous')


def summary():
    probabilities=[dict(effective_openers=k,seen=s,probability=opener_probability(k,s))
                   for s in (3,4) for k in (4,6,8,10,11)]
    required=[dict(seen=s,target=p,minimum_effective_openers=next(k for k in range(26) if opener_probability(k,s)>=p))
              for s in (3,4) for p in (.7,.8,.9)]
    return dict(assessment_kind='heuristic_constraints',anchors=[anchor_margin(c,seat)
                for seat in ('first','second') for c in (2,3,5,6,7,9,11,12)],
                opener_probabilities=probabilities,opener_count_conditions=required,
                blocked_opening=[dict(unavailable_cards=k,seen=4,probability_at_least_three=blocked_probability(k,4))
                                 for k in (4,6,8,10,12)],
                long_game_flow=[flow_bound(c,10,seat) for seat in ('first','second') for c in (2,3,4,5)],
                assumptions=['Uniform shuffle without replacement; no mulligan model or measured metagame frequencies',
                             'An effective opener must be useful under the declared target, not merely cheap enough',
                             'Initial hand3; normal draw1 at each own turn including t1 is a disclosed convention',
                             'Counts are conditional constraints, not a recommended final deck composition'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--anchor-cost',type=int);p.add_argument('--seat',choices=('first','second'),default='first')
    p.add_argument('--effective-openers',type=int);p.add_argument('--seen',type=int,default=4)
    args=p.parse_args()
    try:
        if args.anchor_cost is not None:out=anchor_margin(args.anchor_cost,args.seat)
        elif args.effective_openers is not None:out=dict(probability=opener_probability(args.effective_openers,args.seen),
                 condition='Uniform shuffle, no mulligan; effectiveness is a user-supplied property')
        else:out=summary()
    except (ValueError,StopIteration) as error:p.error(str(error))
    print(json.dumps(out,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
