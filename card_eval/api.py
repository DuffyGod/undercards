"""Public evaluation API: explicit decks in, conditional comparisons out."""
from dataclasses import asdict
from pathlib import Path
from collections import Counter
import gzip, hashlib, json, time
import numpy as np
from . import __version__
from .catalog import resolve, deck, coverage, semantic_key, InputError, UnsupportedRule
from .game import NativeGame, DecisionBudgetExceeded
from .network import Network
from .policies import LearnedPolicy, ReferencePolicy
from .profiles import opponents
from .statistics import interval

DEFAULT_MODEL = Path(__file__).resolve().parent / 'models/paired-v5.npz'


def _issue(path, code, message): return dict(path=path, code=code, message=message)


def validate(request):
    if not isinstance(request, dict): raise InputError([_issue('', 'input_type', 'Request must be a JSON object')])
    allowed = {'deck', 'soul', 'opponents', 'slots', 'candidates', 'seed_start', 'samples', 'policies', 'silence_mode', 'decision_seconds', 'allow_unqualified_policy','planner'}
    if set(request) - allowed: raise InputError([_issue('', 'unknown_fields', 'Unknown input fields: ' + ', '.join(sorted(set(request) - allowed)))])
    own = deck(request.get('deck'), 'deck'); slots = request.get('slots', [0])
    if not isinstance(slots, list) or not slots or len(set(slots)) != len(slots) or any(type(i) is not int or not 0 <= i < 25 for i in slots):
        raise InputError([_issue('slots', 'replacement_slots', 'Select unique explicit deck indices0..24')])
    ref = own[slots[0]]
    if any(semantic_key(own[i]) != semantic_key(ref) for i in slots):
        raise InputError([_issue('slots', 'mixed_reference', 'Selected slots must have equivalent reference-card semantics')])
    soul = request.get('soul', 'INTEGRITY')
    if soul not in ('INTEGRITY', 'KINDNESS'): raise InputError([_issue('soul', 'unsupported_soul', 'SOUL passive not implemented: ' + str(soul))])
    raw_opponents = request.get('opponents')
    if not isinstance(raw_opponents, list) or not raw_opponents: raise InputError([_issue('opponents', 'missing_opponents', 'Declare at least one complete opponent deck')])
    opps = []
    for i, raw in enumerate(raw_opponents):
        if not isinstance(raw, dict) or set(raw) - {'name', 'deck', 'soul', 'policy'}: raise InputError([_issue(f'opponents[{i}]', 'opponent_fields', 'Use name/deck/soul/policy')])
        name = raw.get('name', f'opponent_{i}'); osoul = raw.get('soul', 'INTEGRITY'); policy = raw.get('policy', 'race')
        if not isinstance(name, str) or not name or osoul not in ('INTEGRITY', 'KINDNESS') or policy not in ('race', 'board', 'guard', 'learned'):
            raise InputError([_issue(f'opponents[{i}]', 'opponent_parameters', 'Invalid opponent name, SOUL or policy')])
        opps.append(dict(name=name, cards=deck(raw.get('deck'), f'opponents[{i}].deck'), soul=osoul, policy=policy))
    if len({o['name'] for o in opps}) != len(opps): raise InputError([_issue('opponents', 'duplicate_names', 'Opponent names must be unique')])
    samples = request.get('samples', 32); seed_start = request.get('seed_start', 1410000)
    if type(samples) is not int or samples < 2 or type(seed_start) is not int or seed_start < 0:
        raise InputError([_issue('samples', 'sampling', 'Use integer samples>=2 and seed_start>=0')])
    policies = request.get('policies', ['race', 'board', 'guard'])
    if not isinstance(policies, list) or not policies or len(set(policies)) != len(policies) or any(p not in ('learned', 'race', 'board', 'guard') for p in policies):
        raise InputError([_issue('policies', 'policy_selection', 'Select unique learned/race/board/guard policies')])
    mode = request.get('silence_mode', 'retain'); budget = request.get('decision_seconds', .25)
    if mode not in ('retain', 'reset', 'reject_modified') or type(budget) not in (int, float) or not np.isfinite(budget) or budget <= 0:
        raise InputError([_issue('', 'rules_or_budget', 'Declare a supported silence assumption and positive decision budget')])
    raw_candidates = request.get('candidates')
    if not isinstance(raw_candidates, list) or not raw_candidates: raise InputError([_issue('candidates', 'missing_candidates', 'Supply at least one candidate')])
    candidates = []; blocked = []; names = set()
    for i, raw in enumerate(raw_candidates):
        try:
            spec = resolve(raw)
            if spec.name in names: raise ValueError('Candidate diagnostic names must be unique')
            changed = list(own)
            for index in slots: changed[index] = spec
            changed = deck(changed, f'candidates[{i}].resulting_deck')
            names.add(spec.name); candidates.append(dict(spec=spec, cards=changed))
        except (ValueError, TypeError, KeyError) as exc:
            blocked.append(dict(input=raw, status='unsupported_or_invalid', score=None,
                issues=exc.issues if isinstance(exc, InputError) else [_issue(f'candidates[{i}]', 'candidate', str(exc))]))
    experimental = request.get('allow_unqualified_policy', False)
    if type(experimental) is not bool: raise InputError([_issue('allow_unqualified_policy', 'type', 'Use an explicit boolean')])
    planner=request.get('planner')
    if planner is not None:
        if not isinstance(planner,dict) or set(planner)-{'mode','margin','nodes','depth','width','seconds'}:
            raise InputError([_issue('planner','configuration','Use a planner object with mode/margin/nodes/depth/width/seconds')])
        if not ('learned' in policies or any(o['policy']=='learned' for o in opps)):
            raise InputError([_issue('planner','learned_required','Public planning needs a learned policy')])
        config=dict(mode='proof',margin=.1,nodes=48,depth=3,width=4,seconds=.18);config.update(planner)
        if (config['mode'] not in ('proof','value') or any(type(config[k]) is not int or not 1<=config[k]<=128 for k in ('nodes','depth','width'))
            or any(type(config[k]) not in (int,float) or not np.isfinite(config[k]) for k in ('margin','seconds'))
            or not 0<=config['margin']<=1 or not 0<config['seconds']<min(.25,float(budget))):
            raise InputError([_issue('planner','budget','Use bounded positive node/depth/width, margin0..1, and seconds below both .25 and the decision budget')])
        planner=config
    return dict(own=own, reference=ref, slots=slots, soul=soul, opponents=opps, samples=samples,
                seed_start=seed_start, policies=policies, silence_mode=mode, decision_seconds=float(budget),
                candidates=candidates, blocked=blocked, allow_unqualified_policy=experimental,planner=planner)


def default_request(candidates, reference='Rock Pet', copies=1, samples=32):
    ref = resolve(reference); parsed = []
    for c in candidates:
        try: parsed.append(resolve(c))
        except (ValueError, TypeError): pass
    if type(copies) is not int or not 1 <= copies <= 3: raise ValueError('copies must be1..3')
    # Common background respects copy limits even when a candidate is already
    # present. It is a declared benchmark, not a recommended full deck.
    available = [resolve(s['name']) for s in coverage()['supported'] if s['name'] != ref.name]
    if copies == 3: available = [s for s in available if s.name not in {c.name for c in parsed}]
    own = [ref] * copies
    for round_index in range(3):
        for spec in available:
            limit = 3 - copies if spec.name in {c.name for c in parsed} else 3
            if round_index < limit and len(own) < 25: own.append(spec)
    if len(own) != 25: raise ValueError('Not enough supported cards for a common legal background; supply an explicit request')
    def raw(s):
        if s.card_id is not None: return s.card_id
        d = asdict(s); d.pop('card_id'); return d
    return dict(deck=list(map(raw, own)), candidates=candidates, slots=list(range(copies)), samples=samples,
        opponents=[dict(name=name, deck=list(map(raw, other)), soul='KINDNESS' if name == 'defense' else 'INTEGRITY',
                        policy='guard' if name == 'defense' else 'board' if name == 'refill' else 'race')
                   for name, other in opponents().items()])


def evaluate(request, output=None, checkpoint=None, progress=None):
    output = Path(output) if output else None
    if output and output.exists(): raise ValueError('Output exists; preserve it and use a new directory')
    if output: output.mkdir(parents=True)
    def save(name, data):
        if output: (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    save('input.json', request)
    try: plan = validate(request)
    except InputError as exc:
        result = dict(status='unsupported_input', issues=exc.issues, comparisons=[], scores=None)
        save('result.json', result); return result
    if not plan['candidates']:
        result = dict(status='unsupported_input', comparisons=[], unsupported=plan['blocked'], scores=None)
        save('result.json', result); return result
    needs_model = 'learned' in plan['policies'] or any(o['policy'] == 'learned' for o in plan['opponents'])
    net, metadata = (Network.load(checkpoint or DEFAULT_MODEL) if needs_model else (None, {}))
    model_fp = net.fingerprint if net else None
    certificate = Path(checkpoint or DEFAULT_MODEL).parent / 'validation.json'
    validation = metadata.get('validation', dict(status='not_qualified' if needs_model else 'reference_policy_comparison'))
    if net and certificate.exists():
        cert = json.loads(certificate.read_text(encoding='utf-8'))
        if cert.get('frozen_policy') == model_fp: validation = cert
    base_model_fp=model_fp
    if plan['planner']:
        from .public_planner import PublicPlanner
        probe=PublicPlanner(net,**plan['planner']);model_fp=probe.fingerprint
        # A checkpoint's actor certificate cannot certify a changed planner.
        # All released public-planner configurations remain experimental.
        validation=dict(qualified=False,status='not_qualified',frozen_policy=model_fp,
            base_model=base_model_fp,reason='Public planner requires separate qualification; checkpoint-only certificate does not apply.')
    if needs_model and not validation.get('qualified', False) and not plan['allow_unqualified_policy']:
        result = dict(status='unqualified_policy', scores=None, comparisons=[], policy_validation=validation,
            issues=[_issue('policies', 'unqualified_policy', 'The learned policy failed qualification. Use reference policies or explicitly enable experimental-model diagnostics.')])
        save('result.json', result); return result
    receipt = dict(status='running', program_version=__version__, frozen_policy=model_fp,base_model=base_model_fp,planner=plan['planner'],
        model_name=metadata.get('model_name', Path(checkpoint or DEFAULT_MODEL).stem) if net else None,
        policy_validation=validation,
        completed_games=0, rejected_games=0, requested_samples=plan['samples'], seed_start=plan['seed_start'],
        information='Own initial deck multiset and actually public plays are available. Opponent unseen hand/composition/order are not observations.',
        rules=dict(silence=plan['silence_mode'], current_server_certified=False))
    save('receipt.json', receipt); started = time.monotonic()
    def policy(name):
        if name!='learned':return ReferencePolicy(name)
        if plan['planner']:return PublicPlanner(net,**plan['planner'])
        return LearnedPolicy(net)
    raw_file = gzip.open(output / 'games.jsonl.gz', 'wt', encoding='utf-8') if output else None
    by_card = {c['spec'].name: [] for c in plan['candidates']}
    alpha = .05 / max(1, len(plan['opponents']) * len(plan['policies']) * len(plan['candidates']))
    try:
        for opponent in plan['opponents']:
            for strategy in plan['policies']:
                baseline = None
                for candidate in [dict(spec=plan['reference'], cards=plan['own'], reference=True)] + plan['candidates']:
                    samples = []; diagnostics = Counter()
                    for seed in range(plan['seed_start'], plan['seed_start'] + plan['samples']):
                        pair = []
                        for seat in (0, 1):
                            game = NativeGame((candidate['cards'], opponent['cards']), seed,
                                (policy(strategy), policy(opponent['policy'])), seats=seat,
                                souls=(plan['soul'], opponent['soul']), replacement_slots=plan['slots'],
                                silence_mode=plan['silence_mode'], decision_seconds=plan['decision_seconds'])
                            try: r = game.run()
                            except (DecisionBudgetExceeded, UnsupportedRule) as exc:
                                r = dict(won=None, lost=None, unfinished=True, error=str(exc),
                                         failure_seconds=getattr(exc, 'seconds', None))
                            row = {k: v for k, v in r.items() if k not in ('trace', 'snapshots', 'deck_semantics')}
                            row.update(opponent=opponent['name'], policy=strategy, card=candidate['spec'].name, seed=seed, seat=seat,
                                       reference=bool(candidate.get('reference')))
                            if raw_file: raw_file.write(json.dumps(row, separators=(',', ':')) + '\n')
                            receipt['completed_games'] += 1; receipt['rejected_games'] += r['unfinished']
                            pair.append(None if r['unfinished'] else float(r['won']))
                            if 'candidate_drawn' not in r: diagnostics['unknown'] += 1
                            elif r['candidate_drawn'] == 0: diagnostics['not_received'] += 1
                            elif not r['candidate_played']: diagnostics['received_unplayed'] += 1
                            else: diagnostics['played'] += 1
                            for key in ('candidate_wait', 'candidate_burned', 'candidate_unfunded_turns', 'candidate_slot_blocked_turns'):
                                diagnostics[key] += r.get(key, 0)
                        samples.append((np.mean([0 if x is None else x for x in pair]), np.mean([1 if x is None else x for x in pair])))
                    values = np.asarray(samples)
                    if candidate.get('reference'): baseline = values
                    else:
                        lower, upper = values[:, 0] - baseline[:, 1], values[:, 1] - baseline[:, 0]
                        by_card[candidate['spec'].name].append(dict(opponent=opponent['name'], policy=strategy,
                            win=interval(values[:, 0], values[:, 1]), reference_win=interval(baseline[:, 0], baseline[:, 1]),
                            difference=interval(lower, upper), familywise_difference=interval(lower, upper, alpha),
                            opportunities=dict(diagnostics)))
                    save('receipt.json', receipt)
                    if progress: progress(dict(opponent=opponent['name'], policy=strategy, card=candidate['spec'].name,
                                              completed_games=receipt['completed_games']))
        comparisons = []
        for candidate in plan['candidates']:
            cells = by_card[candidate['spec'].name]
            positive = [r for r in cells if r['difference']['low'] > 0]
            negative = [r for r in cells if r['difference']['high'] < 0]
            complete = all(not r['difference']['unresolved_seed_clusters'] for r in cells)
            if semantic_key(candidate['spec']) == semantic_key(plan['reference']): recommendation = 'equivalent_in_supported_rules'
            elif needs_model and not validation.get('qualified', False): recommendation = 'experimental_only'
            elif cells and complete and plan['samples'] >= 32 and all(r['familywise_difference']['low'] > 0 for r in cells): recommendation = 'conditional_improvement'
            elif cells and complete and plan['samples'] >= 32 and all(r['familywise_difference']['high'] < 0 for r in cells): recommendation = 'conditional_regression'
            elif positive and negative: recommendation = 'policy_or_opponent_sensitive'
            else: recommendation = 'insufficient_evidence'
            comparisons.append(dict(card=candidate['spec'].name, semantics=asdict(candidate['spec']), recommendation=recommendation,
                positive_conditions=[dict(opponent=r['opponent'], policy=r['policy']) for r in positive],
                negative_conditions=[dict(opponent=r['opponent'], policy=r['policy']) for r in negative], conditions=cells))
        if net and net.fingerprint != base_model_fp: raise ValueError('Model changed across candidate comparisons')
        synthetic = sorted({s.name for s in plan['own'] if s.card_id is None} |
                           {s.name for o in plan['opponents'] for s in o['cards'] if s.card_id is None} |
                           {c['spec'].name for c in plan['candidates'] if c['spec'].card_id is None})
        result = dict(status='complete' if comparisons else 'unsupported_input', program_version=__version__,
            reference=asdict(plan['reference']), comparisons=comparisons, unsupported=plan['blocked'],
            policy_validation=receipt['policy_validation'], frozen_policy=model_fp,base_model=base_model_fp,planner=plan['planner'],games=receipt['completed_games'],
            model_name=receipt['model_name'],
            evidence_level='experimental_model' if needs_model and not validation.get('qualified', False) else 'declared_policy_comparison',
            unresolved=receipt['rejected_games'], samples=plan['samples'], synthetic_descriptors=synthetic,
            scope='Conditional replacement in supplied25-card decks and declared opponents. No real-meta weights or universal Gold score.',
            uncertainty='95% paired seed intervals; cross-condition recommendation uses Bonferroni-adjusted tails. Unknown outcomes remain0/1 completion bounds.',
            assumptions=['Initial3 cards and first-turn natural draw', 'No artifacts/mulligan/tribal/death chains',
                         'Automatic callback order is a declared model rule', 'Silence modified-stat cleanup: ' + plan['silence_mode']])
        save('result.json', result); receipt.update(status='complete', elapsed_seconds=time.monotonic() - started)
        save('receipt.json', receipt); return result
    except Exception as exc:
        receipt.update(status='failed', error=repr(exc)); save('receipt.json', receipt); raise
    finally:
        if raw_file: raw_file.close()
