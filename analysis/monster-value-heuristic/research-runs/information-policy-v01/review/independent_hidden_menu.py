"""Independent small-game enumeration: imports no production research model.

OwnHP horizon only. No income/draw, four alternating action windows. Formal hidden spells are Generated copies from Bone Box; native Worsening's
conditional generated copy is separately probed and cannot be paid with zero
remaining enemy GOLD. Magic for observed Lady
Garf resolved before this position; her full current/base/printed cost is 4.
"""
from dataclasses import dataclass, replace, asdict
from functools import lru_cache
from fractions import Fraction
import hashlib
import json
from pathlib import Path

@dataclass(frozen=True)
class Body:
    card: int
    attack: int
    health: int
    taunt: bool = False
    reduction: bool = False
    attacked: bool = False

@dataclass(frozen=True)
class State:
    hp: int = 15
    enemy_hp: int = 30
    ally: Body | None = None
    foe: Body | None = Body(246, 3, 6)
    hand: tuple = (14, 15)
    own_gold: int = 5
    enemy_gold: int = 2
    spell: int = 0
    spell_generated: bool = True
    enemy_acted: bool = False
    delayed_target: str = ''
    generated: tuple = ()

CARDS = {
    14: Body(14, 4, 5, True, True),
    15: Body(15, 6, 5),
}
COSTS = {14: 5, 15: 5, 79: 1, 86: 2, 246: 4}

def canonical(s):
    if s.ally and s.ally.health <= 0:
        s = replace(s, ally=None)
    if s.foe and s.foe.health <= 0:
        s = replace(s, foe=None)
    return s


def attacks(s, owner):
    if owner == 'own':
        if not s.ally or s.ally.attacked:
            return []
        a = s.ally
        out = [('attack_face', replace(s, enemy_hp=max(0, s.enemy_hp-a.attack),
                                       ally=replace(a, attacked=True)))]
        if s.foe:
            b = s.foe
            incoming = max(0, b.attack-(1 if a.reduction and COSTS[b.card] <= 4 else 0))
            out.append(('attack_monster', canonical(replace(s,
                ally=replace(a, health=a.health-incoming, attacked=True),
                foe=replace(b, health=b.health-a.attack)))))
        return out
    if not s.foe or s.enemy_acted:
        return []
    a = s.foe
    out = []
    if not s.ally or not s.ally.taunt:
        out.append(('attack_face', replace(s, hp=max(0, s.hp-a.attack), enemy_acted=True)))
    if s.ally:
        b = s.ally
        incoming = max(0, a.attack-(1 if b.reduction and COSTS[a.card] <= 4 else 0))
        out.append(('attack_monster', canonical(replace(s,
            ally=replace(b, health=b.health-incoming),
            foe=replace(a, health=a.health-b.attack), enemy_acted=True))))
    return out


def casts(s):
    if s.spell == 0 or COSTS[s.spell] > s.enemy_gold:
        return []
    out = []
    for key in ('ally', 'foe'):
        b = getattr(s, key)
        if b is None:
            continue
        if s.spell == 79:
            nb = replace(b, taunt=False, reduction=False)
            delayed = ''
        else:
            nb = replace(b, attack=max(0, b.attack-1), health=b.health-2)
            delayed = key if not s.spell_generated else ''
        out.append((f'cast_{s.spell}_{key}', canonical(replace(s,
            **{key: nb}, spell=0, enemy_gold=s.enemy_gold-COSTS[s.spell],
            delayed_target=delayed))))
    return out


def deployments(s):
    if s.ally is not None or s.own_gold < 5:
        return []
    return [(f'play_{cid}', replace(s, ally=replace(CARDS[cid], attacked=True),
        hand=tuple(c for c in s.hand if c != cid), own_gold=s.own_gold-5)) for cid in s.hand]


def end_enemy(s):
    # Delay checks death at the current turn end; a dead named actor cannot
    # reappear during this finite position. Generation occurs, not a free cast.
    if s.delayed_target and getattr(s, s.delayed_target) is None:
        return replace(s, generated=s.generated+(86,), delayed_target='')
    return replace(s, delayed_target='')


@lru_cache(None)
def own_window(s, last=False):
    # Actions strictly consume hand/ready resources, so this recursion is finite.
    exits = [(('end',), s)]
    for action, ns in deployments(s)+attacks(s, 'own'):
        exits.extend(((action,)+trace, e) for trace, e in own_window(ns, last))
    return tuple(exits)


@lru_cache(None)
def enemy_window(s):
    exits = [(('end',), end_enemy(s))]
    for action, ns in casts(s)+attacks(s, 'enemy'):
        exits.extend(((action,)+trace, e) for trace, e in enemy_window(ns))
    return tuple(exits)


def continuation_value(s):
    s = replace(s, ally=replace(s.ally, attacked=False) if s.ally else None)
    # All own choices occur after enemy actions are public. This worldwise
    # optimization is used only to build a conditional matrix. A separate
    # common-policy witness below certifies it does not overclaim maxmin.
    choices = []
    for own_trace, after_own in own_window(s):
        after_own = replace(after_own, enemy_acted=False)
        replies = [(end.hp, trace, end) for trace, end in enemy_window(after_own)]
        worst = min(replies, key=lambda r:r[0])
        choices.append((worst[0], own_trace, worst))
    return max(choices, key=lambda r:r[0])


def root_value(spell, root, spell_generated=True):
    s = State(spell=spell, spell_generated=spell_generated)
    if root:
        s = dict(deployments(s))[f'play_{root}']
    replies = []
    for trace, e in enemy_window(s):
        value, own_trace, worst = continuation_value(e)
        replies.append((value, trace, own_trace, worst))
    return min(replies, key=lambda r:r[0]), replies


def fixed_root_policy(spell, root):
    """A single non-clairvoyant policy: fixed card now; attack live enemy later."""
    s = dict(deployments(State(spell=spell)))[f'play_{root}']
    outcomes = []
    for _, after_enemy in enemy_window(s):
        after_enemy = replace(after_enemy, ally=replace(after_enemy.ally, attacked=False)
                              if after_enemy.ally else None)
        moves = dict(attacks(after_enemy, 'own'))
        after_own = moves.get('attack_monster', after_enemy)
        after_own = replace(after_own, enemy_acted=False)
        outcomes.extend(e.hp for _, e in enemy_window(after_own))
    return min(outcomes)


def main():
    matrix = {}
    witnesses = {}
    generated_seen = 0
    for root in (14, 15, 0):
        name = {14:'Jerry',15:'Aaron',0:'hold'}[root]
        matrix[name] = {}
        for spell in (79,86):
            worst, replies = root_value(spell, root)
            matrix[name][str(spell)] = worst[0]
            witnesses[f'{name}/{spell}'] = {
                'enemy_first':worst[1], 'own_second':worst[2],
                'enemy_second':worst[3][1], 'terminal':asdict(worst[3][2]),
                'enemy_first_terminal_histories':len(replies),
            }
            generated_seen += sum(bool(r[3][2].generated) for r in replies)
    oracle = min(max(matrix[r][str(w)] for r in matrix) for w in (79,86))
    root_locked_upper = max(min(row.values()) for row in matrix.values())
    common_aaron = {str(w):fixed_root_policy(w,15) for w in (79,86)}
    common_jerry = {str(w):fixed_root_policy(w,14) for w in (79,86)}
    lower = min(common_aaron.values())
    mixed = {str(w):Fraction(2,3)*common_aaron[str(w)]+Fraction(1,3)*common_jerry[str(w)] for w in (79,86)}
    assert common_jerry == {'79':9,'86':15}
    assert list(mixed.values()) == [11,11]
    # Dual weights are an algebraic bound, never empirical world frequencies.
    dual = {name:Fraction(2,3)*row['79']+Fraction(1,3)*row['86'] for name,row in matrix.items()}
    assert max(dual.values()) == 11
    assert matrix == {'Jerry':{'79':9,'86':15},'Aaron':{'79':12,'86':9},'hold':{'79':9,'86':12}}, matrix
    assert (oracle, root_locked_upper, lower) == (12,9,9)
    assert generated_seen == 0
    native_probe = {}
    native_generated_seen = 0
    for root in (14,15,0):
        worst,replies=root_value(86,root,False)
        native_probe[str(root)] = worst[0]
        native_generated_seen += sum(bool(r[3][2].generated) for r in replies)
    assert native_generated_seen > 0
    here = Path(__file__).resolve().parent
    snap = here.parents[4]/'skills/undercards/references/snapshot.json'
    # Resolve by ancestor search to remain relocatable inside this repository.
    snap = next(p/'skills/undercards/references/snapshot.json' for p in here.parents
                if (p/'skills/undercards/references/snapshot.json').exists())
    native = json.loads(snap.read_text())
    keep = {2,4,9,11,14,15,79,86,96,246,351,402}
    report = {
        'method':'independent exact small-game action enumeration; no production imports',
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'snapshot_sha256':hashlib.sha256(snap.read_bytes()).hexdigest(),
        'cards':[c for c in native['cards'] if c['id'] in keep],
        'matrix_own_hp':matrix,
        'worldwise_best_then_min':oracle,
        'root_locked_upper_bound':root_locked_upper,
        'common_policy_lower_bound':lower,
        'common_policy':'Play Aaron at root; on next own turn attack live enemy if possible.',
        'common_policy_world_values':common_aaron,
        'second_common_policy':'Play Jerry at root; on next own turn attack live enemy if possible.',
        'second_common_policy_world_values':common_jerry,
        'separate_randomized_expected_utility':{
            'assumptions':'Hidden world fixed before private root randomization; enemy sees deployed root card and adapts its response. Objective is expected HP, not physical HP floor.',
            'own_policy_weights':{'Aaron':'2/3','Jerry':'1/3'},
            'world_expected_hp':{w:str(v) for w,v in mixed.items()},
            'min_world_expected_hp':'11',
            'dual_upper_certificate_weights_not_empirical_probabilities':{'79':'2/3','86':'1/3'},
            'weighted_upper_values':{w:str(v) for w,v in dual.items()},
        },
        'clairvoyance_overstatement_hp':oracle-lower,
        'generated_worsening_histories_seen':generated_seen,
        'formal_hidden_menu_both_generated':True,
        'common_legal_generated_source':402,
        'separate_native_worsening_rule_probe':{'values':native_probe,'generated_histories_seen':native_generated_seen},
        'worst_reply_witnesses':witnesses,
        'limits':[
            'No income/draw. Existing Lady Garf Magic already resolved.',
            'Costs printed/base/current all 4 for the observed Lady Garf.',
            'Formal hidden menus are generated by Bone Box402; their different SOUL identities do not violate main-deck construction.',
            'Information hypothesis: Bone Box choice/result remains hidden to the opponent; not verified against server UI.',
            'Formal Generated Worsening does not add a copy. Separate native-Worsening probe records actual Delay generation, unpayable at enemy GOLD0.',
            'Original/death identity is unambiguous: no summon/copy/revival of units in this position.',
            'This finite-window exact result is not a universal native card score.',
            'maxmin is a deterministic/physical-HP guarantee; randomized expected utility is a different objective.',
        ],
    }
    (here/'independent-hidden-menu.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['matrix_own_hp','worldwise_best_then_min','root_locked_upper_bound','common_policy_lower_bound','generated_worsening_histories_seen']},ensure_ascii=False))

if __name__ == '__main__':
    main()
