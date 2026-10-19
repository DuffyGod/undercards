"""Read saved single-card conditional results; never build a deck or call API."""
from itertools import combinations
from pathlib import Path
import argparse
import gzip
import json

from frontier import paired_range, diagnose_pair, mixture, piece_at, value, single_use_opportunity_bounds, TOL
from run_study import case_id
from response_window import compare_reply_set

HERE = Path(__file__).resolve().parent


def compare(data, design, ids, menu, board, cash, slots, price_setting='all',
            cash_price=None, second_board=None):
    if len(ids) < 2 or len(ids) != len(set(ids)):
        raise ValueError('Provide at least two distinct focal card IDs')
    if any(cid not in design['candidate_ids'] for cid in ids):
        raise ValueError('Candidate not in this declared short-window support; do not substitute zero')
    key = case_id(menu, board, cash, slots)
    if key not in data:
        raise ValueError('No frozen result at this EXACT background/board/cash/slots condition')
    selected = data[key]['settings']
    if price_setting != 'all':
        if price_setting not in selected:
            raise ValueError('Price setting is not in this saved study')
        selected = {price_setting:selected[price_setting]}
    condition = dict(background_ids=design['background_menus'][menu], menu=menu,
                     board=board, cash=cash, available_slots=slots,
                     cash_price=cash_price if cash_price is not None else [0, 1],
                     shared_price_settings=list(selected))
    comparison = [dict(left=a, right=b, **diagnose_pair(selected, a, b, cash_price))
                  for a, b in combinations(ids, 2)]
    cards = []
    for cid in ids:
        gain = paired_range(selected, cid, 'background', cash_price)
        replacement = paired_range(selected, cid, 2, cash_price)
        row = dict(id=cid, name=design['names'][str(cid)],
                   current_gain_over_background=gain,
                   current_replacement_relative_to_froggit=replacement,
                   current_replacement_loss_range=[max(0., -replacement['maximum']),
                                                   max(0., -replacement['minimum'])],
                   multi_turn_holding_cost_identified=False)
        if cash_price is not None and len(selected) == 1:
            curves = next(iter(selected.values()))
            p = piece_at(curves[str(cid)], cash_price)
            strict = value(curves[str(cid)], cash_price) > value(curves['background'], cash_price) + TOL
            if not strict:
                p = piece_at(curves['background'], cash_price)
            row['one_optimal_current_plan'] = p.get('action', 'Condition on the publicly observed source board')
            row['focal_required_for_strict_gain'] = strict
            row['plan_may_be_nonunique'] = True
            row['menu_paid_or_design_mean_paid'] = -p['slope']
            row['net_menu_value'] = value(curves[str(cid)], cash_price)
        cards.append(row)
    output = dict(assessment_kind='heuristic', empirically_calibrated=False,
                  condition=condition, cards=cards, comparisons=comparison,
                  scope=dict(current_deadline=True, future_special_abilities_priced=False,
                             opponent_response=False, player_survival_evaluated=False,
                             real_world_opportunity_frequency_identified=False,
                             parameter_ranges_are_finite_designs=True,
                             empty_target_legality='Inherited sparse-menu assumption when applicable; not independently server validated',
                             equality_may_hide_future_ability_differences=True),
                  source='results/curves.json.gz; design.json identifies frozen source revision')
    if second_board is not None:
        second_key = case_id(menu, second_board, cash, slots)
        if second_key not in data:
            raise ValueError('Second board must have the same declared resource/background support')
        second = data[second_key]['settings']
        if price_setting != 'all':
            second = {price_setting:second[price_setting]}
        output['two_board_opportunity_conditions'] = dict(
            first_board=board, second_board=second_board,
            interpretation='Select focal card before the board is revealed; q is SECOND-board mass, not a temporal arrival model',
            comparisons=[dict(left=a, right=b, **mixture(selected, second, a, b, cash_price))
                         for a, b in combinations(ids, 2)])
    return output


def compare_saved_reply(data,design,ids,case,price_setting='all',cash_price=None):
    if len(ids)<2 or len(set(ids))!=len(ids) or any(i not in design['candidate_ids'] for i in ids):
        raise ValueError('Use at least two distinct supported focal IDs; excluded effects are not zero')
    if case not in data:raise ValueError('No saved response window under that name')
    selected=data[case]
    if price_setting!='all':
        if price_setting not in selected:raise ValueError('Unknown shared price setting')
        selected={price_setting:selected[price_setting]}
    pairs=[dict(left=a,right=b,**compare_reply_set(selected,a,b,cash_price)) for a,b in combinations(ids,2)]
    cards=[]
    for cid in ids:
        first=next(iter(selected.values()))[str(cid)]
        row=dict(id=cid,name=design.get('names',{}).get(str(cid)),shared_goal_feasible=first['guarantee_feasible'],
                 enabled_goal_when_background_cannot=first.get('enabled_goal_when_background_cannot',first['enabled_survival_when_background_cannot']),
                 enabled_survival_when_background_cannot=first['enabled_survival_when_background_cannot'])
        if first['guarantee_feasible'] and first['background_curve'] is not None:
            curves={s:{'c':r[str(cid)]['curve'],'b':r[str(cid)]['background_curve']} for s,r in selected.items()}
            row['current_gain_over_feasible_background']=paired_range(curves,'c','b',cash_price)
        else:
            row['current_gain_over_feasible_background']=None
        if 'defense_removed_control' in first and first['guarantee_feasible']:
            control=first['defense_removed_control']
            if not control['guarantee_feasible']:
                row['defense_enables_shared_goal']=True
                row['defense_value_vs_same_body_without_keyword']=None
            else:
                curves={s:{'yes':r[str(cid)]['curve'],'no':r[str(cid)]['defense_removed_control']['curve']}
                        for s,r in selected.items()}
                row['defense_enables_shared_goal']=False
                row['defense_value_vs_same_body_without_keyword']=paired_range(curves,'yes','no',cash_price)
        cards.append(row)
    return dict(assessment_kind='heuristic',empirically_calibrated=False,
                case=case,condition=design['cases'][case],
                initial_friendly_board='empty/four free slots',enemy_hero_hp=30,
                cash_price=cash_price if cash_price is not None else [0,1],
                shared_price_settings=list(selected),cards=cards,comparisons=pairs,
                scope='Only the declared one ordinary enemy optional-attack window; not full-turn or match safety',
                infeasible_policy='No numeric fallback when the shared HP/body-retention goal is infeasible',
                trace_warning='Lowest hero HP and lowest asset value can have different enemy-reply witnesses')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    c = sub.add_parser('compare')
    c.add_argument('--ids', nargs='+', type=int, required=True)
    c.add_argument('--menu', choices=('two_plain', 'three_plain', 'four_plain'), default='three_plain')
    c.add_argument('--board', required=True)
    c.add_argument('--cash', required=True, type=int)
    c.add_argument('--slots', required=True, type=int)
    c.add_argument('--price-setting', default='all')
    c.add_argument('--cash-price', type=float)
    c.add_argument('--second-board')
    c.add_argument('--results', type=Path, default=HERE/'results')
    r = sub.add_parser('reply')
    r.add_argument('--ids',nargs='+',type=int,required=True)
    r.add_argument('--case',required=True)
    r.add_argument('--price-setting',default='all')
    r.add_argument('--cash-price',type=float)
    r.add_argument('--results',type=Path,default=HERE/'reply-results')
    b = sub.add_parser('opportunity-bounds')
    b.add_argument('--reward', type=float, required=True)
    b.add_argument('--marginals', type=float, nargs='+', required=True)
    b.add_argument('--reference-value', type=float, required=True)
    args = p.parse_args()
    try:
        if args.command == 'opportunity-bounds':
            out = single_use_opportunity_bounds(args.reward, args.marginals, args.reference_value)
        elif args.command == 'reply':
            with gzip.open(args.results/'reply-curves.json.gz','rt',encoding='utf-8') as f:data=json.load(f)
            design=json.loads((args.results/'design.json').read_text(encoding='utf-8'))
            out=compare_saved_reply(data,design,args.ids,args.case,args.price_setting,args.cash_price)
            out['numerical_producer_commit']=design['producer_source_commit']
        else:
            with gzip.open(args.results/'curves.json.gz', 'rt', encoding='utf-8') as f:
                data = json.load(f)
            design = json.loads((args.results/'design.json').read_text(encoding='utf-8'))
            out = compare(data, design, args.ids, args.menu, args.board, args.cash, args.slots,
                          args.price_setting, args.cash_price, args.second_board)
            out['source'] = dict(curves=str(args.results/'curves.json.gz'),
                                 input_checkout_commit=design.get('input_checkout_commit'),
                                 numerical_producer_commit=design.get('producer_source_commit'))
    except (ValueError, KeyError, FileNotFoundError) as e:
        p.error(str(e))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
