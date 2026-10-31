"""Render stored V7 evidence without training, replay or model selection."""
from collections import Counter
from pathlib import Path
import gzip,json,re

FOLDER=Path(__file__).resolve().parent


def read(name):return json.loads((FOLDER/name).read_text())
def pct(x):return f'{100*x:.2f}'
def bounds(item):
    lo,hi=item['completion_range']
    return pct(lo) if lo==hi else pct(lo)+'～'+pct(hi)
def ci(item):return '['+pct(item['low'])+', '+pct(item['high'])+']'


def render():
    d=read('design.json');fit=read('fit.json');dev=read('development.json');final=read('final.json');value=read('final-value.json');collection=read('diagnostic-collection.json')
    failures=Counter(r['policy'] for r in final['failures']);timings={};events=Counter();all_slots=0
    with gzip.open(FOLDER/'final-games.jsonl.gz','rt') as stream:
        for line in stream:
            row=json.loads(line);all_slots+=1
            if row['policy']=='primary':events.update(row['planner'])
    lines=['# V7：公开多步搜索与动作后价值', '',
        '**通用卡牌评估目标尚未完成。** 本轮恢复并核验原版V7完整逐局文件；原中断记录保留为历史。0.4.0安装包另行验收，V7数据不等于修正版搜索验证。', '',
        '## 关键问题与实际改变', '',
        'V6增加合法知识输入却没有证明策略提升。本轮检验：复用确定规则的同回合前瞻、以及直接针对动作后状态的终局监督，能否补上单步动作差缺少的组合决策。共享actor保持V5；对照原局面重拟合与原局面＋确定动作后局面的同一74维critic。搜索由actor排序、critic评价，分开proof-only、旧critic搜索及新critic搜索；模型不接收隐藏世界。', '',
        '遇到未知抽牌时整条后继分支停止；公开空牌库疲劳可精确计算。非终局回合结束不冒充可继续行动的同回合状态。确定斩杀可跨部署、攻击、法术和当前结束触发，执行前逐次核对公开观察。没有机会模型、充分信念或对手回合搜索。', '',
        '## 可核对资料', '',
        '- ICLR2022 Stochastic MuZero作者解释：https://www.julian.ac/blog/2022/05/15/planning-in-stochastic-environments-with-a-learned-model/ 。采用确定行动/随机事件分解的思想；不是该算法复现，论文OpenReview入口本轮被浏览器校验阻断。',
        '- Tesauro，CACM1995 TD-Gammon授权转载：https://www.bkgm.com/articles/tesauro/tdl.html 。参考终局价值与前瞻结合，以及绝对误差和相对行动排序的区别；本轮不是TD(lambda)。',
        '- 冻结后核对Double Q-learning和SPIBB的原始会议页，链接与适用边界见[METHOD.md](METHOD.md)。本轮没有双估计器或置信集，不把固定门槛称为安全提升保证。', '',
        '## 训练与开发', '',
        f"复用384个V5原开局的V6 current续局，{fit['counts']['root_states']}个原观察、{fit['counts']['after_states']}个确定动作后观察；{fit['counts'].get('unknown_draw',0)}个未知抽牌边界不产生后继标签。按原开局等权，l2=.01，两个优化均收敛。actor指纹相同；没有新卡ID参数、训练胜率成功判据或旧实验重放。", '',
        'V6曾因混合目标中的旧V4未知结果排除一整组；V7仅需要已完整保存的current-V5目标，所以可使用768个原观察。旧V4失败仍原样保留，未补算或填值。', '',
        f"新开发1950000段只选择预定主臂门槛；按完成界下限、平手选更大门槛，最终冻结{dev['selected_margin']}。各候选如下：", '',
        '| 门槛 | 槽位 | 胜率完成界下限% | 未决 |', '|---|---:|---:|---:|']
    for r in dev['results']:lines.append(f"| {r['margin']} | {r['games']} | {pct(r['mean_win_lower'])} | {r['unfinished']} |")
    lines += ['', '这不是按最终结果重选；root控制仅作价值对照，未参与最终策略挑选。单一训练actor的聚类区间不覆盖训练方差。', '',
        '## 新最终策略验证', '',
        f"2050000..2050031的32个新牌序、两座位、八条件、七政策共{all_slots}槽位，{len(final['failures'])}未决。固定策略验收qualified={str(final['qualified']).lower()}。没有在这些最终局面调参或重选其他策略。", '',
        '| 条件 | 主臂胜率完成界% | proof% | 旧价值搜索% | V5% | 主臂－V5配对95%区间，百分点 | 八背景敏感性区间 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    names=dict(pressure='压力',defense='防守',refill='补牌',new_parameters='未训练数值/Charge',new_composition='未训练Taunt＋开始成长',new_mixed_decks='新混合牌组',known_delayed_sweep='已知延迟群伤回归',unseen_learned_opponent='未训练V5对手')
    for g in final['groups']:
        ps={c['policy']:c for c in g['policies']}
        lines.append(f"| {names[g['group']]} | {bounds(ps['primary']['win'])} | {bounds(ps['proof']['win'])} | {bounds(ps['old_value']['win'])} | {bounds(ps['v5']['win'])} | {ci(ps['v5']['primary_gain'])} | {ci(ps['v5']['family_gain'])} |")
    lines += ['', '逐条件race/board/guard及全部配对区间见final.json；不平均成真实环境总分。八背景敏感性对每个比较按.05/8计算，不声称覆盖额外的模型挑选。新混合牌组和学习型对手仍是固定挑战，不是最优反制或Nash验证。熟悉的延迟群伤没有改名叫未见对手。', '',
        '所有政策共享.25秒决策上限；新搜索上限48节点、深度3、宽度4、内部.18秒。实际工作量明显高于V5/参考，不能说耗费相同节点或CPU。节点排序由固定actor决定，critic对照共用搜索配置；墙钟截断仍可能改变展开数。', '',
        '| 政策 | 完整局内记录决策p95秒的最大条件值 | 完整局内记录最大秒 | 预算未决槽位 |', '|---|---:|---:|---:|']
    for p in d['final_policies']:
        ts=[g['timings'][p] for g in final['groups']]
        lines.append(f"| {p} | {max(t['p95'] or 0 for t in ts):.6f} | {max(t['maximum'] or 0 for t in ts):.6f} | {failures[p]} |")
    maximum_failure=max((float(m.group(1)) for r in final['failures'] if (m:=re.search(r'seconds=([0-9.]+)',r['error']))),default=0)
    lines += ['', f"上表最大值不包含被拒绝决策；失败错误文本中最大用时{maximum_failure:.6f}秒。失败局的旧run包装仅保存错误、没有完整逐步计时，缺失继续保留，未伪造。未决按0/1完成界，既未填半胜也未作为学习标签。", '',
        f"主臂记录public_proof={events['public_proof']}，committed_proof={events['committed_proof']}，基线续局价值改动={events['base_continuation_value']}，未知抽牌边界={events['unknown_draw_boundaries']}，proof_mismatch={events['proof_mismatch']}。证明数包含原攻击斩杀也能找到的路径，不等同于新增胜局数。", '',
        '## 独立最终价值诊断', '',
        f"2030000段{collection['episodes']}新开局、{collection['forks']}个fork、{collection['branches']}条V5终局续局，{collection['unresolved_branches']}未知终局；逐决策原观察/合法行动/实际选择及完整输入均保存于diagnostic-rollins和diagnostic-forks。后继未知抽牌{value['counts'].get('unknown_draw',0)}、结束边界{value['counts'].get('end_boundary',0)}均单列。只评价已预先拟合的三个critic，不在这批数据选模型。", '',
        '| 状态 | 原V5 Brier | 原局面重拟合 | 动作后主臂 | 主臂相对原V5误差降低95%区间 | 相对原局面重拟合 |', '|---|---:|---:|---:|---:|---:|']
    for kind,title in [('root','原局面'),('after','动作后局面')]:
        metric=value['metrics'][kind];bs=metric['brier'];gain=metric['afterstate_error_reduction']
        lines.append(f"| {title} | {bs['old']['mean']:.6f} | {bs['root']['mean']:.6f} | {bs['afterstate']['mean']:.6f} | [{gain['old']['low']:.6f}, {gain['old']['high']:.6f}] | [{gain['root']['low']:.6f}, {gain['root']['high']:.6f}] |")
    lines += ['', 'Brier按原开局内等权再按开局聚类。这里评价V5继续行动的价值，不能叫搜索策略自身V，也不能把预测改善当作策略验收。旧诊断值在fit.json，未当新最终证据。', '',
        '## 改变了什么判断', '',
        '除统计试验外，value-alias-witness.json保存一个直接执行的表示反例：双方隐藏区域为空，只把敌方嘲讽和普通单位的当前HP1/9互换，其余公开/已知机制相同。A可清嘲讽后斩杀；B总攻击不足清嘲讽，同一race回应确定击杀我方。真实冻结续局标签1/0，但V5、root、动作后及V6记忆critic输入均相同、预测也相同。任意使用该编码的预测器在此等权对上Brier至少.25。', '',
        '这证明当前价值聚合表示丢失了与决策有关的单位关系，增加动作后标签本身无法消除；不是证明本轮所有失败都由此造成。它是构造边界局面，非自然开局频率/可达分布验证，不计新增独立开局，也未用于调参或重选。已实现的公开战术搜索可辨别这类可在预算内证明的情况，但不能替代一般状态价值表示。', '',
        '## 交付、失败与下一关键问题', '',
        '开发源码支持--planner proof/value、独立配置指纹、base_model溯源、afterstate-v7命名检查点和可编辑请求。所有公开搜索仍需实验模式，不能继承基线模型质量证明。无搜索时V7 actor与V5相同；默认可靠性未提升。未知实卡整体效果依旧拒绝评分，完整实卡规则仍仅20张及语义组合，神器/换牌/种族/死亡生成链和服务器事件裁定仍不完整。', '',
        '先前适配器导出名和单卡lookup预检失败见preflight-failures.json；开发/最终超时不删除。安装及源码外完整包复核尚待恢复后的0.4.0发行流程，不能凭源码检查宣称已完成。读取planner_audit可不重放、不重训核对必要输入、冻结权重、完整分母和表示反例。', '',
        '下一关键问题应围绕已经证实的表示损失：保留单个单位/卡牌的属性与机制关系，在新训练/开发中比较实体集合编码与当前聚合critic；使用相同固定actor、同一批原局面/干预目标及动作排序误差控制，检验改进是否来自信息而非增大容量。再检验分离选择与评价/不确定性回退，以及针对该策略学习回应的对手。当前结果不能证明哪个后续算法一定更好。', '',
        '预算稳定性也须先解决：重复构造、已经可证明的旧攻击斩杀仍继续搜索等是待测成本来源，不能把当前失败悄悄补跑成胜负。新的搜索实现必须更换方法版本并用新开发/最终验证。2030000..2030095与2050000..2050031退休，旧最终段继续退休。', '']
    (FOLDER/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':render()
