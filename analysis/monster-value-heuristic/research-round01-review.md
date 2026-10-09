# Round01 原始研究输出独立复核

2026-10-08；仅复核冻结的 `research-runs/round01`。未调用 API、重试、修改队列、模型或原始回复。本报告是人工审计记录，不授予 semantic approval，也不生成 Gold 报价。

## 能改变下一步的结论

1. **12 个原始回复全部 `finish_reason=stop`，全部能解析为 JSON。没有证据表明本轮发生网络失败或输出截断。** `inventory_000` 的 `failed` 实际为 helper 的 `missing_keys`：有效 JSON 缺 `kind/task_id`，不是 transport。summary 的空错误列表不能替代该任务文件的 `error`。
2. **整体通过 3/12，不等于其余内容全丢。** 用冻结 `semantic_v6.validate`、完整冻结 snapshot 逐卡复验，64 张新卡中 48 条结构通过，其中 32 条来自整体未通过的 inventory。它们可作逐条审阅材料，不能自动作为可信执行输入。
3. **结构通过仍出现足以改变质量评价的语义错误。** 明确例子是 #534 把“受伤”编码成没有 HP buff，#135 把普通 kill 编码成 exact kill，#103 把“降攻后 ATK=0”编码成仅存在目标，#678 的金额来源指向生成物而非触发法术。应先修条件/来源映射和准入门，再扩大自动评分覆盖；不能靠增加重抽样消除这些系统性错误。
4. 四个 review 请求共 14 条提案中，**未证实新的重复计价或 Gold 单调性错误**。已有爆牌惩罚、零费用下界、ALL 宽单目标和已存在的 choice group 多次被误报。实际复现的有价值边界是条件 Haste 遇减伤会整窗拒绝，并连带阻断其他已知合法目标路线。

## 执行与结构失败分类

总 usage `641,553 tokens`，直接加总 12 个原始 `raw_usage.total_tokens`；不据此推断费用。所有任务仍有 `semantic_review_required=true`、`semantic_approval=false`，不能发布自动语义审核通过的结果。

| 请求 | summary 状态 | 核实的失败种类 | 新卡逐条结构通过 |
|---|---|---|---:|
| inventory_000 | failed | JSON 外壳缺 kind/task_id；内部 #883/#805 使用 unknown 却标 parsed | 6/8 |
| inventory_001 | structure_validation_failed | #759 引用未来/自身 module_id | 7/8 |
| inventory_002 | structure_validation_failed | #790 未知公式/机制仍标 parsed | 7/8 |
| inventory_003 | structure_validation_failed | #781/#925/#245 非法枚举；#171 绑定非输出模块；#171/#921 未知仍 parsed | 3/8 |
| inventory_004 | completed | 整体结构通过；不代表语义正确 | 8/8 |
| inventory_005 | structure_validation_failed | #301/#248 数值表达不完整；#248 来源非事件输出；#542/#975 前向/自身引用 | 4/8 |
| inventory_006 | completed | 整体结构通过；不代表语义正确 | 8/8 |
| inventory_007 | structure_validation_failed | #993 数量表达/事件输出绑定不合法；#495 未知仍 parsed；#500 state_change 缺明确 key 与 0/1 | 5/8 |
| counterexample_000 | completed | 3 个提案结构通过，未证实新模型错误 | — |
| counterexample_001 | structure_validation_failed | 一条 card:20 的 ALL 引用不在卡面 effect_readable 中，其他片段未因此消失 | — |
| model_review_000 | structure_validation_failed | 两段代码 source_id 错指 score_cards.py，实际在 context_value.py | — |
| model_review_001 | structure_validation_failed | payment_frontier 文档引用拼接跨行，非精确连续子串 | — |

逐卡复验使用完整 snapshot 供引用卡校验；只给当前 10 张卡的字典会虚假产生大量 invalid referenced card，本报告没有把这些误报算入失败。原始任务 hash 校验均通过。

## 四组提案逐项判断

| 请求/提案 id | 独立结论 | 可保留内容 |
|---|---|---|
| counterexample_000 / fixed_state_weights_under_override | 给出的 t3 Gold=20 在 `make_panel` 被累计基础金币检查拒绝，根本到不了声称的权重观察。改成合法 Gold=6、hand=6 后，仍保留 deployed 的共享先验权重；这是 override 干预原状态的行为，不是权重重复。状态标签与修改后资源可能不一致，属于审计解释问题 | 保留合法 override 的标签/先验说明；不要据非法反例重算每卡权重 |
| 同 / discount_monotonicity_floor | `paid_cost_discount(0,-1,True)=0`、`(1,0,True)=1` 已复现，符合支付 floor=0。零费继续减费没有现金收益，不违反弱单调性 | 零费边界回归用例 |
| 同 / waiting_negative_capacity | hand=7、等两回合、每回合自然抽 1、其他出牌 0，已复现 additional_natural_burns=1。程序本来就在计算等待的额外容量损失 | 正向回归，不是遗漏惩罚 |
| counterexample_001 / vulkin_all_target_wide_entity | 宽单目标包括友军、自己玩家、对手玩家，符合给定 ALL 前提；不是只能打敌方。`card:20` 的 `ALL` 在 metadata，不能冒充 effect_readable 连续子串 | 目标集合检查；需单独支持 metadata 证据路径 |
| 同 / tsunderplane_aoe_plus_face_split | 已复现 1 个候选、2 条伤害实例：两只 1 HP 敌怪各变 0 HP，对手 30→27，没有把整套 AoE 按敌怪重复 | 可保留为 AoE+face 正向回归 |
| 同 / broken_car_conditional_haste_zero_damage | Armor/Dodge 下 received≠nominal 导致显式拒绝，确为覆盖边界；程序没有错误授予 Haste | 保留未知裁定与局部拒绝测试 |
| model_review_000 / vulkin_wide_entity_self_target | 将 owner 玩家误作触发怪物本身。K007 禁的是本卡怪物自身，不是己方玩家；其引用 Gaster Blaster 的“怪物或自己”也不支持该结论 | 只保留 player_self / monster_this 区别作为反误报测试 |
| 同 / tsunderplane_face_damage_scope | “若调用方错误合并则重计”是未经观察的假设；当前 `_magic_candidates` 的两实例行为正确 | 与上一组合并保留一个回归，不当作新缺陷 |
| 同 / hotdog_choice_branch_guard | 引用错文件；真实 `context_value.parse` 返回两模块均含 `choice_group='magic-choice'`，`enumerate_choice_branches` 返回各选一的两支，已复现。声称没有 choice group 是假阳性 | 保留互斥测试，拒绝据此新增重复模块 |
| 同 / broken_car_other_monster_count_and_haste_gate | parser 引用也错文件；条件 Haste 减伤限制与上一组重复。其 wide_entity 假设不符合实际 monster 模板 | 合并保留一个边界，见下节混合目标反例 |
| model_review_001 / cost_distribution_not_quality | 忠实复述已有资源工具边界，不是新模型缺陷 | 可进入 handoff 的 scope 说明 |
| 同 / joint_gold_hand_conditional | 忠实复述联合资源频率不是实战/身份频率、不会推断 board/Soul | 可进入 handoff；“两个维度”不等于统计独立 |
| 同 / candidate_in_hand_selection_bias | 正确区分收入/抽牌后、决策前，以及 used_before_decision 已实现价值未估计而非零 | 可保留采样时点说明，不是已证实选择偏差修复 |
| 同 / future_payment_frontier_boundary | 内容符合已知手牌资源前沿边界，但 quote 把原文换行连接为空格，结构拒绝合理 | 可人工重定位来源后写入说明，保留原回复不改 |

### 已执行的条件 Haste 混合路线反例

直接调用冻结 `coupled_magic._magic_candidates`；输入角色本体 3/7、一个友怪 2/2、一个敌怪 1/5 且 Armor=true，双方玩家 30 HP、delta=0、空 log，damage_specs=`[{amount:2,target:'monster'}]`、conditional_limit=3。

有 Armor 时抛 `Conditional Haste with mitigated/ambiguous received damage is not verified`；删去敌方 Armor 后有两条合法路线。**即使友方目标没有减伤、其分支已知，另一目标的未知伤害判定仍使整个枚举返回失败。** 这不是证明服务器应授予哪一种 Haste，而是证明“不确定分支→整窗拒绝”的范围比单分支更大。

低成本改进提案：将已知路线和未知路线分别记录，返回 partial 及可验证的路线下界/诊断；不能静默丢弃未知路线后假称得到全局最佳路线，也不能把 partial 下界发布成完整分数。本报告没有修改此行为。

## Inventory 可挽救片段与真实风险

64 条均保留了原始卡面文本，可供人工审阅。48 条结构通过不是 48 条可信可执行注解。以下错误既存在于外壳失败批，也存在于整体通过批。

| 卡 ID | 实际问题 | 低成本下一步 |
|---|---|---|
| 534 | `while damaged` 被写成 `has_hp_buff=false`；满血但没有 buff 会错误满足，带 buff 后仍受伤又会错误不满足 | 无有限受伤谓词则 unknown/partial；不能拿近似合法枚举替代 |
| 815 | “本回合死亡的其他非 TOKEN 怪物”被写成当前场面 `other_monster_count`；notes 正确而 typed 字段错误 | 死亡事件过滤与当前场面数量分开；没有表达式就 partial |
| 54 | 新副本 ATK/HP -1 被写成 `stat_set=-1`，把增量改成设定值 | 保留 Dust→输出绑定；增减与赋值必须分别核对 |
| 125 | “everything other than this”映射到 all_monsters，遗漏双方玩家和排除本卡；自己承认有限 recipient 不能准确表达，仍 parsed | 保留 turn_end/伤害 1；其余 partial，不用 closest enum 冒充完整 |
| 135 | 普通 kill 后 heal 使用 exact_kill guard，而非杀死即可；notes 另有当前费用/未说明费用的自相矛盾 | 普通 kill 事件与 Bullseye/精准零血分开；保留 Magic 与 turn_start 两触发 |
| 25 | “After this kills”缩成 attack_killed_monster，可能漏其自身 Magic 击杀；单次 2 伤害的 ALL 范围也未完整编码 | 不擅自缩成攻击事件；宽单目标需单独审核 |
| 265 | “法术伤害 +2”的修正器写为 passive damage 实例，notes 才解释不是定时伤害 | 不直接执行该 damage；修正器未建模则 partial；可保留 Add 2 Spade 及输出降费绑定 |
| 678 | `source_cost` 的表达式引用 add 输出 a（Spincake），notes 却说来源是 Shock 触发法术；这会按生成卡费用缩放，而非触发法术费用 | 触发事件来源与生成 recipient_ref 分开绑定；floor(cost/2) 仅在来源正确后可用 |
| 103 | kill 的 guard 是 has_target，而真正条件为减攻后 ATK=0；文本 condition 保留了 0 ATK，不能补救错误执行信号 | 增加有限目标 stat 比较或 partial；应有 ATK=2 与 ATK=3 成对反例 |
| 221 | return 只 typed actor_survives，缺“已攻击”联合条件 | 生存与攻击历史各自记录；不能仅靠 condition 自然语言执行 |
| 59 | Dodge (3) 的 numeric amount=null、count=1，计数只留在 evidence 中 | 定量关键词提取后再执行，当前保留作为人工片段 |

更可靠的可保留片段包括 #169 Magic Summon Bun、#426 Dust Summon Rabbick、#108 Dust Summon Pebble、#763 Magic 与 Dust 分别 Add Shovel、#589 Shock Add Draft、#588 Shock heal player 3、#507 Shock heal this 3、#15 空效果。这些片段的事件、对象、引用和固定数量可直接与卡面逐项核对；召唤空位、手牌容量、Shock 触发频率等执行/定价条件仍由共同 context 负责，不由 LLM 给概率。

## 探针解释与审核准入

summary 只将整体通过的 inventory_004/006 纳入 exact agreement，不能代表全部 8 次。重新读取 8 个原始批：#20 有 8 个 signature（signature 包含 unresolved 文本，不能把 8 个直接称为 8 种真实机制）；共同的 monster-only recipient 已不足以表达给定 ALL 的玩家范围，另 inventory_005 把 source 由 this 改成 targeted_monster，值得人工阻断。#49 有 2 个 signature、7 个完整行版本：inventory_005 的冗余 target=self，其余 target=other，但 recipient 均 monster_this、amount_basis 均 hand_size_after_play、amount=1、stat=both，实际主体与公式保持一致。其 notes 漂移不等于身材公式漂移。

因此下一步应保留全部原始结果和 hash；另建逐行人工审核记录与 salvage 清单，不改写失败文件来伪造成功。当前不应把 `consistency=false` 当作“请求没有执行”，也不应把 `parsed/structure passed` 当作规则正确。本轮先封存以上已核实证据；未做全部 64 卡的最终语义批准，亦未验证真实服务器条件 Haste 的减伤判定。
