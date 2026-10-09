# 启发式卡牌估值工具：迭代中

当前日期2026-10-08。这是低成本、解释型工具，不是完整对局模拟器或已校准天梯强度榜。主智能体设计数值函数；DeepSeek只辅助提取机制、条件和疑问，不输出Gold价格、最终分数或实战概率。

## 可运行部分

- `score_cards.py`：共同身材函数、简单即时效果、四类角色参数、±1敏感度。复杂文字保留partial，正式分数留空。Aaron的5G只作为显式尺度锚，不是强牌标签。
- `heuristic_contexts.py`：原始24个情境模板和数量表达式；统一入口进一步把资源与场面拆开；互斥选择、实际支付与未用降费记账。
- `context_value.py`：0.4.0逐情境账本。404张4–8G池中17张完整文字可由受限模块执行，其余保留partial；不代表全牌实战估值已完成。
- `unified_value.py`：当前主要入口。默认72个共同状态；所有卡保留相同权重，允许有限等待与满手额外烧牌损失。主分数是未截断的条件部署报价差，非现金利润；不可在窗口内部署或机制不支持时整卡主分数留空。
- `coupled_magic.py`：Magic目标与Haste行动共同选择，按同一有限窗口比较P0（普通主体＋原场面）、Pmid（Magic后普通主体）、P1（Magic＋关键词）。三项账目望远镜求和，不重复给击杀奖金；支持其它友军/双方玩家的正确单目标范围。
- `combat_increment.py`：本回合Haste攻击、付费合成回应、下一己方回合普通攻击的成对资源差；Magic世界相同，嘲讽与伤害实例共用约束，终局报价留空。没有独立击杀或关键词奖金。
- `payment_frontier.py`：已知手牌的2–3轮支付计划，将降费拆为实际付款节省与额外解锁净收益；报价/行动上限须显式提供，未使用牌不计现金。
- `resource_curve.py`：仅抽牌/收入/支出；部署、留预算、攒已知关键费三策略共用牌序。无战斗/格子/换牌/疲劳，费用模型不是胜率。
- `resource_profile_bridge.py`：保留每个阶段全部非空手的Gold/手数联合频率，直接输入统一状态面板；每桶一个代表只作诊断。并未按候选在手过滤，不能当候选实际持有率。
- `build_resource_comparison.py`：三个抽象25牌费用分布、同一支出策略/种子/场面先验的端到端可复算比较；费用分布不是强牌名单。
- `batch_annotate.py`：冻结规则/模板、分批标注、重复探针、来源hash、持久化续跑、显式限额和失败重试。
- `cached_dialogue.py` / `few_shots.py`：V5为固定system与9组示例；V6独立契约为12组，最后一条才放批次卡面；独立完整前缀可复用。
- `semantic_v6.py`：有序模块、同分支多动作、事件/输出绑定与有限数量表达式。结构通过仍须审核选择器、属性覆盖、成功依赖等漏项。
- `annotation_semantic_checks.py`：只发现矛盾，不自动批准语义或定价。
- `knowledge_resolution.py`：只处理冻结K007已经明确回答的ALL目标范围疑问；原始回复不改，解析结果保留逐项解决记录。

## API派发标准

每个请求的固定前缀包含Skill规则、完整rules.md边界、全部mechanics词典、同一schema以及few-shot。动态数量表示为乘数和amount_basis，实例数count与目标数分开；stat区分ATK/HP；repeat_rule区分明确重复；choice_group防止互斥收益相加。后续沉默只针对当前这张卡，不追回已作用于其他实体的Magic。

批次按费用与机制族分层选卡，并交叉加入Vulkin/Glyde探针；对不同批次改变排列。跨批一致性仅必要条件，不证明正确。同一结构也可能重复错误，所以保留独立语义检查和集中复核。没有因为想得到某个排名而重试；`--retry-failed`只补传输失败。

缓存不是声称自动节约：直接保存实际payload及hash、共享prefix hash和接口usage。腾讯代理返回过`prompt_tokens_details.cached_tokens`，V5后续批实际为11008、11008、11264。缺少缓存字段时记录unknown。DeepSeek官方说明见 [上下文缓存](https://api-docs.deepseek.com/zh-cn/guides/kv_cache/)，接口字段见 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)；代理行为以本次实际响应为准。

## 第一轮证据

- 最初两轮16卡小批发现原文重写、目标字段、沉默对象和击杀概念错误，未通过的输出已隔离，没有直接生成榜单。
- 中央复核依然可能重复错，V3有ordinary kill/exact kill、次数/总伤害等矛盾。独立检查器明确记录，不因模型复核自称正确。
- 六张简单卡经限定语义复查，结果在 `pilot-reviewed-scores.json`；数字只覆盖首版启发式范围，不是卡牌最终质量。
- V4/V5已覆盖一个32张分层样本，完整知识前缀减少了把Need/Delay等已知规则反复列未知的问题；K007解决记录与原始差异均保存。
- 404张完整卡池的标注计划有51批，已完成16批。独立复核130张不同卡，抽查32张非探针后发现结构缺口；扩批暂停，先用保存的失败样本完善规范和局部复核。119张结构合并不等于语义批准。

V6另完成两个回归批与四个未见文本批。未见文本四批全部网络成功、16张结构通过，20探针有真实目标域分歧，退出1表示一致性门未过。见 `holdout-v6-review.md`；不为通过门禁反复抽样。逐卡定价仍以主智能体实现为准。

模型已接入有限等待、资源样本和显式已知手牌的支付解锁，但仍缺候选持有概率、构筑抽牌质量、完整对手转化与复杂循环。旧`context_value.score`可支付均值不能直接排榜；一般比较用`unified_value.py`的共同权重主分数，另外显示可支付比例和未报价原因。角色/场面/事件权重都是公开先验，不是实战统计。

## 使用

从工作区运行：

```powershell
python -X utf8 analysis/monster-value-heuristic/score_cards.py --cards 15 11 13 20 243 --output analysis/monster-value-heuristic/check.json
python -X utf8 analysis/monster-value-heuristic/context_value.py --output analysis/monster-value-heuristic/context-check.json
python -X utf8 analysis/monster-value-heuristic/resource_curve.py --demo --output analysis/monster-value-heuristic/curve-check.json
python -X utf8 analysis/monster-value-heuristic/unified_value.py --compact --output analysis/monster-value-heuristic/unified-check.json
python -X utf8 analysis/monster-value-heuristic/build_resource_comparison.py --trials 1000 --output analysis/monster-value-heuristic/resource-comparison-check
```

批量规划不会读取密钥或调用API。实际调用复用用户的`E:/NoScan/Codex/test_llm_api.py`，不会修改该文件：

```powershell
python -X utf8 analysis/monster-value-heuristic/batch_annotate.py plan --pool-4-8 --limit 32 --batch-size 8 --tag sample-new
python -X utf8 analysis/monster-value-heuristic/batch_annotate.py run --tag sample-new --max-api-calls 4
python -X utf8 analysis/monster-value-heuristic/batch_annotate.py run --tag sample-new --retry-failed --max-api-calls 1
```

变更提示/输入需要新tag；旧请求、回复、失败attempt及冻结源保持可追溯。批次失败/不一致退出非0；数值评分器还要求单独语义审核，模型自检不替代审核。进一步扩展可利用标注提出的机制组合，但要为共享模块增加规则和账本验证，不采纳模型自由报出的分数。

## 验证

当前基础、批量门禁、语义矛盾、共同context和新账本测试已实现。运行：

2026-10-08当前151项检查通过。包括独立复核发现的0ATK接触、Dodge/Armor实例、Magic/Haste共同目标、低血量入口一致性、全资源分布保留49/51支付门槛与缓存副本隔离。它们验证局部不变量，不证明151种卡牌实战强度。

```powershell
python -X utf8 -m unittest discover -s analysis/monster-value-heuristic -p test_*.py
```

最新方法与实际覆盖见 [方法与验证-v04.md](方法与验证-v04.md)，数值见 `unified-pool-v03.json`。独立复核见 `coupled-integration-review.md`、`resource-deck-review.md`。较早记录保留原版本统计，不能混作当前结果。后续按机制家族扩展死亡/生成物、回应频率和构筑抽牌质量，所有候选共用参数，不为具名卡拟合。
