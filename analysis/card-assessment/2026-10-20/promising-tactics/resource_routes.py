"""Nine analyst-selected resource/timing candidates, explicit conditional routes.

No text parser, hidden draw oracle, opponent policy, or game simulator. Hand and
board preconditions are part of each record; all realized plays are charged.
"""
from tactic_core import route, compare, CARDS, B, F, hit, live


def build_routes():
    records, comparisons, notes = [], [], []

    def add(*args, **kwargs):
        record = route(*args, **kwargs)
        records.append(record)
        return record

    # Bomb: same three held cards. Playing the free card first changes which
    # non-Generated card is the cheapest remaining forced sacrifice.
    common = dict(condition='Cash >=3; empty own field; hand exactly Bomb, '
                  'non-Generated Tiny Froggit and Aaron; legal ordinary enemy '
                  'Rock Pet 3/3; no death triggers or damage prevention.',
                  features=dict(starting_hand_ids=[29, 196, 15], minimum_cash=3),
                  unknown=['Retained Aaron and Tiny have different future '
                           'option values; uniform marginal hand price hides identity.'])
    add(29, 'bomb_cheapest_replacement', 'bomb_erase_tiny', [], [B(3, 3)],
        [B(4, 3)], [], erased=1,
        path=['Play Bomb for 3G; Tiny 0G is cheapest remaining eligible card.',
              'Erase Tiny and deal 3 to Rock Pet; retain Aaron.'], **common)
    add(29, 'bomb_cheapest_replacement', 'tiny_then_bomb_erase_aaron', [], [B(3, 3)],
        [B(1, 1), B(4, 3)], [], used=[196, 29], erased=1,
        path=['Play Tiny for 0G.', 'Play Bomb for 3G; erase remaining Aaron.',
              'Deal 3 to Rock Pet; both newly played bodies remain.'], **common)

    # Microwave's nominal one-card, one-gold body actually consumes two cards.
    add(226, 'microwave_spare_card', 'play_and_erase', [], [], [B(3, 2)], [],
        erased=1, condition='Cash >=1; hand contains Microwave and one '
        'legal chosen erasable card; a free deployment slot.',
        path=['Pay 1G, play Microwave, erase the chosen other hand card.'],
        unknown=['Taunt protection and erased-card identity beyond uniform '
                 'hand price are not priced.'])
    add(226, 'microwave_spare_card', 'do_not_play', [], [], [], [],
        used=[], paid=0, condition='Same root: retain Microwave and the other '
        'card now; this is an instantaneous pass, not a safe next-turn claim.',
        path=['Do not commit either card or any gold.'],
        unknown=['Future cost of not establishing Taunt/board is not included.'])

    # Returning a ready attacker first throws away an available attack. The
    # returned card is ONE hand card, not a retained battlefield Aaron as well.
    for attack_first in (False, True):
        add(113, 'igloo_ready_aaron',
            'aaron_face_then_igloo' if attack_first else 'igloo_without_aaron_attack',
            [B(6, 5)], [], [B(5, 4)], [], gained=1,
            damage=6 if attack_first else 0,
            condition='Existing ordinary Aaron 6/5 is ready; enemy field '
            'empty, enemy HP >=6; cash >=4 and own field initially has one '
            'body, so Igloo can legally enter before its return Magic.',
            path=(['Aaron attacks hero for 6.'] if attack_first else []) +
                 ['Play Igloo for 4G and return Aaron to hand.'],
            unknown=['Returned-card damage/base-stat reset and future replay '
                     'are not assumed; no returned-body stock remains on board.'])

    # Same two ordinary cards and budget, same final board; draw identities are
    # revealed only after drawing and are not played in either route.
    river_condition = ('Cash >=9; starting own hand has 5 cards including '
                       'River Person and Froggit; enemy hand has 6; both '
                       'decks have enough ordinary cards without Turbo or '
                       'draw replacement; initially empty fields.')
    river_first = add(154, 'river_same_two_cards', 'river_then_froggit', [], [],
        [B(2, 3), B(4, 7)], [], used=[154, 2], gained=2,
        condition=river_condition,
        path=['Play River Person: own hand 5 ->4 ->6 (draw 2); enemy draws 0.',
              'Play held Froggit: own hand 6 ->5.'],
        features=dict(final_own_hand=5, final_enemy_hand=6))
    river_last = add(154, 'river_same_two_cards', 'froggit_then_river', [], [],
        [B(2, 3), B(4, 7)], [], used=[2, 154], gained=3,
        condition=river_condition,
        path=['Play held Froggit: own hand 5 ->4.',
              'Play River Person: own hand 4 ->3 ->6 (draw 3); enemy draws 0.'],
        features=dict(final_own_hand=6, final_enemy_hand=6))
    comparisons.append(compare(river_last, river_first,
        'Same paid cards, gold and bodies: playing already-held Froggit before '
        'the refill retains exactly one additional ordinary card.'))
    add(154, 'river_opponent_refill', 'full_hand_low_enemy_hand', [], [],
        [B(4, 7)], [], gained=0, enemy_gained=5,
        condition='Own hand initially7 including River; enemy hand1; enough '
        'non-Turbo cards in enemy deck; no other actions or modifiers.',
        path=['River leaves own hand6, so draw0; enemy draws5 to reach6.'],
        unknown=['Enemy gained card identities and future cash/hand pressure '
                 'differ from our cards; symmetric hand price is a hypothesis.'])

    # Sadmobile's draw discount is only cash if the drawn card is really used.
    # Previous-turn spending is a CONDITION, not a free achieved strategy.
    for qualified in (False, True):
        add(546, 'sadmobile_previous_spend_' + ('7' if qualified else '6'),
            'draw_then_play_froggit', [], [], [B(5, 7), B(2, 3)], [],
            used=[546, 2], paid=6 if qualified else 8, gained=1,
            condition=('Previous turn spent ' + ('7' if qualified else '6') +
                       'G; now cash >=8; draw actually reveals Froggit; '
                       'two free slots. Decide to play it after revelation.'),
            path=['Play Sadmobile for6G and reveal Froggit.',
                  'The qualified draw costs0G; otherwise it costs2G.',
                  'Play the now-known Froggit; do not also keep a hand-card reward.'],
            unknown=['Cost/board consequences of the previous-turn7G plan '
                     'are outside this root; do not infer paying extra solely '
                     'to qualify is worthwhile.'])
    add(546, 'sadmobile_discount_unspent', 'qualified_draw_held', [], [],
        [B(5, 7)], [], gained=1,
        condition='Previous turn spent7G; now play Sadmobile and retain one '
        'actually drawn usable card; no later payment within endpoint.',
        path=['Pay6G, draw one card, apply its -2COST and hold it.'],
        unknown=['Unspent discount has no realized gold reward; cost floor '
                 'and eventual use are not inferred.'])

    # Same current two-card hand, no fabricated combo card or extra spending.
    tasque_condition = ('Cash >=8; hand contains held Froggit and Tasque; '
                        'no earlier qualifying plays this turn; initially '
                        'empty ordinary fields; preserve same final positions.')
    tasque_early = add(624, 'tasque_same_two_cards', 'tasque_then_froggit', [], [],
        [B(2, 3), B(2, 3)], [], used=[624, 2],
        condition=tasque_condition,
        path=['Play Tasque first: zero prior 1+base-cost cards, so2/3.',
              'Play Froggit; Tasque Magic does not retroactively update.'])
    tasque_late = add(624, 'tasque_same_two_cards', 'froggit_then_tasque', [], [],
        [B(2, 3), B(3, 4)], [], used=[2, 624],
        condition=tasque_condition,
        path=['Play Froggit for2G.', 'Play Tasque for6G: one previous '
              'qualifying card gives ATK+1/HP+1, so3/4.'],
        unknown=['Haste continuation is not priced; no enemy to attack and '
                 'Haste is not permission to hit hero.'])
    comparisons.append(compare(tasque_late, tasque_early,
        'Identical hand consumption and8G: already-planned Froggit first '
        'gives Tasque one additional +1/+1 without a fabricated extra card.'))

    # Use14G in BOTH rows so both orders are feasible, then separately expose
    # the tighter11G funding condition; Transparency remains unchanged.
    guard_condition = ('Cash14G, hand exactly Knight Knight and Casual Guard2, '
                       'no prior base9+ card played this turn, empty fields; '
                       'no cost modifiers; preserve final positions.')
    guard_early = add(743, 'guard_same_two_cards', 'guard_then_knight', [], [],
        [B(5, 9), B(4, 4)], [], used=[743, 17], paid=14,
        condition=guard_condition,
        path=['Play Guard first for5G.', 'Play Knight for9G.'],
        unknown=['Residual Transparency not priced; same in both orders.'],
        features=dict(minimum_cash_for_this_order=14))
    guard_late = add(743, 'guard_same_two_cards', 'knight_then_guard', [], [],
        [B(5, 9), B(4, 4)], [], used=[17, 743], paid=11,
        condition=guard_condition,
        path=['Play Knight with base9G first.',
              'While still in hand Guard now costs5-3=2G; play it.'],
        unknown=['Residual Transparency not priced; same in both orders.'],
        features=dict(minimum_cash_for_this_order=11))
    comparisons.append(compare(guard_late, guard_early,
        'Same two hand cards and final bodies, high-base-cost trigger first '
        'saves3 actualG; unlike merely holding a discount, payment is realized.'))

    # Flameguy: attack BEFORE sacrifice; killed body's F is actually removed.
    for attack_first in (False, True):
        add(812, 'flameguy_ready_aaron',
            'aaron_face_then_sacrifice' if attack_first else 'sacrifice_before_attack',
            [B(6, 5)], [], [B(5, 4)], [], gained=2,
            damage=6 if attack_first else 0,
            condition='Existing Aaron6/5 ready; enemy field empty, HP>=6; '
            'cash>=4; after Flameguy leaves hand, two draws fit and deck '
            'contains at least2 non-Turbo ordinary cards.',
            path=(['Aaron attacks hero for6.'] if attack_first else []) +
                 ['Play Flameguy4G, kill Aaron, draw2 usable cards.'],
            unknown=['Sacrificed Aaron has no Dust or extra triggers; draw '
                     'identities and future utility use common hand price.'])
    add(812, 'flameguy_spent_tiny', 'sacrifice_unready_tiny', [B(1, 1)], [],
        [B(5, 4)], [], gained=2,
        condition='Existing Tiny1/1 cannot attack now; cash>=4, one free '
        'entry slot and enough hand/deck room for2 ordinary draws.',
        path=['Play Flameguy, kill Tiny, draw2; remove Tiny body stock.'])

    # Long Sink: at hero27HP, three HEAL is real; same enemy and timing in both
    # rows. No attack + heal may dominate a tiny trade at central face price.
    sink_condition = ('Own hero27/30HP, no own monsters, ordinary enemy '
                      'Tiny1/1 without triggers, cash>=5; no other end '
                      'effects, enemy action, silence or HP changes.')
    sink_attack = add(509, 'sink_hero27_tiny', 'haste_kill_tiny', [], [B(1, 1)],
        [B(4, 5)], [], stage='own_end', condition=sink_condition,
        path=['Play Sink4/6 for5G, attack Tiny: kill it, take1, remain4/5.',
              'Sink attacked, so no own-end hero heal.'])
    sink_idle = add(509, 'sink_hero27_tiny', 'decline_attack_heal3', [], [B(1, 1)],
        [B(4, 6)], [B(1, 1)], heal=3, stage='own_end',
        condition=sink_condition,
        path=['Play Sink4/6 and decline its Haste attack.',
              'At own end heal hero27->30, leave enemy Tiny alive.'])
    comparisons.append(compare(sink_idle, sink_attack,
        'Same held card/payment/own-end exposure: retaining1HP of Sink plus '
        'real3 hero healing competes with removing one enemy Tiny.'))
    add(509, 'sink_hero30_tiny', 'full_hp_idle', [], [B(1, 1)],
        [B(4, 6)], [B(1, 1)], heal=0, stage='own_end',
        condition='As above but own hero30/30HP; no damage before own end.',
        path=['Decline attack; own-end actual healing is0, not3.'])

    notes.extend([
        'Nine candidates are outside the existing49 profiles:29,226,113,154,'
        '546,624,743,812,509. All routes are local conditional endpoints.',
        'J includes all played/erased cards and usable own/enemy gains. A '
        'generated/drawn card then played has +1gain and -1play, not both '
        'a battlefield asset and a retained inventory reward.',
        'J>0 is NOT a universal deployment/carry gate: with F(6/5)=5, gold=1 '
        'and hand=1, vanilla Aaron J=-1. A pass without future exposure does '
        'not prove refusing all board development is sound.',
        'Previous-turn qualification for Sadmobile is a conditional root, '
        'not a free strategy. Charge any incremental prior action cost '
        'separately before making a recommendation.',
        'Haste is monster-only on entry. Existing ready Aaron may attack '
        'hero in these empty-enemy roots; no generated Haste hero hits used.',
        'Entry requires a real free slot BEFORE Igloo/Flameguy Magic returns '
        'or kills an ally. Full-board entry is not made legal by its payoff.',
    ])
    return records, comparisons, notes
