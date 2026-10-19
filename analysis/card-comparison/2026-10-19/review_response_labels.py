"""Independent closed-form audit of retained single-attacker survival labels.

Reads JSON only; imports no production model and performs no action search.
The reported post-own-action enemy state is an input, not revalidated here.
"""
import gzip
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main():
    design = json.loads((HERE/'reply-results/design.json').read_text())
    with gzip.open(HERE/'reply-results/reply-curves.json.gz', 'rt') as f:
        data = json.load(f)
    failures = []
    totals = dict(case_card_settings=0, menu_labels=0, feasible_menus=0,
                  infeasible_menus=0, curve_pieces=0, distinct_hp_witnesses=0)

    def check(condition, location, problem):
        if not condition:
            failures.append(dict(location=location, problem=problem))

    check(set(data) == set(design['cases']), 'root', 'case support differs from design')
    for case, settings in data.items():
        check(set(settings) == set(design['price_settings']), case,
              'price support differs from design')
        for setting, cards in settings.items():
            check(set(cards) == {str(c) for c in design['candidate_ids']},
                  case+'/'+setting, 'candidate support differs from design')
            for cid, result in cards.items():
                totals['case_card_settings'] += 1
                location = '/'.join((case, setting, cid))
                hp, floor = result['own_hp'], result['minimum_own_hp']
                condition = result['condition']
                check(condition['initial_own_board'] == 'empty' and condition['slots'] == 4,
                      location, 'initial friendly board is outside empty/four-slot contract')
                check(condition['enemy_hero_hp'] == 30, location,
                      'enemy hero differs from declared nonterminal 30HP case')
                expected_feasible = []
                expected_background = []
                for index, menu in enumerate(result['menus']):
                    path = location+'/menu/'+str(index)
                    totals['menu_labels'] += 1
                    remaining = menu['enemy_after_own']
                    check(len(remaining) <= 1, path, 'more than one remaining attacker')
                    damage = remaining[0][0] if remaining and remaining[0][1] > 0 else 0
                    expected_hp = hp-damage
                    feasible = expected_hp >= floor
                    check(menu['guaranteed_own_hp'] == expected_hp, path,
                          'guaranteed HP differs from no-Taunt closed form')
                    check(menu['feasible'] == feasible, path,
                          'survival label differs from no-Taunt closed form')
                    totals['feasible_menus' if feasible else 'infeasible_menus'] += 1
                    expected_feasible.append(feasible)
                    if not menu['plan']['candidate_used']:
                        expected_background.append(feasible)
                    if feasible:
                        check(expected_hp <= menu['asset_worst_reply_own_hp'] <= hp,
                              path, 'asset-worst HP lies outside possible one-hit HP range')
                        if menu['asset_worst_reply_own_hp'] != expected_hp:
                            totals['distinct_hp_witnesses'] += 1
                any_feasible = any(expected_feasible)
                any_background = any(expected_background)
                check(result['guarantee_feasible'] == any_feasible, location,
                      'aggregate feasibility differs from menu disjunction')
                check((result['curve'] is not None) == any_feasible, location,
                      'curve/null status differs from aggregate feasibility')
                check((result['background_curve'] is not None) == any_background,
                      location, 'background curve/null status differs from background feasibility')
                check(result['enabled_survival_when_background_cannot'] ==
                      (any_feasible and not any_background), location,
                      'survival-enablement label differs from menu disjunction')
                for piece in result['curve'] or []:
                    totals['curve_pieces'] += 1
                    matching = [m for m in result['menus'] if m['plan'] == piece['action']
                                and abs(m['paid']+piece['slope']) < 1e-10]
                    check(bool(matching), location, 'curve action has no retained physical menu')
                    check(any(m['feasible'] and m['guaranteed_own_hp'] ==
                              piece['guaranteed_own_hp'] for m in matching),
                          location, 'curve HP guarantee differs from its retained menu')
    output = dict(
        scope='Independent no-Taunt one-attacker HP algebra over retained JSON; no search or price recomputation',
        formula='ownHP - surviving_enemy_attack; ownHP if no surviving attacker',
        production_imports=False, old_producer_executed=False,
        post_own_enemy_transitions_independently_recomputed=False,
        opponent_asset_optimum_independently_recomputed=False,
        totals=totals, failure_count=len(failures), failures=failures)
    (HERE/'review-response-labels.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(output, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
