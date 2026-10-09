"""Semantic teaching examples, never card quality or Gold-value labels."""


def module(kind, trigger, target, evidence, amount=None, basis='fixed', stat='none',
           count=1, repeat='none', reference=None, condition='', choice=None):
    return {'kind': kind, 'trigger': trigger, 'target': target, 'amount': amount,
            'amount_basis': basis, 'stat': stat, 'count': count,
            'repeat_rule': repeat, 'card_ref': reference, 'condition': condition,
            'evidence': evidence, 'choice_group': choice}


def example(text, modules, codes, timing, exposure, correction):
    return {'input_effect': text,
            'correct_annotation': {'printed_effect': text, 'modules': modules,
                                   'condition_codes': codes, 'timing': timing,
                                   'silence_exposure': exposure, 'unresolved': []},
            'common_error_and_correction': correction}


def examples():
    buff = 'Magic: Give an ally monster +2 ATK.'
    growth = 'Magic: Gain ATK +1/HP +1 for each card in your hand.'
    damage = 'Magic: Deal 1 DMG to a monster for each other monster.'
    chain = 'After this attacks and kills a monster, deal 1 DMG to a random enemy monster. If it died, repeat.'
    discount = 'Dust: Give all cards in your hand -1 COST.'
    exact = 'Bullseye: Draw a card.'
    choice = 'Magic: Deal 3 DMG to an enemy or give an ally monster +3 ATK.'
    return [
        example('', [], [], 'none', 'none', '空白主体无能力；正常攻击不是额外效果。'),
        example(buff, [module('buff', 'magic', 'ally', buff, 2, stat='ATK')],
                ['target_exists'], 'immediate', 'none', '沉默施法者不撤回已给另一友军的增益；body只指自身持续数值。'),
        example(growth, [module('buff', 'magic', 'self', growth, 1, 'hand_size_after_play', 'both')],
                ['hand_size'], 'immediate', 'body', 'amount=1是乘数，最终增益为打出后的手牌数；可变不等于未知。'),
        example(damage, [module('damage', 'magic', 'other', damage, 1, 'other_monster_count')],
                ['target_exists', 'enemy_count', 'ally_count'], 'immediate', 'none',
                '一次总伤害=其他怪物数×1，不拆成多次1点；其他怪物计双方并排除该主体。'),
        example('Haste. Dodge (1). ' + chain,
                [module('combat', 'passive', 'self', 'Haste.'),
                 module('combat', 'passive', 'self', 'Dodge (1).', 1),
                 module('damage', 'attack', 'enemy_monster', chain, 1, repeat='on_kill',
                        condition='攻击击杀后开始；随后每次随机1伤只有再击杀才继续')],
                ['target_exists', 'random_outcome'], 'conditional', 'future',
                '普通kill允许过量伤害，不是exact_kill；Dodge仅抵消一个伤害实例，未写重置就不重置。'),
        example(exact, [module('draw', 'bullseye', 'self', exact)], ['exact_kill'],
                'conditional', 'future', 'Bullseye要求目标HP恰好变成0且死亡，不是攻击造成0DMG；未来仍可触发。'),
        example(discount, [module('discount', 'dust', 'hand', discount, -1)], ['death_required'],
                'death', 'future', '死亡时在手的牌才降费，新抽的牌不追溯；实际节省取决于后来付款，不能把全手直接算到账G。'),
        example(choice, [module('damage', 'magic', 'enemy', choice, 3, choice='magic-choice'),
                         module('buff', 'magic', 'ally', choice, 3, stat='ATK', choice='magic-choice')],
                ['target_exists'], 'immediate', 'none', '相同choice_group的模块只能选择其一，不能伤害和增攻同时全额计值。'),
        example('Magic: Draw a card.', [module('draw', 'magic', 'self', 'Magic: Draw a card.')],
                [], 'immediate', 'none', '复制原文a card，不能把evidence改成1 card；count=1。满手会烧牌，不能已抽后再被沉默追回。'),
    ]
