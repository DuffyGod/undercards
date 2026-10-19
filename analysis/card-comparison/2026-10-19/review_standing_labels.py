"""Read only the new standing JSON and check one-body guarantees analytically.

No production imports, old HP audit, action search or numerical price replay.
"""
import gzip
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main():
    design = json.loads((HERE/'reply-standing/design.json').read_text())
    with gzip.open(HERE/'reply-standing/reply-curves.json.gz', 'rt') as f:
        data = json.load(f)
    failures = []
    totals = dict(base_results=0, defense_control_results=0, base_menus=0,
                  defense_control_menus=0, feasible_menus=0, infeasible_menus=0,
                  curve_pieces=0)

    def check(condition, location, problem):
        if not condition:
            failures.append(dict(location=location, problem=problem))

    def audit(result, path, control=False):
        totals['defense_control_results' if control else 'base_results'] += 1
        hp, hp_floor = result['own_hp'], result['minimum_own_hp']
        body_floor = result['minimum_own_bodies']
        feasible_flags, background_flags = [], []
        for n, menu in enumerate(result['menus']):
            loc = path+'/menu/'+str(n)
            totals['defense_control_menus' if control else 'base_menus'] += 1
            own, enemy = menu['own_after_own'], menu['enemy_after_own']
            check(len(own) <= 1 and len(enemy) <= 1, loc,
                  'outside one-friendly/one-enemy analytic contract')
            check(all(not u['taunt'] and u['health'] > 0 for u in own), loc,
                  'Taunt or a dead retained friendly invalidates closed form')
            a = enemy[0][0] if enemy and enemy[0][1] > 0 else 0
            expected_hp = hp-a
            if not own:
                bodies = 0
            elif a == 0:
                bodies = len(own)
            else:
                u = own[0]
                bodies = int(u['dodge'] > 0 or
                             u['health'] > max(0, a-int(u['armor'])))
            feasible = expected_hp >= hp_floor and bodies >= body_floor
            check(menu['guaranteed_own_hp'] == expected_hp, loc,
                  'HP guarantee differs from closed form on new standing record')
            check(menu['guaranteed_body_count'] == bodies, loc,
                  'body guarantee differs from closed form')
            check(menu['feasible'] == feasible, loc,
                  'joint HP/body feasibility differs from conjunction of guarantees')
            totals['feasible_menus' if feasible else 'infeasible_menus'] += 1
            feasible_flags.append(feasible)
            if not menu['plan']['candidate_used']:
                background_flags.append(feasible)
        any_feasible, background_feasible = any(feasible_flags), any(background_flags)
        check(result['guarantee_feasible'] == any_feasible, path,
              'aggregate feasibility differs from menu disjunction')
        check((result['curve'] is not None) == any_feasible, path,
              'curve/null status differs from feasibility')
        check((result['background_curve'] is not None) == background_feasible, path,
              'background curve/null status differs from feasibility')
        check(result['enabled_goal_when_background_cannot'] ==
              (any_feasible and not background_feasible), path,
              'joint goal enablement differs from feasible menus')
        for piece in result['curve'] or []:
            totals['curve_pieces'] += 1
            matching = [m for m in result['menus'] if m['plan'] == piece['action']
                        and abs(m['paid']+piece['slope']) < 1e-10]
            check(any(m['feasible'] and
                      m['guaranteed_own_hp'] == piece['guaranteed_own_hp'] and
                      m['guaranteed_body_count'] == piece['guaranteed_body_count']
                      for m in matching), path,
                  'curve guarantees do not match a retained feasible menu')

    check(set(data) == set(design['cases']), 'root', 'case support differs from design')
    for case, settings in data.items():
        check(set(settings) == set(design['price_settings']), case,
              'price support differs from design')
        for setting, cards in settings.items():
            check(set(cards) == {str(c) for c in design['candidate_ids']},
                  case+'/'+setting, 'candidate support differs from design')
            for cid, result in cards.items():
                path = '/'.join((case, setting, cid))
                audit(result, path)
                if 'defense_removed_control' in result:
                    audit(result['defense_removed_control'], path+'/defense_removed', True)
    out = dict(scope='Only new reply-standing JSON; independent one-body HP/retention algebra',
               production_imports=False, old_hp_label_audit_executed=False,
               old_producer_executed=False, physical_post_own_transitions_recomputed=False,
               totals=totals, failure_count=len(failures), failures=failures)
    (HERE/'review-standing-labels.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(out, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
