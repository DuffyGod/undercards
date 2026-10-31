"""Complete, copy-legal monster decks used as declared reference scenarios."""
from .catalog import deck, Spec, Effect
import random


def base_deck():
    return deck(['Rock Pet'] * 3 + ['Froggit'] * 3 + ['Moldsmal'] * 3 + ['Spider'] * 3 +
                ['Candy Dish'] * 3 + ['Aaron'] * 3 + ['Bench'] * 3 + ['Fishing Rod'] * 2 + ['Bloody Tree'] * 2)


def opponents():
    return {
        'pressure': deck(['Ice Cap'] * 3 + ['Spider'] * 3 + ['Rock Pet'] * 3 + ['Moldsmal'] * 3 +
            ['Froggit'] * 3 + ['Aaron'] * 3 + ['Candy Dish'] * 3 + ['Charles'] * 3 + ['Bench']),
        'defense': deck(['Dummy'] * 3 + ['Candy Dish'] * 3 + ['Charles'] * 3 + ['Sad Dragon'] * 3 +
            ['Vegetoid'] * 3 + ['Scarf Mouse'] * 3 + ['Aaron'] * 3 + ['Rock Pet'] * 3 + ['Fishing Rod']),
        'refill': deck(['Fishing Rod'] * 3 + ['Bench'] * 3 + ['Bloody Tree'] * 3 + ['Rock Pet'] * 3 +
            ['Froggit'] * 3 + ['Scarf Mouse'] * 3 + ['Aaron'] * 3 + ['Candy Dish'] * 3 + ['Vegetoid']),
    }


def training_pool():
    # New numeric tuples and single mechanisms; composed evaluation cards are
    # deliberately absent from the training pool.
    pool = []; rng = random.Random(20261031)
    for index, (kw, effects) in enumerate([
        ((), ()), ((('haste', 1),), ()), ((('charge', 1),), ()), ((('taunt', 1),), ()),
        ((('armor', 1),), ()), ((('dodge', 1),), ()),
        ((), (Effect('play', 'draw', 'owner', 1),)), ((), (Effect('end', 'draw', 'owner', 1),)),
        ((), (Effect('start', 'buff', 'self', 1),)), ((), (Effect('end', 'buff', 'self', 1, 1),)),
        ((), (Effect('play', 'silence', 'enemy'),)), ((), (Effect('play', 'damage', 'all_enemy', 2),)),
        ((), (Effect('play', 'heal', 'owner', 4),)),
    ]):
        for j in range(8):
            attack, health = rng.randrange(0, 8), rng.randrange(1, 10)
            cost = max(0, min(8, round((attack + health) / 3) + int(bool(effects)) + rng.choice((-1, 0, 1))))
            pool.append(Spec(f'train_{index}_{j}', cost, attack, health, kw, effects))
    return pool
