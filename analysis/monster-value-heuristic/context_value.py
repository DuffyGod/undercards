"""Context-based heuristic primitives, designed centrally, not LLM prices.

No complete match simulator. Values are conditional deployment diagnostics;
unaffordable fixtures stay visible and are not assigned fabricated play gains.
"""
from __future__ import annotations
import argparse
import copy
import itertools
import json
from pathlib import Path
import re

import heuristic_contexts as h
import score_cards as base
import combat_increment as combat
import payment_frontier as payments
import coupled_magic as coupled

VERSION = 'context-ledger-0.4.0'
# Joint event weights conditional on the declared phase; not empirical rates.
EVENTS = {
    3: {'ordinary_death': .45, 'silenced_before_event': .20, 'other_non_death_removal': .10, 'no_event_in_window': .25},
    5: {'ordinary_death': .55, 'silenced_before_event': .15, 'other_non_death_removal': .10, 'no_event_in_window': .20},
    8: {'ordinary_death': .60, 'silenced_before_event': .10, 'other_non_death_removal': .15, 'no_event_in_window': .15},
}
CASH_WINDOW_WEIGHT = {3: .70, 5: .85, 8: .95}


def term(kind, amount=None, basis='fixed', stat='none', trigger='magic', target='self', choice=None):
    return dict(kind=kind, amount=amount, amount_basis=basis, stat=stat,
                trigger=trigger, target=target, choice_group=choice)


def parse(card):
    """Complete templates only, no named-card special cases or best-case labels."""
    text = card['effect_readable'].strip()
    statuses = {}
    remainder = text
    while True:
        prefix = re.match(r'^(Haste|Dodge \((\d+)\)|Armor|Taunt)\.\s*', remainder)
        if not prefix:
            break
        token = prefix.group(1)
        if token.startswith('Dodge'):
            statuses['dodge'] = int(prefix.group(2))
        else:
            statuses[token.lower()] = True
        remainder = remainder[prefix.end():]
    if statuses:
        rest, unknown = parse(dict(card, effect_readable=remainder))
        # Growth reset and Dust callbacks remain outside this primitive.
        compatible = all(m['kind'] in ('damage', 'target_damage', 'face_damage', 'debuff', 'draw', 'conditional_haste')
                         for m in rest)
        if not unknown and compatible:
            bundle = term('combat')
            bundle['statuses'] = statuses
            return rest + [bundle], []
        return rest, unknown + ['combat bundle requires coupled lifecycle/target modeling']
    if not text:
        return [], []
    m=re.fullmatch(r'Magic: Deal (\d+) DMG to a monster for each other monster\. If this deals (\d+) or less DMG, gain Haste\.',text)
    if m:
        return [term('target_damage',int(m[1]),basis='other_monster_count',target='monster'),
                term('conditional_haste',int(m[2]))],[]
    m=re.fullmatch(r'Magic: Deal DMG to an enemy monster equal to the number of cards in your hand\.(?: (Bullseye: .+))?',text)
    if m:
        modules=[term('target_damage',1,basis='hand_size_after_play',target='enemy_monster')]
        return modules,(['unimplemented linked trigger: '+m[1]] if m[1] else [])
    m=re.fullmatch(r'Magic: Deal (\d+) DMG to a monster\.',text)
    if m: return [term('target_damage',int(m[1]),target='monster')],[]
    m=re.fullmatch(r'Magic: Deal DMG (\d+)\.',text)
    if m and card.get('target')=='ALL':
        return [term('target_damage',int(m[1]),target='wide_entity')],[]
    patterns = [
        (r'Magic: Gain ATK \+(\d+)/HP \+(\d+) for each card in your hand\.', 'hand_growth'),
        (r'Dust: Give all cards in your hand -(\d+) COST\.', 'dust_discount'),
        (r'Dust: Earn GOLD (\d+)\.', 'dust_cash'),
        (r'Magic: Give an ally monster \+(\d+) ATK/\+(\d+) HP\.', 'ally_both'),
        (r'Magic: Gain \+(\d+) ATK/\+(\d+) HP\.', 'self_both'),
        (r'Magic: Deal (\d+) DMG to an enemy or give an ally monster \+(\d+) ATK\.', 'choice'),
        (r'Magic: Give a monster \+(\d+) HP\.', 'any_health'),
        (r'Magic: Give all other ally monsters ATK \+(\d+)/HP \+(\d+)\.', 'all_ally_both'),
        (r'Magic: Deal (\d+) DMG to this\.', 'self_damage'),
        (r'Magic: Swap a monster\x27s ATK and HP\.', 'swap'),
        (r'Magic: Set an enemy monster\x27s ATK to (\d+) and gain HP equal to the amount of ATK decreased\.', 'attack_to_health'),
    ]
    for pattern, kind in patterns:
        m = re.fullmatch(pattern, text)
        if not m:
            continue
        n = [int(v) for v in m.groups()]
        if kind == 'hand_growth':
            return [term('buff', n[0], 'hand_size_after_play', 'ATK'),
                    term('buff', n[1], 'hand_size_after_play', 'HP')], []
        if kind == 'dust_discount':
            return [term('discount', -n[0], trigger='dust', target='hand')], []
        if kind == 'dust_cash':
            return [term('cash', n[0], trigger='dust')], []
        if kind == 'ally_both':
            return [term('buff', n[0], stat='ATK', target='ally'),
                    term('buff', n[1], stat='HP', target='ally')], []
        if kind == 'self_both':
            return [term('buff', n[0], stat='ATK'), term('buff', n[1], stat='HP')], []
        if kind == 'choice':
            return [term('damage_choice', n[0], target='enemy', choice='magic-choice'),
                    term('buff', n[1], stat='ATK', target='ally', choice='magic-choice')], []
        if kind == 'any_health':
            return [term('any_health', n[0], target='other')], []
        if kind == 'all_ally_both':
            return [term('all_ally_buff', n[0], stat='ATK', target='ally'),
                    term('all_ally_buff', n[1], stat='HP', target='ally')], []
        if kind == 'self_damage':
            return [term('self_damage', n[0])], []
        if kind == 'swap':
            return [term('swap', 0, target='other')], []
        if kind == 'attack_to_health':
            return [term('attack_to_health', n[0], target='enemy_monster')], []
    modules, unknown = base.parse_effect(card)
    converted = []
    for m in modules:
        kind = m['kind']
        if kind in ('buff_attack', 'buff_health'):
            converted.append(term('buff', m['amount'], stat='ATK' if kind == 'buff_attack' else 'HP', target='ally'))
        elif kind == 'debuff':
            converted.append(term('debuff', -m['amount'], stat='ATK', target='all_enemy_monsters'))
        else:
            converted.append(term(kind, m['amount'], target=m['target']))
    return converted, unknown


def body(a, hp, reference, role):
    return base.body_value(a, hp, reference, base.role_parameters(role))


def event_weights(ctx, scale=1.):
    phase=max(t for t in EVENTS if t<=ctx['own_turn'])
    result = dict(EVENTS[phase])
    old = result['ordinary_death']
    result['ordinary_death'] = min(1 - result['silenced_before_event'] - result['other_non_death_removal'], old * scale)
    result['no_event_in_window'] += old - result['ordinary_death']
    return result


def evaluate_branch(card, ctx, modules, reference, event_scale=1., quote_only=False):
    role = ctx['role']
    cash_weight=CASH_WINDOW_WEIGHT[max(t for t in CASH_WINDOW_WEIGHT if t<=ctx['own_turn'])]
    bv = lambda a, hp: body(a, hp, reference, role)
    self_attack, self_health = card['attack'], card['health']
    ally_buffs = []
    all_ally_buffs = []
    self_damage = 0
    combat_bundles = []
    damage_modules=[]
    conditional_haste_limit=None
    combat_enemies = copy.deepcopy(ctx['enemy_bodies'])
    enemy_player_hp_after_magic = ctx.get('enemy_player_hp',30)
    others = []
    for m in modules:
        if m['kind'] == 'combat':
            combat_bundles.append(m)
        elif m['kind'] in ('damage','target_damage','damage_choice','face_damage'):
            damage_modules.append(m)
        elif m['kind']=='conditional_haste':
            if conditional_haste_limit is not None: raise ValueError('Multiple conditional Haste gates are unsupported')
            conditional_haste_limit=int(m['amount'])
        elif m['kind'] == 'buff' and m['target'] == 'self':
            amount = h.evaluate_amount(m, ctx)
            if m['stat'] == 'ATK': self_attack += amount
            elif m['stat'] == 'HP': self_health += amount
        elif m['kind'] == 'buff' and m['target'] == 'ally':
            ally_buffs.append(m)
        elif m['kind'] == 'all_ally_buff':
            all_ally_buffs.append(m)
        elif m['kind'] == 'self_damage':
            self_damage += h.evaluate_amount(m, ctx)
        else:
            others.append(m)
    printed = bv(card['attack'], card['health'])
    original = bv(card['attack'], max(0, card['health'] - self_damage))
    # One final-body delta, not separate overlapping ATK and HP bonuses.
    growth = bv(self_attack, max(0, self_health - self_damage)) - original
    events = event_weights(ctx, event_scale)
    retained_growth = (1 - events['silenced_before_event']) * growth
    ledger = [dict(term='ordinary_body', model_gold=printed),
              dict(term='irreversible_self_damage', model_gold=original-printed,
                   note='intrinsic self damage is legal; not a selectable self-target and not undone by silence'),
              dict(term='joint_self_growth', model_gold=retained_growth,
                   gross_growth=growth, loss_if_silenced=growth,
                   note='incremental modifier exposure only; ordinary body lifetime is embedded in baseline')]
    if ally_buffs or all_ally_buffs:
        da = sum(h.evaluate_amount(m, ctx) for m in ally_buffs if m['stat'] == 'ATK')
        dh = sum(h.evaluate_amount(m, ctx) for m in ally_buffs if m['stat'] == 'HP')
        gains = [bv(t['attack'] + da, t['health'] + dh) - bv(t['attack'], t['health'])
                 for t in ctx['ally_bodies_before_play']]
        ledger.append(dict(term='joint_ally_buff', model_gold=max(gains, default=0.),
                           note='one observed ally chosen; cannot target caster; later caster silence does not undo it'))
        da = sum(h.evaluate_amount(m, ctx) for m in all_ally_buffs if m['stat']=='ATK')
        dh = sum(h.evaluate_amount(m, ctx) for m in all_ally_buffs if m['stat']=='HP')
        value = sum(bv(t['attack']+da,t['health']+dh)-bv(t['attack'],t['health']) for t in ctx['ally_bodies_before_play'])
        ledger.append(dict(term='joint_all_other_ally_buff', model_gold=value, target_count=len(ctx['ally_bodies_before_play']),
                           note='caster excluded; each target receives one joint ATK/HP change'))
    for m in others:
        amount = h.evaluate_amount(m, ctx)
        kind = m['kind']
        if kind == 'debuff':
            value = sum(bv(t['attack'], t['health']) - bv(max(0, t['attack'] + amount), t['health'])
                        for t in ctx['enemy_bodies'])
            ledger.append(dict(term='all_enemy_attack_delta', model_gold=value))
            for target in combat_enemies:
                target['attack'] = max(0, target['attack'] + amount)
        elif kind == 'draw':
            kept = min(int(amount), 7 - ctx['hand_size_after_play'])
            p = base.role_parameters(role)
            # Conditional net option value: no second payment deduction.
            value = kept * p['draw_value'] * p['future_draw_use']
            ledger.append(dict(term='draw_net_options', model_gold=value, drawn=amount, kept=kept,
                               note='net future option prior, not full drawn body; current hand room is exact'))
        elif kind == 'discount':
            if 'death_event_hand_quotes' in ctx:
                quotes = ctx['death_event_hand_quotes']
                if [q['cost'] for q in quotes] != ctx['death_event_hand_costs']:
                    raise ValueError('Quotes must describe the same declared event hand')
                if 'future_payment_play_caps' not in ctx:
                    raise ValueError('Quoted frontier requires declared common play caps')
                window=ctx['resource_use_window']
                incomes=[h.base_income(t,ctx.get('second_player',False)) for t in range(window['first_own_turn'],window['last_own_turn']+1)]
                frontier=payments.compare_discount(quotes,incomes,window['assumed_carry_gold'],
                                                  ctx['future_payment_play_caps'],amount)
                conditional=frontier['total_net_improvement_model_gold']
                value=events['ordinary_death']*cash_weight*conditional
                ledger.append(dict(term='dust_quoted_payment_frontier',model_gold=value,
                                   conditional_improvement_model_gold=conditional,frontier=frontier,event_weights=events,
                                   note='replaces matched usage-mask savings; direct paid savings plus unlocked net options, no extra full body or whole-hand cash bonus; quotes/caps are declared priors'))
            else:
                payment_rows = h.discount_payment_ledger(ctx, amount)
                saved = payment_rows['total_saved_paid_gold']
                value = events['ordinary_death'] * cash_weight * saved
                ledger.append(dict(term='dust_actual_payment_savings', model_gold=value,
                                   conditional_saved_gold=saved, payments=payment_rows,
                                   event_weights=events, note='unused cards save zero; never counted as immediately received cash; extra actions not priced without explicit future-hand quotes'))
        elif kind == 'cash':
            value = events['ordinary_death'] * cash_weight * amount
            ledger.append(dict(term='dust_cash', model_gold=value, conditional_cash=amount,
                               event_weights=events, note='cash receipt once; not also a cost refund'))
        elif kind == 'any_health':
            options = [bv(t['attack'],t['health']+amount)-bv(t['attack'],t['health']) for t in ctx['ally_bodies_before_play']]
            options += [bv(t['attack'],t['health'])-bv(t['attack'],t['health']+amount) for t in ctx['enemy_bodies']]
            value = max(options, default=0.)
            ledger.append(dict(term='mandatory_any_monster_health', model_gold=value,
                               note='may only have hostile targets; negative effect retained, caster excluded'))
        elif kind == 'swap':
            options = [bv(t['health'],t['attack'])-bv(t['attack'],t['health']) for t in ctx['ally_bodies_before_play']]
            options += [bv(t['attack'],t['health'])-bv(t['health'],t['attack']) for t in ctx['enemy_bodies']]
            ledger.append(dict(term='stat_swap_fresh_targets', model_gold=max(options, default=0.),
                               note='only shared fresh synthetic targets; injured/max-HP semantics not modeled'))
        elif kind == 'attack_to_health':
            options = []
            for t in ctx['enemy_bodies']:
                removed_attack = max(0,t['attack']-amount)
                enemy_delta = bv(t['attack'],t['health'])-bv(amount,t['health'])
                own_growth = bv(self_attack,self_health+removed_attack)-bv(self_attack,self_health)
                total = enemy_delta + (1-events['silenced_before_event'])*own_growth
                options.append(dict(total=total, target=t, enemy_delta=enemy_delta, own_growth=own_growth))
            chosen = max(options, key=lambda x:x['total']) if options else dict(total=0, target=None, enemy_delta=0, own_growth=0)
            ledger.append(dict(term='one_target_attack_to_self_health', model_gold=chosen['total'], coupled_target=chosen,
                               note='same target sets both quantities; caster silence removes gained HP only'))
        else:
            raise ValueError('Unsupported branch term: ' + kind)
    if damage_modules:
        # Resolve target choice and attacks jointly. Direct damage is a
        # diagnostic part of the same P1-P0 difference, never a second kill.
        if any(m['kind']=='debuff' for m in others):
            raise ValueError('Joint damage and attack debuff window not implemented')
        if self_attack!=card['attack'] or self_health!=card['health'] or self_damage:
            raise ValueError('Joint damage with caster modifier reset not implemented')
        statuses={}
        for bundle in combat_bundles:
            if set(statuses)&set(bundle['statuses']): raise ValueError('Duplicate combat status bundle')
            statuses.update(bundle['statuses'])
        specs=[]
        for m in damage_modules:
            target=m['target']
            if m['kind']=='face_damage': target='opponent'
            elif target=='enemy': target='enemy_entity'
            specs.append({'amount':int(h.evaluate_amount(m,ctx)),'target':target})
        result=coupled.evaluate_cached(card,ctx,specs,statuses,reference,
                               conditional_haste_limit=conditional_haste_limit)
        if result['total_delta_model_gold'] is None:
            raise ValueError('Terminal outcome cannot be assigned a resource Gold premium')
        ledger.extend([
            dict(term='magic_immediate_resource_delta',model_gold=result['direct_damage_model_gold'],
                 selection=result['magic_selection'],note='part of total same-window difference; no additional full removal bonus'),
            dict(term='magic_response_interaction',model_gold=result['magic_interaction_model_gold'],
                 note='same Magic target; changed enemy response and next-own attack relative to original board'),
            dict(term='paired_keyword_exchange_increment',model_gold=result['keyword_delta_model_gold'],details=result,
                 note='P1-Pmid on the same selected post-Magic board; sum with immediate and interaction equals P1-P0')])
        combat_bundles=[]
    elif conditional_haste_limit is not None:
        raise ValueError('Conditional Haste requires its bound damage instance')
    for bundle in combat_bundles:
        result = combat.premium(self_attack, max(0, self_health-self_damage),
                                combat_enemies, bundle['statuses'],
                                ctx['opponent_gold_before_response'], reference, role,
                                own_player_hp=ctx.get('own_player_hp',30),
                                enemy_player_hp=enemy_player_hp_after_magic)
        if result['premium_model_gold'] is None:
            raise ValueError('Terminal outcome cannot be assigned a resource Gold premium')
        ledger.append(dict(term='paired_keyword_exchange_increment',
                           model_gold=result['premium_model_gold'], details=result,
                           note='at most one current Haste attack plus one common next-turn attack; immediate Magic applied identically to both baselines; no extra kill/keyword bonus'))
    gross = sum(r['model_gold'] for r in ledger)
    if quote_only:
        return dict(gross_model_gold=gross, quoted_cost=card['cost'],
                    net_quote_model_gold=gross-card['cost'], ledger=ledger,
                    actual_payment_made=False)
    return dict(gross_model_gold=gross, paid_cost=card['cost'], net_model_gold=gross - card['cost'], ledger=ledger)


def score(card, reference):
    modules, unsupported = parse(card)
    rows = []
    for ctx in h.make_contexts():
        if card['cost'] > ctx['gold_before_play']:
            rows.append(dict(context_id=ctx['context_id'], weight=ctx['weight'], role=ctx['role'],
                             own_turn=ctx['own_turn'], affordable=False, net_model_gold=None,
                             note='No deployment; cost not paid. Holding/waiting value not estimated.'))
            continue
        bound = h.bind_candidate(ctx, card['cost'])
        candidates = []
        for branch in h.enumerate_choice_branches(modules):
            terms = [modules[i] for i in branch['selected_module_indexes']]
            result = evaluate_branch(card, bound, terms, reference)
            result['choice_selection'] = branch['choice_selection']
            result['event_sensitivity'] = [evaluate_branch(card, bound, terms, reference, x)['net_model_gold'] for x in (.65, 1.35)]
            candidates.append(result)
        # Current observed choices, same context; never choose a best context.
        best = max(candidates, key=lambda r: r['net_model_gold'])
        rows.append(dict(context_id=ctx['context_id'], role=ctx['role'], own_turn=ctx['own_turn'],
                         weight=ctx['weight'], affordable=True, **best))
    played = [r for r in rows if r['affordable']]
    coverage = sum(r['weight'] for r in played)
    mean = sum(r['weight'] * r['net_model_gold'] for r in played) / coverage if coverage else None
    return dict(card_id=card['id'], name=card['name'], paid_cost=card['cost'], printed_effect=card['effect_readable'],
                support_status='partial' if unsupported else 'supported_heuristic', unsupported_effects=unsupported,
                conditional_net_model_gold=None if unsupported else mean,
                supported_terms_conditional_net=mean, payable_design_weight=coverage, contexts=rows,
                score_scope='conditional deployability only; no full deck/holding value and no win-rate claims')


def compare_pair(left, right, reference):
    """Same payable contexts; do not mistake changing sample weights for value."""
    a, b = score(left, reference), score(right, reference)
    right_rows = {r['context_id']: r for r in b['contexts']}
    common = [(r, right_rows[r['context_id']]) for r in a['contexts']
              if r['affordable'] and right_rows[r['context_id']]['affordable']]
    weight = sum(x['weight'] for x, _ in common)
    difference = sum(x['weight'] * (x['net_model_gold'] - y['net_model_gold']) for x, y in common) / weight if weight else None
    return dict(left_id=left['id'], right_id=right['id'],
                common_payable_weight=weight,
                left_payable_weight=a['payable_design_weight'], right_payable_weight=b['payable_design_weight'],
                supported_terms_common_context_delta=difference,
                full_heuristic_common_context_delta=difference if not a['unsupported_effects'] and not b['unsupported_effects'] else None,
                scope='same-context deployment comparison, not full deck or holding value')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cards', type=int, nargs='+')
    p.add_argument('--output', required=True)
    args = p.parse_args()
    cards = base.load_cards()
    reference, _ = base.make_reference(cards)
    chosen = [c for c in cards if c['id'] in args.cards] if args.cards else [c for c in cards if c['card_type']=='monster' and c['pool_category']=='ordinary_non_token' and 4 <= c['cost'] <= 8]
    output = dict(version=VERSION, context_version=h.VERSION, event_weights=EVENTS,
                  cash_window_weights=CASH_WINDOW_WEIGHT, parameters_are_design_assumptions=True,
                  combat_version=combat.VERSION,
                  payment_frontier_version=payments.VERSION,
                  limitations=['Conditional means use different payable masks and must not be directly ranked; use compare_pair for matched comparisons.',
                               'Body uses a common printed-body reference; stage boards change action targets, not the body-price reference.',
                               'Response event weights are assumptions; keyword counterfactuals use a paid synthetic response, not a full opponent-conversion evaluation.',
                               'Keyword premiums cover one response window and common next-turn attack; no other friendly defenders or Dust callbacks. Both players start at 30HP; immediate Magic is preserved.',
                               'Future usage masks are scenarios. Only current immediate choices may optimize using this implementation.',
                               'Dust counts direct cash/payment savings only; unlocking extra actions or earlier play remains outside this estimate.'],
                  scope='Conditional heuristic diagnostics, not empirically calibrated prices.', scores=[score(c, reference) for c in chosen])
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'cards':len(chosen),'supported_heuristic':sum(r['support_status']=='supported_heuristic' for r in output['scores'])}))


if __name__ == '__main__':
    main()
