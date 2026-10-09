"""Reproducible numerical probes; no desired named-card strength labels."""
import hashlib
import json
from pathlib import Path

import combat_increment as combat
import context_value as values
import payment_frontier as payments
import score_cards as base

HERE=Path(__file__).resolve().parent


def main():
    cards=base.load_cards()
    reference,_=base.make_reference(cards)
    roles=('aggro','control','combo','midrange')
    body_marginals={role:[dict(from_attack=a,to_attack=a+1,health=7,
                               delta_model_gold=values.body(a+1,7,reference,role)-values.body(a,7,reference,role))
                          for a in range(2,11)] for role in roles}
    hand=[dict(cost=3,gross_model_gold=3.5),dict(cost=3,gross_model_gold=3.5)]
    frontier=payments.compare_discount(hand,[2,2],max_plays=2,cost_delta=-1)
    combat_probes={
        'two_small_targets':combat.premium(2,5,[dict(attack=1,health=1),dict(attack=1,health=1)],
                                           dict(haste=True),0,reference,'aggro',{'none':1}),
        'empty_board':combat.premium(2,5,[],dict(haste=True),0,reference,'aggro',{'none':1}),
        'magic_already_removed_targets':combat.premium(6,4,[dict(attack=3,health=0)],
                                                       dict(haste=True),5,reference,'aggro',{'none':1}),
    }
    folder=HERE/'annotation-runs'/'pool-v5-complete404'
    records=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(folder.glob('batch_*.json'))]
    cache=dict(requests=len(records),prompt_tokens=sum(r.get('usage',{}).get('prompt_tokens',0) for r in records),
               reported_cached_tokens=sum(r.get('cache_metrics',{}).get('cached_tokens') or 0 for r in records),
               unknown_cache_requests=sum(r.get('cache_metrics',{}).get('cached_tokens') is None for r in records),
               missing_raw_usage_requests=sum('raw_usage' not in r for r in records),
               distinct_prefixes=len({r['shared_prefix_sha256'] for r in records}))
    cache['reported_hit_fraction']=cache['reported_cached_tokens']/cache['prompt_tokens']
    status=json.loads((folder/'consistency.json').read_text(encoding='utf-8'))
    outcome=dict(date='2026-10-08',context_version=values.VERSION,combat_version=combat.VERSION,
                 parameters_are_design_assumptions=True,
                 source_sha256={f:hashlib.sha256((HERE/f).read_bytes()).hexdigest() for f in
                                ('score_cards.py','context_value.py','combat_increment.py','payment_frontier.py','knowledge_resolution.py')},
                 body_attack_marginals=body_marginals,payment_unlock_example=frontier,
                 combat_probes=combat_probes,cache=cache,
                 annotation_status={k:status[k] for k in ('all_batches_consistent','accepted_count','probe_checks','usage')},
                 limitations=['All prices, response weights and hand quotes are normative, not observed Gold-equivalent truth.',
                              'Not a card-strength ranking; incomplete effects and conditional payable masks cannot become a global rank.',
                              'Cache hits do not validate semantic correctness or establish Tencent billing prices.',
                              'Known-hand frontier is evaluated at a declared event; no future random draws are revealed to current actions.'])
    (HERE/'iteration-diagnostics-2026-10-08.json').write_text(json.dumps(outcome,ensure_ascii=False,indent=2),encoding='utf-8')
    rows='\n'.join(f"| {r} | {body_marginals[r][4]['delta_model_gold']:.3f} | {body_marginals[r][7]['delta_model_gold']:.3f} |" for r in roles)
    report=f'''# 启发式Value迭代记录：2026-10-08

本轮完成可复用缓存前缀、独立语义审查、联合战斗窗口与支付解锁模块。数值由主智能体定义，DeepSeek只提取语义。以下是可复算的局部估值诊断，尚不是完整卡牌强度榜。

## 固定知识对话与实际缓存

每次请求共享system和9组user/assistant示例，共19条固定消息；最后一条才放本批卡面与依赖。固定部分含Skill、完整规则边界、机制词典及统一字段，消息内容和顺序逐字复用，并校验prefix hash。

本轮16请求共{cache['prompt_tokens']:,}输入token，接口报告{cache['reported_cached_tokens']:,}缓存token，约{cache['reported_hit_fraction']:.1%}；prefix hash只有{cache['distinct_prefixes']}种。前8批未保存原始usage，只保存了解析的缓存字段，历史限制保留。不能据此推断腾讯代理的收费折扣。

4–8G普通怪物全池404张，计划51批，目前完成16批。独立复核实际读取130张不同卡、抽查32张非探针；当前119张通过结构合并，仍非语义批准。不能把404的计划数字当完成覆盖。两探针的数值结构一致；原始Vulkin的两条ALL疑问已由精确匹配K007解决并保留日志。复杂卡仍存在触发、受益对象、公式、同分支多动作和漏项问题，扩批暂停，先改规范和局部复核，无需全部重抽。

## 数值模型的新进展

**攻击边际来自共同身材函数。** 以下均为HP=7，只改同一合成主体的ATK；不以具名强牌排名拟合：

| 对手任务 | 6→7 ATK | 9→10 ATK |
|---|---:|---:|
{rows}

单位为启发式G。过量攻击贬值，但遇到新的击杀线时局部边际可以上升，不强制每一级都下降。Aaron仅作5G尺度锚，缺少足够无效果中费卡，因此这些不是实战测得的金币换算率。

**Haste/Dodge/Armor/Taunt联合估计。** 现在是“本回合可选一次Haste怪物攻击→一个公开定义的对手回应→下一己方回合一次普通攻击”。双方允许同样的延后选择，Haste当回合不能打脸；目标受嘲讽限制，闪避按伤害实例消耗。比较最终身体、双方HP和对手剩余资源，额外攻击／击杀不再另加奖。对手花费的效用明确不是我方到账金币。Magic改变的场面在两路完全相同。

2/5主体面对两只1/1的无回应例中，Haste前后最多两次攻击，普通最多一次；空场对照的纯Haste增值为0。Magic已清掉的怪物也不会在后续窗口复活。终局停止行动且资源报价留空；未支持免疫、Dust回调、成长清除等组合仍保持partial。

**降费包含直接节省和解锁。** 已知两张3G牌，各总收益先验3.5G；未来两轮收入各2G，无初始余额，每轮最多两次行动。旧费用只能用一张，净0.5G；各降1G后能用两张，净3G。差值2.5G严格拆成旧计划少付1G＋额外行动净1.5G。不能另外再加两张牌的完整身材。未使用的卡不算省钱，未花的金币不算损失。

手牌报价与行动上限必须显式给出，不从卡名猜测；模型未获得这类输入时只计实际付款节省。当前context模型在404张池中可执行16张完整文字的受限模块，其他保留partial；这不意味着16张已完成全部实战质量评估，也不能直接比较不同可支付面板的条件均值。

## 下一轮应扩展的结构

优先落地同分支多动作、触发类型、玩家／主体／生成输出的绑定、有限数量公式与覆盖检查。现有分支枚举器已支持choice_branch捆绑，但DeepSeek V5 schema尚未升级，旧文件不会被静默改写。用本轮保存的失败样本回归，再对受影响条目集中修订；不靠重复请求直到一致。

同时把局面报价、可支付性和有限等待成本接起来，用同一构筑参数评估卡牌；继续保持机制级参数，避免为四张讨论卡或人工名单单独拟合。

可复算数据：[iteration-diagnostics-2026-10-08.json](iteration-diagnostics-2026-10-08.json)。独立审查：[v5-pool-audit.md](v5-pool-audit.md)、[combat-review.md](combat-review.md)、[combat-review-v02.md](combat-review-v02.md)。新版接入复核未发现默认24情境的阻断问题，另发现两个外部泛化边界；已禁止0ATK敌人主动接触，并让Magic使用同一伤害实例处理Armor/Dodge。仍不将局部审查当全部机制批准。
'''
    (HERE/'迭代记录-2026-10-08.md').write_text(report,encoding='utf-8')
    print(json.dumps({'cache':cache,'report':str(HERE/'迭代记录-2026-10-08.md')},ensure_ascii=False))


if __name__=='__main__': main()
