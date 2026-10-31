"""Human-readable output; full machine-readable data remains in result.json."""

LABELS = {
    'experimental_only': '学习模型未达标，仅作实验诊断',
    'equivalent_in_supported_rules': '在已支持机制中等价',
    'conditional_improvement': '在全部声明条件下有改善证据',
    'conditional_regression': '在全部声明条件下有退步证据',
    'policy_or_opponent_sensitive': '结论依赖对手或打法',
    'insufficient_evidence': '证据不足，暂不排序',
}


def percentage(value): return f'{value * 100:+.2f}'


def markdown(result):
    if result['status'] != 'complete':
        lines = ['# 暂不能给出完整评估', '', '未实现、无效输入或未达标模型没有被当作可信评分。', '']
        for item in result.get('issues', []): lines.append(f"- {item['path']}: {item['message']}")
        for item in result.get('unsupported', []):
            lines.append(f"- {str(item['input'])}: " + '; '.join(i['message'] for i in item['issues']))
        return '\n'.join(lines) + '\n'
    lines = ['# 卡牌替换评估', '', f"参照：{result['reference']['name']}。每项按同种子、双方座次配对，未上手和未出场都保留。", '',
             '这些结果适用于输入牌组、声明对手和已实现规则；没有合成为真实环境总分或Gold价格。', '']
    if result.get('model_name'): lines += ['使用模型：'+result['model_name']+'。验证状态见本报告结尾及 result.json。','']
    if result.get('planner'):
        config=result['planner']
        lines += ['公开搜索：'+config['mode']+'，价值偏离门槛'+str(config['margin'])+'。未知抽牌与非终局回合边界不展开；价值针对基线续局，策略仍属实验。','']
    for card in result['comparisons']:
        lines += [f"## {card['card']}", '', LABELS[card['recommendation']], '',
                  '| 对手 | 我方策略 | 替换差，百分点 | 配对95%区间 | 未收到/收到未出/已出 |',
                  '|---|---|---:|---:|---:|']
        for cell in card['conditions']:
            diff = cell['difference']; lower, upper = diff['completion_range']
            point = percentage(diff['mean']) if diff['mean'] is not None else f'{percentage(lower)}～{percentage(upper)}（完成界）'
            counts = cell['opportunities']
            denom = '/'.join(str(counts.get(k, 0)) for k in ('not_received', 'received_unplayed', 'played'))
            lines.append(f"| {cell['opponent']} | {cell['policy']} | {point} | {percentage(diff['low'])}～{percentage(diff['high'])} | {denom} |")
        lines.append('')
    if result.get('unsupported'):
        lines += ['## 未评分的候选', '']
        for item in result['unsupported']: lines.append('- ' + str(item['input']) + ': ' + '; '.join(i['message'] for i in item['issues']))
        lines.append('')
    if result.get('synthetic_descriptors'):
        lines += ['含虚构语义描述：' + '、'.join(result['synthetic_descriptors']) + '；这些数值不代表真实卡面。', '']
    lines += [f"共{result['games']}个比较槽位，{result['unresolved']}个未决；未决保留0/1完成界，不记作半胜。", '',
              '跨全部条件的方向建议使用更严格的多重比较阈值；单行区间用于查看条件差异。', '',
              '规则边界：' + '；'.join(result['assumptions']) + '。', '',
              ('学习模型尚未通过独立验证，上述数值仅作实验诊断。' if result.get('evidence_level') == 'experimental_model'
               else '本次比较使用声明策略，不代表最优对弈；牌序区间不覆盖规则误差或策略不足。')]
    return '\n'.join(lines) + '\n'
