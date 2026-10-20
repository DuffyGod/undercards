"""One held Tsunderplane's public deployment/attack ordering, without draws.

This is not a deck search or a future-turn search. The caller decides whether to
enable this local policy extension. Only a currently legal #21 can be projected;
the environment remains responsible for executing the selected deployment.
"""
from dataclasses import replace

from model import (CARDS, attack, board_score, choose_combat,
                   choose_deployment, hurt, unit)


def _combat_endpoint(view, policy, config):
    """Apply the existing current-turn policy to an immutable public view."""
    if view.board.hp <= 0 or view.board.foe_hp <= 0:
        return view
    plan, _ = choose_combat(view, policy, config)
    board = view.board
    for actor, target in plan:
        if board.hp <= 0 or board.foe_hp <= 0:
            break
        board, _ = attack(board, actor, target, config)
    return replace(view, board=board)


def _project_plane(view, held):
    """Exactly #21's deterministic Play/Magic; no other card or draw effects."""
    if (held.cid != 21 or held not in view.hand
            or CARDS[21]['cost'] > view.cash
            or len(view.board.own) >= view.slots
            or view.board.hp <= 0 or view.board.foe_hp <= 0):
        raise ValueError('Plane projection requires a current legal deployment')
    damaged = tuple(hurt(enemy, 1)[0] for enemy in view.board.foe)
    board = replace(view.board,
                    own=view.board.own + (unit(held),),
                    foe=tuple(enemy for enemy in damaged if enemy.h > 0),
                    foe_hp=view.board.foe_hp - 3)
    return replace(view, board=board,
                   hand=tuple(card for card in view.hand if card.uid != held.uid),
                   cash=view.cash - CARDS[21]['cost'])


def precombat_choice(view, policy, config):
    """Return a held #21 uid to deploy before combat, or None.

    Public lethal from Plane then ordinary attacks has priority. Otherwise the
    Plane must already be the greedy deployment choice; compare the two orders
    for that same card, including its Haste attack in either order. A tie keeps
    the original combat-first policy. No other deployment is simulated.
    """
    if (view.board.hp <= 0 or view.board.foe_hp <= 0
            or len(view.board.own) >= view.slots
            or CARDS[21]['cost'] > view.cash):
        return None
    planes = sorted((held for held in view.hand if held.cid == 21),
                    key=lambda held: held.uid)
    if not planes:
        return None

    combat_first = _combat_endpoint(view, policy, config)
    if combat_first.board.foe_hp <= 0:
        return None  # Existing attacks already win; do not spend an extra card.

    endpoints = {}
    for held in planes:
        end = _combat_endpoint(_project_plane(view, held), policy, config)
        endpoints[held.uid] = end
        if end.board.foe_hp <= 0:
            return held.uid

    preferred = choose_deployment(view, policy)
    held = next((card for card in planes if card.uid == preferred), None)
    if held is None:
        return None

    if combat_first.board.hp > 0 and combat_first.board.foe_hp > 0:
        combat_first = _combat_endpoint(
            _project_plane(combat_first, held), policy, config)
    plane_first = endpoints[held.uid]
    if board_score(plane_first.board, policy) > board_score(combat_first.board, policy):
        return held.uid
    return None
