"""Render actual frozen evidence; never train, replay, or choose a model."""
from pathlib import Path
from collections import Counter
import json,re

F=Path(__file__).resolve().parent
def read(n):return json.loads((F/n).read_text())
def pc(v):return f'{100*v:.2f}'
def point(v):
    a,b=v['completion_range'];return pc(a) if a==b else pc(a)+'～'+pc(b)
def ci(v):return '['+pc(v['low'])+', '+pc(v['high'])+']'


def render():
    d=read('design.json');fit=read('fit.json');dev=read('development.json');final=read('final.json');val=read('final-value.json');ph=read('value-profiles.json');fail=Counter(r['policy'] for r in final['failures'])
    lines=['# V9：实体关系、机制绑定与全程价值监督','',
        '**程序版本0.4.0；通用可靠卡牌评估目标尚未完成。** 训练、策略泛化、价值预测和安装交付分开核对；不把程序可安装或训练上涨称为全池评分成功。','',
        '## 资料与实际方法','',
        '- Deep Sets（Zaheer等，NeurIPS2017）：https://papers.nips.cc/paper/2017/hash/f22e4747da1aa27e363d86d40ff442fe-Abstract.html ，采用实体共享非线性变换后按区域池化。',
        '- Relational Deep Reinforcement Learning（Zambaldi等）：https://arxiv.org/abs/1806.01830 ，参考实体/关系归纳偏置；未复现其自注意力RL或直接套用论文任务成绩。',
        '- On the Limitations of Representing Functions on Sets（Wagstaff等，ICML2019）：https://proceedings.mlr.press/v97/wagstaff19a.html ，核对固定潜维集合表示的限制，不宣称16维嵌入是充分状态。','',
        'V7的确定赢/输边界状态在旧聚合编码下完全相同。V8修复实体输入、机制trigger/op/scope/amount联合绑定后，又实际发现3821个训练状态只在1..12回合且无空牌库；训练好的模型对原确定输反例仍高估约84%。V8权重、开发和失败全部保留，未开始原预定223/225最终；不是按最终结果改选。','',
        'V9复用已有匹配V5 actor的完整训练/开发轨迹，不重跑旧游戏。实体主臂9329参数、聚合MLP容量控制9349参数；相同数据、更新预算、正则、开发选择及冻结actor。旧线性critic是额外控制，与它比较同时改变容量和监督覆盖，不能把差异只归因于实体表示。手牌无序，公开场位保留；名字、ID、私手、牌序和随机种子不是值输入。','',
        '## 训练与冻结','',
        f"训练共{fit['training']['states']}状态，768个已执行原开局的复用标签，其中11213状态来自384个已有V5完整轨迹；343个过12回合、76个空己方牌库，仍不等于充分后期覆盖。未知终局、抽牌后继、非终局end分别计数，不作零标签。源文件与输入缓存都保存。",'',
        '| 臂 | 参数 | 诊断NLL选择epoch | 选择时诊断Brier |','|---|---:|---:|---:|']
    for name,r in fit['arms'].items():
        row=next(x for x in r['curve'] if x['epoch']==r['selected_epoch']);lines.append(f"| {name} | {r['parameters']} | {r['selected_epoch']} | {row['development']['brier']:.6f} |")
    lines += ['',f"新217开发三门槛各80槽位，均终局；按预定规则选主臂门槛{dev['selected_margin']}，胜率67.50%。之后固定全部模型/配置。复用诊断只选epoch，未用于宣称新最终成功。V8与V9初始化不同，阶段间变化不单独归因于覆盖增加。",'',
        '## 新策略最终','',f"2350000..2350031，32牌序×两座次×八背景×七政策，共3584槽位，{len(final['failures'])}未决，qualified={str(final['qualified']).lower()}。源代码、权重与开发先提交再执行；不在最终调参、重选其他臂或重跑失败。",'',
        '| 背景 | 实体主臂胜率完成界% | 等容量聚合% | 线性搜索% | V5% | 主臂－聚合95%区间，百分点 | 主臂－V5区间 |','|---|---:|---:|---:|---:|---:|---:|']
    for g in final['groups']:
        ps={r['policy']:r for r in g['policies']}
        lines.append(f"| {g['group']} | {point(ps['entity']['win'])} | {point(ps['aggregate']['win'])} | {point(ps['linear']['win'])} | {point(ps['v5']['win'])} | {ci(ps['aggregate']['primary_gain'])} | {ci(ps['v5']['primary_gain'])} |")
    lines += ['', 'race/board/guard、完整配对区间和八背景敏感性见final.json。没有平均成真实环境总分；固定planner对手并非学习后的最优反制。严格整体门槛要求所有背景正增益，未通过不等于每项均无局部改善；局部判断仍须看预定区间。','',
        '所有政策共同决策上限.25秒；三个搜索臂48节点/深度3/宽度4/内部.12秒，共用actor排序。实际CPU和信息处理量不同，不能说相同节点或毫秒工作量。proof-first-2首先执行已有确定斩杀；原版public-own-turn-1完整保留用于V7，数据不重标。','',
        '| 政策 | 终局成功记录内的最高条件p95秒 | 此类记录最大秒 | 预算未决 |','|---|---:|---:|---:|']
    for n in d['final_policies']:
        ts=[g['timings'][n] for g in final['groups']];lines.append(f"| {n} | {max(x['p95'] or 0 for x in ts):.6f} | {max(x['maximum'] or 0 for x in ts):.6f} | {fail[n]} |")
    maximum=max((float(m.group(1)) for r in final['failures'] if (m:=re.search(r'seconds=([0-9.]+)',r['error']))),default=0)
    lines += ['',f"被拒绝决策不在上表成功记录内，错误文本最大秒数{maximum:.6f}。旧run包装对失败局没有完整逐步计时，缺失保留，不伪造。未知胜负按0/1完成界，未填半胜或训练标签。",'',
        '## 独立价值最终','',
        f"2330000段96新世界，配对续局的可评分原局面{val['counts']['roots']}、动作后{val['counts']['after']}；未知原因见final-value.json。目标始终是V5续局，不是搜索新策略V。没有用这批数据选择epoch或门槛。",'',
        '| 局面 | 实体Brier | 聚合Brier | 线性Brier | 实体对聚合误差降低95%区间 | 对线性 |','|---|---:|---:|---:|---:|---:|']
    for k,m in val['metrics'].items():
        bs=m['brier'];e=m['entity_error_reduction'];lines.append(f"| {k} | {bs['entity']['mean']:.6f} | {bs['aggregate']['mean']:.6f} | {bs['linear']['mean']:.6f} | [{e['aggregate']['low']:.6f}, {e['aggregate']['high']:.6f}] | [{e['linear']['low']:.6f}, {e['linear']['high']:.6f}] |")
    lines += ['', '额外分阶段诊断事先写入VALUE_ANALYSIS.md，直接复用新世界中的V5行为完整轨迹；race轨迹不重标成V5，未决终局排除。子集相关，不能当新独立实验。','',
        '| V5完整轨迹阶段 | 观察 | 牌序簇 | 实体Brier | 聚合Brier | 线性Brier |','|---|---:|---:|---:|---:|---:|']
    for k,m in ph['profiles'].items():
        bs=m['brier'];values=' | '.join(f"{bs[n]['mean']:.6f}" for n in ('entity','aggregate','linear')) if bs else '缺失 | 缺失 | 缺失'
        lines.append(f"| {k} | {m['states']} | {m['opening_clusters']} | {values} |")
    lines += ['', '分阶段CI见value-profiles.json，样本少/缺失不能解释为零误差。','',
        '## 改变的判断与未决问题','',
        '表达修复有可核对的内容：当前生命与嘲讽/准备的关系未在编码前合并，机制触发和目标也不再分别汇总；但既有反例的训练后概率仍失败，见representation-check.json，不能说已学会该战术。固定actor的平均MC预测下降也不自动证明更好行动排序，仍以完整终局对局为准。','',
        '数据诊断排除了“已有几千个动作后标签就覆盖整局”的判断；复用完整轨迹带来后期/空库标签，却仍稀少。下一关键问题是对行动差、关键多步后果与对手反制直接学习，并检验信息集历史/信念的作用；不要继续只加集合维数、卡牌数量或训练胜率。需要新训练/开发和最终，233/235及已读旧最终全部退休。','',
        '## 可运行交付与限制','',
        '程序0.4.0包含proof/value公开搜索、实体价值推理、命名训练模型、完整输入预检、共享策略的实体替换和机器/人读结果。entity-v9检查点本身保留V5 actor，只有显式加planner才改变行动；默认参考策略和未达标门槛没有升级。所有公开搜索仍需实验模式。wheel、完整源码/证据ZIP及源码外安装/清单实测收据随Git保存，运行入口见START_HERE.md。','',
        '规则仍仅20张完整实卡及支持语法。未知完整效果拒绝评分，未知抽牌分支停止，服务器事件、沉默裁定、神器、换牌、种族、死亡生成链仍有限制。没有充分信念、策略迭代下的自一致新V或针对主臂训练的最优反制。单一训练初始化的区间不覆盖训练方差，不能将产物称为可靠全池评估已经完成。','']
    (F/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':render()
