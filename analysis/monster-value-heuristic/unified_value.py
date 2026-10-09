"""Common-state reservation quotes and deployment diagnostics, not match simulation.

Every card keeps the same profile weights, even when presently unaffordable.
Quotes do not manufacture a legal play or a Gold payment. Only extra waiting
before deployment is discounted; ordinary attack/Dust delay is already in the
underlying ledger. Unknown effects leave the whole-card headline empty.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import context_value as ledger
import heuristic_contexts as contexts
import score_cards as base

VERSION='common-state-reservation-0.3.1'
HERE=Path(__file__).resolve().parent
ROLES=contexts.ROLES
DEFAULT_PROFILE={
    'name':'generic_fixed_panel',
    'role_weights':{r:.25 for r in ROLES},
    'phase_weights':{'3':1/3,'5':1/3,'8':1/3},
    'resource_state_weights':{'deployed':.5,'reserved':.5},
    'joint_resource_weights':None,
    'resource_joint_samples':None,
    'second_player':False,
    'board_weights':{
        'aggro':{'pressured':.60,'contested':.35,'clear':.05},
        'control':{'pressured':.15,'contested':.35,'clear':.50},
        'combo':{'pressured':.05,'contested':.15,'clear':.80},
        'midrange':{'pressured':.25,'contested':.50,'clear':.25}},
    'delay_rate':{'aggro':.30,'control':.15,'combo':.35,'midrange':.20},
    'burn_option_multiplier':1.,
    'natural_draws_per_wait_turn':1,
    'other_plays_per_wait_turn':0,
    'future_income_available_fraction':1.,
    'reserved_gold_budget':0.,
    'maximum_extra_wait':3,
    'context_overrides':{},
}
LIMITATIONS=[
    'Normative model-G quotes, not observed Gold equivalence or win rate.',
    'Fixed synthetic boards and hands; no server simulation or future random information.',
    'Delay discounts positive gross, not nominal payment; no payment occurs when quoting an unavailable card.',
    'Waiting freezes conditional boards; hand counts follow declared draws/other uses, never future card identities.',
    'Body includes ordinary hand/slot use and attack delay; extra hand loss is additional natural burns relative to freeing one slot.',
    'Full-card headlines remain empty for unsupported text; known-term subtotals are not lower bounds.',
    'Default income fraction 1 is an optimistic cash-availability scenario; include reduced fractions for pressured decks.',
    'Construction profiles alter shared context/prior parameters, not named-card bonuses.',
    'Main reservation margin is an unclipped finite-window deployment quote, not an optimal-play prediction; the optional-use surplus is separately clipped.',
    'Beyond-window continuation value is not estimated; forced quotes retain its state weight and mark the tail boundary.',
    'Board priors are independently crossed with resource states; resource samples do not infer weaker opponents from a larger hand.',
    'Optional joint resource samples preserve all observed Gold/hand pairs; these remain conditional resource-policy samples, not candidate-identity or real-match frequencies.',
]


def number(x,name,minimum=0):
    if type(x) not in (float,int) or not math.isfinite(x) or x<minimum:
        raise ValueError(name+' must be finite and >= '+str(minimum))
    return x


def distribution(value,keys,name):
    if not isinstance(value,dict) or set(value)!=set(keys):
        raise ValueError(name+' has wrong keys')
    for x in value.values(): number(x,name)
    if abs(sum(value.values())-1)>1e-9: raise ValueError(name+' must sum to one')


def normalize_profile(data=None):
    data={} if data is None else data
    if not isinstance(data,dict) or not set(data)<=set(DEFAULT_PROFILE):
        raise ValueError('Unknown profile fields')
    p=copy.deepcopy(DEFAULT_PROFILE)
    p.update(copy.deepcopy(data))
    if not isinstance(p['name'],str): raise ValueError('Profile name must be text')
    distribution(p['role_weights'],ROLES,'role_weights')
    distribution(p['phase_weights'],('3','5','8'),'phase_weights')
    distribution(p['resource_state_weights'],('deployed','reserved'),'resource_state_weights')
    joint=p['joint_resource_weights']
    if joint is not None:
        if not isinstance(joint,dict) or set(joint)!={'3','5','8'}: raise ValueError('joint_resource_weights has wrong phases')
        for weights in joint.values(): distribution(weights,('deployed','reserved'),'joint_resource_weights')
    samples=p['resource_joint_samples']
    if samples is not None:
        if not isinstance(samples,dict) or set(samples)!={'3','5','8'}:
            raise ValueError('resource_joint_samples has wrong phases')
        for phase,items in samples.items():
            if not isinstance(items,list) or not items:
                raise ValueError('Resource samples must be a nonempty list per phase')
            seen=set()
            for item in items:
                if not isinstance(item,dict) or set(item)!={'gold_before_play','hand_size_before_play','weight'}:
                    raise ValueError('Invalid joint resource sample fields')
                gold=number(item['gold_before_play'],'sample Gold')
                hand=item['hand_size_before_play']
                if type(hand) is not int or not 1<=hand<=7:
                    raise ValueError('Sample hand must be integer 1..7')
                number(item['weight'],'sample weight')
                pair=(gold,hand)
                if pair in seen: raise ValueError('Duplicate joint resource pair')
                seen.add(pair)
            if abs(sum(item['weight'] for item in items)-1)>1e-9:
                raise ValueError('Joint resource sample weights must sum to one per phase')
    if type(p['second_player']) is not bool: raise ValueError('second_player must be boolean')
    if not isinstance(p['board_weights'],dict) or set(p['board_weights'])!=set(ROLES): raise ValueError('board_weights has wrong roles')
    for weights in p['board_weights'].values(): distribution(weights,('pressured','contested','clear'),'board_weights')
    if set(p['delay_rate'])!=set(ROLES): raise ValueError('delay_rate has wrong keys')
    for x in p['delay_rate'].values(): number(x,'delay_rate')
    number(p['burn_option_multiplier'],'burn option multiplier')
    for field in ('natural_draws_per_wait_turn','other_plays_per_wait_turn'):
        if type(p[field]) is not int or not 0<=p[field]<=7: raise ValueError(field+' must be integer 0..7')
    number(p['reserved_gold_budget'],'reserve budget')
    f=number(p['future_income_available_fraction'],'income fraction')
    if f>1: raise ValueError('Income fraction must be <=1')
    if type(p['maximum_extra_wait']) is not int or not 0<=p['maximum_extra_wait']<=10:
        raise ValueError('maximum_extra_wait must be integer 0..10')
    if not isinstance(p['context_overrides'],dict): raise ValueError('context_overrides must be a dictionary')
    return p


def make_panel(profile):
    rows=contexts.make_contexts()
    ids={s['context_id'] for s in rows}
    if not set(profile['context_overrides'])<=ids:
        raise ValueError('Unknown context ID in overrides')
    samples=profile['resource_joint_samples']
    if samples is not None:
        for changes in profile['context_overrides'].values():
            if not isinstance(changes,dict) or {'gold_before_play','hand_size_before_play'} & set(changes):
                raise ValueError('Joint samples cannot be combined with Gold/hand representative overrides')
        templates={(s['role'],s['own_turn'],s['joint_resource_state']):s for s in rows}
        rows=[]
        for role in ROLES:
            for phase,items in samples.items():
                for item in items:
                    state='reserved' if item['hand_size_before_play']>=4 else 'deployed'
                    child=copy.deepcopy(templates[role,int(phase),state])
                    child['resource_sample']=copy.deepcopy(item)
                    rows.append(child)
    allowed={'gold_before_play','opponent_gold_before_response','hand_size_before_play',
             'ally_bodies_before_play','enemy_bodies','death_event_hand_costs','actually_used_mask',
             'death_event_hand_quotes','future_payment_play_caps'}
    crossed=[]
    for s in rows:
        changes=profile['context_overrides'].get(s['context_id'],{})
        if not isinstance(changes,dict) or not set(changes)<=allowed:
            raise ValueError('Unsupported context override')
        if samples is not None and {'gold_before_play','hand_size_before_play'} & set(changes):
            raise ValueError('Joint samples cannot be combined with Gold/hand representative overrides')
        s.update(copy.deepcopy(changes))
        if samples is not None:
            s.update({k:s['resource_sample'][k] for k in ('gold_before_play','hand_size_before_play')})
        number(s['gold_before_play'],'gold before play')
        number(s['opponent_gold_before_response'],'opponent gold')
        if any(not isinstance(s[key],list) for key in ('ally_bodies_before_play','enemy_bodies')):
            raise ValueError('Boards must be lists of body records')
        ally=len(s['ally_bodies_before_play']); enemy=len(s['enemy_bodies'])
        s.update(ally_count_before_play=ally,ally_count_after_play=ally+1,
                 ally_empty_slots_before_play=4-ally,ally_empty_slots_after_play=3-ally,
                 enemy_count=enemy,enemy_empty_slots=4-enemy,other_monster_count=ally+enemy,
                 hand_size_after_play=s['hand_size_before_play']-1)
        joint=profile['joint_resource_weights']
        state_weights=joint[str(s['own_turn'])] if joint is not None else profile['resource_state_weights']
        resource_weight=s['resource_sample']['weight'] if samples is not None else state_weights[s['joint_resource_state']]
        s['weight']=(profile['role_weights'][s['role']]*profile['phase_weights'][str(s['own_turn'])]
                     *resource_weight)
        s['second_player']=profile['second_player']
        s['cumulative_base_gold_cap']=contexts.cumulative_base_gold(s['own_turn'],profile['second_player'])
        window=s['resource_use_window']
        window['base_income_in_window']=sum(contexts.base_income(t,profile['second_player']) for t in range(window['first_own_turn'],window['last_own_turn']+1))
        window['available_gold_assumption']=window['assumed_carry_gold']+window['base_income_in_window']
        for response in s['response_states']:
            response['affordable']=response['paid_cost']<=s['opponent_gold_before_response']
        contexts.validate_context(s)
        for unit in s['enemy_bodies']+s['ally_bodies_before_play']:
            if not isinstance(unit,dict) or not {'attack','health'}<=set(unit): raise ValueError('Target body fields missing')
            number(unit['attack'],'target attack'); number(unit['health'],'target health')
            if unit['health']==0: raise ValueError('Dead bodies do not occupy initial target slots')
        s['candidate_paid_cost']=None
        s['gold_after_play']=None
        # Resource state labels no longer determine the board. A measured
        # rich hand cannot silently grant a weak/empty opposing board.
        for board,ally_n,enemy_n in [('pressured',0,3),('contested',2,2),('clear',2,0)]:
            child=copy.deepcopy(s)
            targets=s['stage_target_bodies']
            child['ally_bodies_before_play']=copy.deepcopy(changes.get('ally_bodies_before_play',targets[:ally_n]))
            child['enemy_bodies']=copy.deepcopy(changes.get('enemy_bodies',targets[:enemy_n]))
            ally=len(child['ally_bodies_before_play']); enemy=len(child['enemy_bodies'])
            child.update(ally_count_before_play=ally,ally_count_after_play=ally+1,
                         ally_empty_slots_before_play=4-ally,ally_empty_slots_after_play=3-ally,
                         enemy_count=enemy,enemy_empty_slots=4-enemy,other_monster_count=ally+enemy,
                         board_state=board,resource_context_id=s['context_id'],context_id=s['context_id']+'-'+board)
            if samples is not None:
                child['context_id']=s['context_id']+'-g'+str(s['gold_before_play'])+'-h'+str(s['hand_size_before_play'])+'-'+board
            child['weight']=s['weight']*profile['board_weights'][s['role']][board]
            contexts.validate_context(child)
            crossed.append(child)
    return crossed


def affordability(card,s,profile):
    """Additional cash wait, not a decision to actually execute a future play."""
    cost=card['cost']; actual=s['gold_before_play']; usable=max(0,actual-profile['reserved_gold_budget'])
    path=[dict(extra_turns=0,forecast_gold=actual,available_for_candidate=usable)]
    earliest=0 if cost<=usable else None
    for d in range(1,profile['maximum_extra_wait']+1):
        received=contexts.base_income(s['own_turn']+d,profile['second_player'])
        actual+=received*profile['future_income_available_fraction']
        usable=max(0,actual-profile['reserved_gold_budget'])
        path.append(dict(extra_turns=d,forecast_gold=actual,income=received,
                         declared_background_spend=received*(1-profile['future_income_available_fraction']),
                         available_for_candidate=usable))
        if cost<=usable and earliest is None: earliest=d
    return dict(now_payable=cost<=path[0]['available_for_candidate'],
                legally_affordable_now=cost<=s['gold_before_play'],
                earliest_extra_wait=earliest,cash_path=path)


def waiting_hand(s,extra_turns,profile):
    """Paired capacity replay only; the comparator grants no body or cash."""
    held=s['hand_size_before_play']; released=held-1
    held_burns=released_burns=0; path=[]
    for t in range(1,extra_turns+1):
        for _ in range(profile['natural_draws_per_wait_turn']):
            if held==7: held_burns+=1
            else: held+=1
            if released==7: released_burns+=1
            else: released+=1
        held-=min(profile['other_plays_per_wait_turn'],held-1)
        released-=min(profile['other_plays_per_wait_turn'],released)
        path.append(dict(extra_turns=t,held_hand_size=held,released_hand_size=released,
                         held_natural_burns=held_burns,released_natural_burns=released_burns))
    return dict(hand_before_deployment=held,additional_natural_burns=held_burns-released_burns,
                capacity_path=path,comparator='one slot released, capacity only; no free card effect or Gold')


def forecast_context(s,d,profile):
    future=copy.deepcopy(s); hand=waiting_hand(s,d,profile)
    future['own_turn']+=d
    future['gold_before_play']=s['gold_before_play']+profile['future_income_available_fraction']*sum(contexts.base_income(s['own_turn']+t,profile['second_player']) for t in range(1,d+1))
    future['hand_size_before_play']=hand['hand_before_deployment']
    future['hand_size_after_play']=hand['hand_before_deployment']-1
    future['cumulative_base_gold_cap']=contexts.cumulative_base_gold(future['own_turn'],profile['second_player'])
    window=future['resource_use_window']
    window['death_event_own_turn']=future['own_turn']
    window['first_own_turn']=future['own_turn']+1
    window['last_own_turn']=future['own_turn']+2
    window['base_income_in_window']=sum(contexts.base_income(t,profile['second_player']) for t in range(window['first_own_turn'],window['last_own_turn']+1))
    window['available_gold_assumption']=window['assumed_carry_gold']+window['base_income_in_window']
    contexts.validate_context(future)
    return future,hand


def quote_state(card,s,reference,profile,event_scale=1.,delay_scale=1.):
    modules,unknown=ledger.parse(card)
    cash=affordability(card,s,profile)
    choices=[]; immediate_quotes=[]
    for d in range(profile['maximum_extra_wait']+1):
        future,hand=forecast_context(s,d,profile)
        feasible=card['cost']<=cash['cash_path'][d]['available_for_candidate']
        for branch in contexts.enumerate_choice_branches(modules):
            selected=[modules[i] for i in branch['selected_module_indexes']]
            try:
                result=ledger.evaluate_branch(card,future,selected,reference,event_scale,quote_only=True)
                gross=result['gross_model_gold']
                if d==0: immediate_quotes.append(gross)
                if not feasible: continue
                retention=(1+profile['delay_rate'][s['role']]*delay_scale)**(-d)
                delay_loss=(1-retention)*max(0,gross)
                p=base.role_parameters(s['role'])
                capacity_loss=hand['additional_natural_burns']*p['draw_value']*p['future_draw_use']*profile['burn_option_multiplier']
                choices.append(dict(**result,choice_selection=branch['choice_selection'],extra_wait=d,
                                    deployment_own_turn=future['own_turn'],forecast_hand=hand,
                                    reservation=gross-delay_loss-capacity_loss,retention=retention,
                                    delay_loss=delay_loss,capacity_loss=capacity_loss))
            except ValueError as exc:
                unknown.append('context pricing boundary: '+str(exc))
    if not choices:
        if immediate_quotes:
            # A forced-deployment quote is undefined with no payable route.
            # Preserve the row, horizon/capacity diagnostics and its weight;
            # never switch to a free zero quote only for expensive cards.
            hand=waiting_hand(s,profile['maximum_extra_wait'],profile)
            p=base.role_parameters(s['role'])
            capacity_loss=hand['additional_natural_burns']*p['draw_value']*p['future_draw_use']*profile['burn_option_multiplier']
            return dict(context_id=s['context_id'],weight=s['weight'],role=s['role'],own_turn=s['own_turn'],
                        pricing_supported=False,unsupported=unknown+['No payable deployment route; continuation beyond horizon is not priced'],cash_feasibility=cash,
                        gross_quote_model_gold=max(immediate_quotes),nominal_cost=card['cost'],actual_payment_made=False,
                        paid_cost_now=None,quoted_net_without_extra_wait=max(immediate_quotes)-card['cost'],
                        chosen_extra_wait=None,route='no payable deployment within horizon',tail_value_not_estimated=True,
                        optional_use_surplus=None,ledger=[],extra_hand_wait_loss=capacity_loss,forecast_hand=hand)
        return dict(context_id=s['context_id'],weight=s['weight'],role=s['role'],
                    pricing_supported=False,unsupported=unknown,cash_feasibility=cash)
    best=max(choices,key=lambda c:(c['reservation'],-c['extra_wait']))
    gross=best['gross_model_gold']
    d=best['extra_wait']; retention=best['retention']
    delay_loss=best['delay_loss']; hand_loss=best['capacity_loss']; reservation=best['reservation']
    return dict(context_id=s['context_id'],role=s['role'],own_turn=s['own_turn'],
                weight=s['weight'],pricing_supported=not unknown,unsupported=unknown,
                gross_quote_model_gold=gross,nominal_cost=card['cost'],actual_payment_made=False,
                paid_cost_now=None,quoted_net_without_extra_wait=max(immediate_quotes)-card['cost'] if immediate_quotes else None,
                reservation_quote_model_gold=reservation,
                adjusted_net_quote_model_gold=reservation-card['cost'],
                extra_wait_discount=retention,additional_wait_loss=delay_loss,
                extra_hand_wait_loss=hand_loss,cash_feasibility=cash,
                chosen_extra_wait=d,route='conditional quoted deployment',tail_value_not_estimated=False,
                forecast_hand=best['forecast_hand'],deployment_own_turn=best['deployment_own_turn'],
                optional_use_surplus=max(0,reservation-card['cost']),
                ledger=best['ledger'],choice_selection=best['choice_selection'],
                interpretation='reservation quote at fixed conditional panel; not actual cash profit')


def score(card,reference,profile=None,include_rows=True):
    profile=normalize_profile(profile)
    for field in ('attack','health','cost'): number(card[field],'card '+field)
    if card['health']==0: raise ValueError('Candidate must have positive printed HP')
    panel=make_panel(profile)
    rows=[quote_state(card,s,reference,profile) for s in panel]
    positive=[r for r in rows if r['weight']>0]
    known=all('adjusted_net_quote_model_gold' in r for r in positive)
    supported=known and all(r['pricing_supported'] for r in positive)
    average=lambda key:sum(r['weight']*r[key] for r in positive) if known else None
    sensitivity=[]
    # Shared parameter changes across all cards, not independently selected
    # best/worst contexts or estimates of statistical confidence.
    for name,event_scale,delay_scale in [('less_death_slower_pressure',.65,.65),('more_death_faster_pressure',1.35,1.35)]:
        varied=[quote_state(card,s,reference,profile,event_scale,delay_scale) for s in panel if s['weight']>0]
        value=sum(r['weight']*r['adjusted_net_quote_model_gold'] for r in varied) if all('adjusted_net_quote_model_gold' in r for r in varied) else None
        sensitivity.append(dict(parameter_scenario=name,supported_terms_adjusted_quote=value,
                                full_card_adjusted_quote=value if supported else None))
    tasks={}
    for role in ROLES:
        group=[r for r in positive if r['role']==role]
        weight=sum(r['weight'] for r in group)
        tasks[role]=sum(r['weight']*r['adjusted_net_quote_model_gold'] for r in group)/weight if known and weight else None
    return dict(card_id=card['id'],name=card['name'],nominal_cost=card['cost'],printed_effect=card['effect_readable'],
                profile_name=profile['name'],profile_sha256=hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest(),
                weight_sum=sum(r['weight'] for r in rows),context_count=len(rows),
                support_status='supported_local_heuristic' if supported else 'partial',
                value_quote_model_gold=average('reservation_quote_model_gold') if supported else None,
                value_margin_model_gold=average('adjusted_net_quote_model_gold') if supported else None,
                intrinsic_net_quote_model_gold=average('quoted_net_without_extra_wait') if supported else None,
                supported_terms_margin=average('adjusted_net_quote_model_gold'),
                optional_use_surplus_model_gold=average('optional_use_surplus') if supported else None,
                unused_option_design_weight=sum(r['weight'] for r in positive if r.get('optional_use_surplus')==0) if supported else None,
                present_payable_design_weight=sum(r['weight'] for r in positive if r.get('cash_feasibility',{}).get('now_payable')),
                no_payment_within_window_weight=sum(r['weight'] for r in positive if r.get('cash_feasibility',{}).get('earliest_extra_wait') is None),
                task_margins=tasks if supported else {role:None for role in ROLES},
                unsupported=sorted({reason for r in positive for reason in r['unsupported']}),
                sensitivity=sensitivity,scope=LIMITATIONS,contexts=rows if include_rows else None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cards',type=int,nargs='+')
    parser.add_argument('--profile',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--compact',action='store_true')
    args=parser.parse_args()
    cards=base.load_cards(); reference,counts=base.make_reference(cards)
    profile=normalize_profile(json.loads(args.profile.read_text(encoding='utf-8')) if args.profile else None)
    chosen=[c for c in cards if c['id'] in args.cards] if args.cards else [c for c in cards if c['card_type']=='monster' and c['pool_category']=='ordinary_non_token' and 4<=c['cost']<=8]
    if args.cards and set(args.cards)!={c['id'] for c in chosen}: raise ValueError('Unknown card IDs')
    output=dict(version=VERSION,ledger_version=ledger.VERSION,profile=profile,reference_cost_counts=counts,
                shared_state_weights=True,prices_are_normative=True,scores=[score(c,reference,profile,not args.compact) for c in chosen])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'cards':len(chosen),'supported':sum(s['value_margin_model_gold'] is not None for s in output['scores'])}))


if __name__=='__main__': main()
