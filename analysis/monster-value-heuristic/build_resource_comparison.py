"""Reproducible resource/deployment comparison; no strength-labelled decks.

Three abstract 25-card curves use identical policy, shuffle seed, draw rules,
opponent-task and board priors. Differences are conditional on the same card
being available, not estimates of how often that card will be drawn/held.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import context_value as ledger
import resource_profile_bridge as bridge
import score_cards as base
import unified_value as unified

HERE = Path(__file__).resolve().parent
CURVES = {
    'lower_cost': [1]*4+[2]*6+[3]*6+[4]*4+[5]*3+[6]*2,
    'middle_cost': [1]*2+[2]*3+[3]*4+[4]*5+[5]*4+[6]*4+[7]*2+[8],
    'higher_cost': [2]*2+[3]*3+[4]*4+[5]*4+[6]*5+[7]*4+[8]*3,
}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def build(output, trials=1000):
    output.mkdir(parents=True, exist_ok=True)
    cards = base.load_cards()
    reference, counts = base.make_reference(cards)
    pool = [c for c in cards if c['card_type']=='monster'
            and c['pool_category']=='ordinary_non_token' and 4<=c['cost']<=8]
    # Whole-text template support only. No card name or manual quality labels.
    selected = [c for c in pool if not ledger.parse(c)[1]]
    modules=(base,ledger,unified,bridge,ledger.combat,ledger.coupled,ledger.payments)
    provenance={Path(module.__file__).name:hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                for module in modules}
    write(output/'run-provenance.json',{'source_sha256':provenance,
          'template_supported_ids':[c['id'] for c in selected], 'trials_per_curve':trials,
          'interpretation':'Hashes captured before numerical evaluation; template support is not semantic/meta validation.'})
    results = {}
    for name, costs in CURVES.items():
        data = {'name': name+'_deploy', 'deck_costs': costs, 'policy': 'deploy',
                'future_income_available_fraction': .60,
                'resource_config': {'trials': trials, 'seed': 20261008,
                                    'opening_hand': 3, 'first_turn_draw': True,
                                    'first': True, 'horizon': 8}}
        write(output/(name+'-input.json'), data)
        sampled = bridge.build_profile(data)
        write(output/(name+'-resources.json'), sampled)
        if not sampled['profile_ready']:
            raise ValueError('No nonempty-hand phase in '+name)
        profile = sampled['unified_profile']
        write(output/(name+'-profile.json'), profile)
        scores=[]
        for index,c in enumerate(selected,1):
            scores.append(unified.score(c,reference,profile,include_rows=False))
            if index%4==0:
                print(json.dumps({'curve':name,'completed_cards':index,'total_cards':len(selected)},ensure_ascii=False),flush=True)
        write(output/(name+'-values.json'), {
            'unified_version': unified.VERSION, 'ledger_version': ledger.VERSION,
            'source_sha256':provenance,'profile_sha256': bridge.digest(profile), 'scores': scores})
        results[name] = {'cost_histogram': dict(sorted(Counter(costs).items())),
                         'phase_summaries': sampled['phase_summaries'],
                         'scores': scores}
        print(json.dumps({'curve': name, 'template_supported': len(selected),
                          'fully_quoted': sum(s['value_margin_model_gold'] is not None for s in scores)}, ensure_ascii=False), flush=True)
    comparison = []
    for card in selected:
        by_curve = {name: next(s for s in result['scores'] if s['card_id']==card['id'])
                    for name, result in results.items()}
        comparison.append({'card_id': card['id'], 'name': card['name'], 'cost': card['cost'],
                           'margins': {name: row['value_margin_model_gold'] for name,row in by_curve.items()},
                           'payable_now_weights': {name: row['present_payable_design_weight'] for name,row in by_curve.items()},
                           'unsupported': {name: row['unsupported'] for name,row in by_curve.items()}})
    summary = {'versions': {'unified': unified.VERSION, 'ledger': ledger.VERSION, 'bridge': bridge.VERSION},
               'source_sha256':provenance,
               'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'reference_counts': counts, 'pool_size': len(pool),
               'whole_text_template_count': len(selected), 'trials_per_curve': trials,
               'scope': 'Same candidate-availability condition and opponent priors; abstract curves, not quality rankings or match frequencies.',
               'shared_assumptions': {'policy': 'deploy', 'future_income_available_fraction': .60,
                                      'candidate_present': 'conditional; not inferred from sampling',
                                      'opening_hand': 3, 'first_turn_draw': True,
                                      'board_and_phase_weights': 'unified defaults'},
               'comparison': comparison}
    write(output/'comparison.json', summary)
    return summary


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE/'resource-comparison-v03')
    parser.add_argument('--trials', type=int, default=1000)
    args = parser.parse_args()
    build(args.output, args.trials)
