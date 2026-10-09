# Coupled damage integration review

Reviewed 2026-10-08, read-only. Source versions: context-ledger-0.4.0,
paired-response-window-0.2.0, coupled-damage-window-0.1.1. No API or full-game
simulation was run. This review used source inspection and one offline
counterexample; the parent's 149 passing tests were not independently rerun.

**Final state:** the parent fixed the player-HP propagation issue below during
this review. Re-running the exact counterexample against context SHA256
`663540610c3645fbf15bb5796e4a3dce086349688d2f42f339c3764fc1c65c8e`
now rejects resource pricing on both the keyword-only and zero-damage paths.
No remaining reproducible defect was found; the section below records the
original finding and its regression case, not an outstanding blocker.

No blocking defect was found in the default 24-context panel. Immediate damage,
Magic interaction, and keyword increments form a telescoping P1−P0 ledger;
the full total is retained in details and is not added a second time. The same
chosen Magic target is used for Pmid and P1. Targets and the early Haste action
are fixed before the hidden reply; the subsequent ordinary attack observes it.
The implemented target domains separate enemy_monster, enemy_entity, monster,
wide_entity, opponent, and forced AoE; friendly monster targets exclude the
caster. The hand-damage prefix leaves the unimplemented Bullseye trigger partial.

## Fixed finding: keyword-only path ignored explicit player HP

`context_value.evaluate_branch` initializes `enemy_player_hp_after_magic = 30`
and its keyword-only `combat.premium` call omits `own_player_hp`. In contrast,
the damage path passes the context to `coupled.evaluate`, which reads both
`own_player_hp` and `enemy_player_hp`.

Counterexample: a printed 2/2 with Dodge (1), role aggro, one enemy 8/8,
own player HP 1, enemy player HP 30, opponent Gold 6. Use a bound phase-3
reserved context with cost 4 and replace the enemy body list with that enemy.

- `Dodge (1).` receives gross quote **2.8999875278291807**, including keyword
  premium **1.074784335962919**. Its ordinary no-event state has own HP **30**,
  and its enemy-face state has own HP **22**, despite the supplied HP 1.
- `Dodge (1). Magic: Deal 0 DMG to the opponent.` receives a ValueError:
  `Terminal outcome cannot be assigned a resource Gold premium`. This route
  correctly preserves the supplied HP 1 and finds the chosen lethal enemy reply.

Zero damage changes which entry point is used and thereby changes the actual
input state. This is a correctness defect in external-context support, rather
than a pricing calibration question. It does **not** affect the existing
default 24 contexts or the resource bridge, which use the default 30 HP.

Minimum correction: pass `ctx.get('own_player_hp', 30)` and
`ctx.get('enemy_player_hp', 30)` through the keyword-only call, with the same
validation and terminal convention as the damage path. Add the zero-damage
counterfactual above as a regression test.

## Safe cache signature suggestion

For repeated successful coupled evaluations, isolate the cache by the reference
object and use only the effective numeric inputs read by `evaluate`: printed
attack/health; role; ordered enemy and other-ally body lists; effective opponent
Gold; both effective player HP values; ordered damage specs; statuses; effective
response weights; and conditional_haste_limit. Include evaluator version when
persistence is involved. Preserve board order: stable-slot tie breaks and
returned target indices make it observable. Do not key on card name, cost,
unrelated resource-context fields, or future hand identities.

Keep a live reference identity or an object-owned cache, rather than using a
bare reusable Python `id(reference)` as a persistent key. If reference prices
or configuration are mutable, invalidate or namespace by their content/version.
Validate before normalizing a key so invalid strings/booleans are not silently
converted to valid numbers. Store and return deep copies: callers may annotate
plans, outcomes, logs, and candidate details. Do not reuse a damaged-state
result for a keyword-only original-board result. This is a performance
recommendation, not an additional observed defect.

## Reviewed source hashes

SHA256:

- context_value.py: `7e6cd9f9772d8579b4ff9918c070033b751b1c569c533965acbe3bcbe8c3b738`
- combat_increment.py: `e9b565a7efe3c92b6f559b1c7fac3058ec767ee70a0135fa4ef3227f72680623`
- coupled_magic.py: `c8fc58b2bfbb946f070cf96448c000fada4da8d0daf0888c623ea1b8fc4de6c7`
- heuristic_contexts.py: `d97e2af5f49de2b758d03dd8880b8d585c3dbd09de6f5a9e31e44e550eb4c85c`
