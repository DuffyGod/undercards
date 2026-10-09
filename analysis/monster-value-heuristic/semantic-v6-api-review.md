# semantic-v6-regression8 原始API语义复核

审查日期：2026-10-08。范围为 `annotation-runs/semantic-v6-regression8/batch_000.json` 与 `batch_001.json` 原始输出。未调用API，未修改冻结请求、批次、冻结语义文件、API适配或价格程序。

## 结论

V5中主要的表达性失败已经改善：同一分支多动作、Shock触发、7−H、生成物属性绑定、事件数量依赖、普通kill和Shock开关均准确出现。但仍有未完整承载的限定，尤其880的base COST及跨区费用数据；因此“8张结构全部通过”不能等于“8张都可直接定价”。

这是**已知失败样本的回归**。八张requested中394、775、503、471、664、201、958共七张在本次fewshots中有同文本示例；880没有整卡示例，但其分支结构由类似示例覆盖。不能用这个结果估计未见卡牌的标注准确率。

两批共12条观测、10张不同卡（8张requested＋20／49）。现有合并记录：invalid_tasks为空，requested accepted_count=8；20完整signature有2种，49有1种。`all_batches_consistent=false`及`semantic_review_required=true`仍保留，未宣称正式评分可发布。

## 逐条原始语义审查

| 批次／ID | 已改善／正确内容 | 尚存问题与执行边界 |
|---|---|---|
| 000／394 | left分支同时包含+1/+1与Armor；right同时召唤与输出Haste，Haste明确recipient_ref=c；左右guards互补。body_and_future与自身buff及能力一致 | 复制是否取当前／基础状态仍不由card_ref=394表达；不能直接把ref解释成新印刷版本。副本Magic默认不触发的前提已明确，勿重列未知 |
| 000／880 | right同时1点all_enemies与Haste；all_enemies包含玩家，修复V5遗漏。左7点伤害，Bullseye存活条件，return与discount分开 | return模块d错误携带amount=-1；费用改变另在e中，存在泛化执行时重复读取风险。e的stat=COST不能区分**base COST与current COST**。左分支“正前方”只留在evidence，未成typed选择器。需在定价前解决这些限定 |
| 000／775 | Attack为shock，不再magic或泛化passive；Candy／Disarmed仍是被动状态；最低HP敌怪条件保留 | 最低HP是自然语言选择器，非typed算子。无需再次抽样；简单执行器要么明确解析该选择器，要么保留未执行状态 |
| 000／503 | amount=1，hand_empty_after_play，count=1；Need guard保留。没有再把手数当空格数。notes明确7−H及Need失败仍可打本体 | no-duplicate过滤仅在原文／notes及need_satisfied抽象guard。需要调用者给出经验证的当前牌库Need状态，不能默认true |
| 000／20 | damage2、magic、单实例、recipient=other，notes遵循宽单目标与排除施法主体前提 | 无新数值问题；recipient=other仍由输入ALL前提决定合法目标，不是AOE |
| 000／49 | 1×打出后手数、both、count1、body暴露，准确 | 与001完全一致 |
| 001／49 | 同上 | 没有typed分歧 |
| 001／20 | 核心数值与typed字段同000 | 新增英文“ALL target selection among enemy monsters/player is not further specified...”疑问。已给K007完整前提，不应重新列为未知；措辞还漏提友方合法目标。但没有把typed改为enemy_only或AOE，故是已知规则应用／疑问治理问题，不是伤害标准漂移 |
| 001／958 | 自身2伤害＋all_enemies2伤害完整，Shock先关闭0，Support后重启1；heal为support，unknown数值，partial。full heal没有被误当持续HP增益 | max_HP−current_HP不在当前有限表达式中，partial是正确的能力覆盖边界；不用将已知full-heal含义当规则未知。真实队列顺序依旧不由此测试确认 |
| 001／201 | 普通攻击kill guard，没有exact_kill；heal4明确给player_self；summon359，未来能力暴露 | 互相死亡／是否仍触发的队列未验证，不应自行加actor_survives。现有输出没有偷偷加此条件，保持正确保守边界 |
| 001／664 | erase数量取dustpile按753过滤；add数量引用event_erased(a)；输出Haste绑b；buff数值引用event_not_added(b)，受益输出也绑b。未再用非法dustpile_composition basis，Erase≠死亡前提保留 | 事件执行器须区分attempted／successfully-added／not-added记录，不可把全部尝试量当成功输出。这里引用正确，但不证明容量处理或游戏队列已经执行正确 |
| 001／471 | you伤害5给player_self；add数量1；COST+1、+1/+1、Haste分别绑add输出b，不再给施法主体，也没有漏掉费用变化 | 看2个随机LostSoul再选择一个只有evidence与notes；候选池、offer数量及选择过程尚非typed。可用于机制账本核对，不应当作任意已知LostSoul的直接生成 |

## 探针分歧分类

- 49两批完整signature一致。
- 20两批的modules、condition_codes、timing、silence_exposure、annotation_status完全一致；只差unresolved。
- 这次20的condition_codes两批都为空；与旧版本的target_exists差异是跨版本规范漂移，不是本次两批相互不一致。
- 已给K007后再提出英文目标范围疑问，是应用已知前提失败。`known_rule_resolutions=[]`说明当前resolver没有归一化这条英文疑问；不应靠第三次重新请求模型来“投票”消除。
- generic recipient=other与单个宽目标没有冲突，但具体合法目标应交由给定元数据／规则前提解决，不能按英文notes漏提友方而缩窄typed目标。

## fixed count=null 的漏洞与本次修复

原live V6允许一个 `kind=draw,count_basis=fixed,count=null,annotation_status=parsed` 通过。这个状态无法知道抽牌数量，且没有明确unknown门，应拒绝。

已只修改**live** `semantic_v6.py` 和本智能体的 `test_semantic_v6.py`：

- VERSION从0.1.0升为0.1.1。
- 任意fixed count必须明确非负整数；null必须转为count_basis=unknown并标partial，或按卡面a card正确填1。
- 唯一CONTRACT同步说明此约束，没有追加矛盾旧说明。
- 新测试依次检查fixed/null拒绝、unknown/parsed拒绝、unknown/partial允许、fixed1/parsed允许。
- 14项测试全部通过；使用新live validator重验原两批，均仍通过，因为实际输出count全部明确。

冻结目录的 `semantic_v6.py` 与已发送请求完全未改。格式校验增强不追溯伪装本次API已使用新版本。

## 应当集中处理而非重抽样的事项

1. 880的return amount应为null；费用改变保留在单独discount模块。明确base/current字段作用域，再验证返回后的状态保存，不能把两份-1都当现金收益。
2. typed recipient与数量已经能承载主要失败样本；下一步只补最低HP／正前方／随机候选选择这类有限选择器，不要扩展成自由脚本。
3. 已知规则resolver用规则ID与多语言归一化处理ALL、Summon默认不Magic、Erase不Dust等前提，仍保留真正未裁定互动；清理不能抹去其它疑问。
4. 先使用这些冻结响应做确定性回归和人工集中修订，再抽真正未见文本验证迁移。当前多数样本直接出现在fewshots中，继续重复它们无法提供泛化证据。
5. 输出仍是语义数据；tuple/branch正确、fewshot回归正确及schema通过都不能替代定价账本的条件兑现与公开参数。
