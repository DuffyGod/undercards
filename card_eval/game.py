"""Twenty-five explicit semantic cards on BOTH sides; no aggregate host roles."""
from dataclasses import replace, asdict
from .legacy import environment, bridge
from .knowledge import Knowledge

Config = environment.Config
Unit = environment.Unit
DecisionBudgetExceeded = environment.DecisionBudgetExceeded


class NativeGame(environment.LearningGame):
    def __init__(self, decks, seed, agents, seats=0, souls=('INTEGRITY', 'INTEGRITY'),
                 replacement_slots=(0,), silence_mode='retain', recorder=None, decision_seconds=.25):
        if len(decks) != 2 or any(len(d) != 25 for d in decks): raise ValueError('Two explicit25-card decks required')
        if len(souls) != 2 or any(s not in ('INTEGRITY', 'KINDNESS') for s in souls): raise ValueError('Unsupported SOUL')
        if not replacement_slots or any(type(i) is not int or not 0 <= i < 25 for i in replacement_slots):
            raise ValueError('Replacement entity slots required')
        self.native_decks = tuple(tuple(d) for d in decks); self.souls = tuple(souls)
        self.replacement_slots = frozenset(replacement_slots)
        candidate = self.native_decks[0][replacement_slots[0]]
        self.knowledge = Knowledge(self.native_decks)
        # With no deck-generation/return mechanics, natural draws exhaust25
        # cards and fatigue31 kills before start-healing (hero ceiling30).
        # Sixty own turns therefore covers supported healing stalls; this is
        # a simulator completion bound, not a claimed server turn limit.
        super().__init__('wide', seed, Config(rounds=60, seat=seats, soul=souls[0]), candidate,
                         agents, silence_mode=silence_mode, recorder=recorder, decision_seconds=decision_seconds)
        self.structure = 'explicit_25_card_decks'
        # Retain the exact initial entity permutations and opening draws.
        for actor, p in enumerate(self.players):
            def convert(card):
                return replace(card, kind='candidate' if actor == 0 and card.uid in self.replacement_slots else 'custom')
            p.hand = list(map(convert, p.hand)); p.deck = list(map(convert, p.deck))
        self.copies = len(self.replacement_slots)
        self.candidate_drawn = sum(c.kind == 'candidate' for c in self.players[0].hand)
        self.candidate_played = self.candidate_burned = self.candidate_first_turn = 0
        self.candidate_wait = self.candidate_unfunded_turns = self.candidate_slot_blocked_turns = 0

    def spec(self, actor, card):
        return self.native_decks[actor][card.uid]

    def event(self, actor, action, **kwargs):
        super().event(actor, action, **kwargs)
        if action == 'play':
            # Resolve only the card that has actually become public. Neither
            # fields() nor any policy consults an opponent's other descriptors.
            self.knowledge.observe_play(actor, self.native_decks[actor][kwargs['card']['uid']])

    def view(self, actor):
        a, b = self.players[actor], self.players[1 - actor]
        # ABI field expresses a public possibility only. Never count actual
        # hidden removal cards to provide a private-deck oracle to the policy.
        possible_control = int(bool(b.deck or b.hand))
        return bridge.View(tuple(a.hand), tuple(a.units), tuple(b.units), a.hp, b.hp, a.cash, b.cash,
            a.turn, b.turn, self.cfg.seat if actor == 0 else 1 - self.cfg.seat,
            len(a.deck), possible_control, replace(self.cfg, soul=self.souls[actor]))

    def observation(self, actor):
        obs = super().observation(actor)
        obs['config']['soul'] = self.souls[actor]
        obs['own_soul'] = self.souls[actor]; obs['enemy_soul'] = self.souls[1 - actor]
        obs.update(self.knowledge.fields(actor))
        return obs

    def act_turn(self, actor):
        previous = self.cfg
        self.cfg = replace(self.cfg, soul=self.souls[actor])
        try: super().act_turn(actor)
        finally: self.cfg = previous

    def run(self):
        result = super().run()
        result['souls'] = list(self.souls)
        result['deck_semantics'] = [[asdict(s) for s in d] for d in self.native_decks]
        return result
