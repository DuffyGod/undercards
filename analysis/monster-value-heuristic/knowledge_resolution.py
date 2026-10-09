"""Resolve narrowly recognized questions already answered in frozen premises.

Preserve raw replies. This is neither a broad semantic approval nor model votes.
"""
import copy
import hashlib

ALL_SCOPE_QUESTIONS = {
    'ALL target selection among enemy monsters/player is not further specified by the card text.',
    'target_metadata=ALL，但卡面未明确伤害目标为怪物、玩家或两者',
    'target_metadata=ALL，但Magic不能选择触发本卡自身；可选怪物或玩家的具体范围未在卡面明确',
    'target_metadata=ALL，但卡面未明确伤害目标为怪物还是玩家',
    'target_metadata=ALL表示可指定的目标类别，但卡面未写明目标类别，无法确定是敌怪、玩家还是其他合法目标',
    'target_metadata ALL的具体可选目标类别未在卡面明确',
    'target_metadata=ALL表示可指定的目标类别，但卡面未写明目标范围；按规则Magic不能选择触发它的怪物自身，故target填other并说明。',
    'target_metadata=ALL的具体可选目标类别未在卡面明确，按other处理',
}


def recognized_all_scope_question(question):
    return isinstance(question, str) and question.strip() in ALL_SCOPE_QUESTIONS


def resolve(row, card, system):
    out = copy.deepcopy(row)
    records, retained = [], []
    for question in row.get('unresolved', []):
        answered = None
        if 'K007:' in system and card.get('target') == 'ALL' and recognized_all_scope_question(question):
            answered = 'K007: explicit project ALL single-target scope premise'
        if answered:
            premise = next(line for line in system.splitlines() if line.startswith('K007:'))
            records.append({'card_id': row['card_id'], 'question': question, 'resolved_by': answered,
                            'premise_sha256': hashlib.sha256(premise.encode('utf-8')).hexdigest()})
        else:
            retained.append(question)
    out['unresolved'] = retained
    return out, records
