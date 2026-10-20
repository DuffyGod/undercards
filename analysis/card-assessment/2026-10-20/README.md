# Agent 主导的逐卡多维评价

当前主线已改为：**从全卡池读卡与推演 → 提出用途和比较候选 → 写可复核的条件账本 → 程序做共同定价、敏感度与反例检查**。卡牌无需先被对局模拟器实现。`value_ledger.py`不含卡牌ID、效果白名单、固定出牌脚本或环境频率；任意Agent推导的前后端点均可输入。端点是否符合卡面仍要机制复核，计算通过不能替代它。

[数值标准与实例](MODEL.md)、[24张自主候选](candidate-mechanics.md)、[独立标准审查](review-standard.md)、[机制审查及修复](review-ledger.md)。旧[联合开局研究](../../card-comparison/2026-10-20/joint-opening/README.md)保留为局部证据，不再决定能研究哪些牌。

## 当前交付与未完成部分

- **755张普通可构筑卡目录**：671怪物、84法术，逐卡有卡面、数值特征、印刷费付款窗口及持牌模型入口；未研究效果不按白板整卡评分。
- **49张Agent条件档案**，含673条条件端点/价格记录，另有固定伤害包抗性维度。记录数不是实验次数、覆盖率或正确率；不少条件仍有显式未定价特征，不能说49张已得到完整实战总分。
- **197张旧DeepSeek材料索引**：逐卡保留归档成员、原结构/语义状态与分歧。旧目录名complete404不能当404条完成，实际对应聚合仅119条；未重跑缺失任务，未将旧结构通过升级为本轮已验证。
- **95个新用途审查批次**：每批8张、全池755张、固定Toriel/Rod探针、完整共享前置与卡池索引。当前凭据缺失，**本轮实际API请求为0**；不能把待执行队列算完成。默认只跑两批pilot，主Agent检查后才扩大并发/批量。

**755张全部可靠定价仍未完成。** 该目录和队列保证未实现/未审阅卡不会被悄悄排除；当前可用产出是条件价、明确的携带门槛和可比较家族，不是全池强度榜。无外部对局数据时，真实机会频率、持牌摩擦和环境替代价值仍须保留为未知。

## 三个维度

1. **绝对条件收益**：共同模型G尺度下的身体及效果收益，另列支付后的余量；不按费用归一化，不以各批LLM估值平均作为Gold。
2. **出手/携带机会成本**：可选择不出；给联合可执行窗口概率q、额外持有摩擦H与替代收益R的条件门槛。q/H/R没有数据就不填假数。手牌溢出有可执行的成对库存计算。
3. **用途与其他特征**：兑现阶段、卡/金/格占用、即时/后续作用、固定伤害包抗性、对位与对手规避、未定价能力。未来回合、死亡后、Delay后与当前部署禁止混作同一时点。

## 直接查询

```sh
# Toriel对8/8目标；读取具体条件，不做整卡无条件总分
python analysis/card-assessment/2026-10-20/assess.py card 8 --root tall

# 携带门槛：H=.75是示例假设，q不是推测的真实概率
python analysis/card-assessment/2026-10-20/assess.py carry 8/tall/0 --bad 8/small/0 --holding-cost .75 --q 0 .25 .5 1

# 同费Bench-Aaron，求有效额外牌价格的翻转点
python analysis/card-assessment/2026-10-20/assess.py compare 243/empty/1 15/empty/0

# 同一张卡持续占手 vs 已使用替代卡，计算额外烧牌量
python analysis/card-assessment/2026-10-20/assess.py holding --hand 7 --draws 1 1 1 1 1 --plays 0 0 0 0 0

# 不在预设目标中的新端点：不需要实现/注册新机制
python analysis/card-assessment/2026-10-20/assess.py ledger analysis/card-assessment/2026-10-20/examples/toriel-7-4.json

# 尚待分析的卡也能查询，明确返回pending而非假0分
python analysis/card-assessment/2026-10-20/assess.py card 1000
```

[实际查询输出](query-examples.json)、[全池目录](results/catalog.json)、[49卡完整条件档案](results/dossiers.json)、[可比较CSV](results/conditional-values.csv)、[跨卡翻转记录](results/family-comparisons.json)。CSV的stage和unpriced必须一起读，不能排序gross列后称为全池强度榜。

## DeepSeek协同

云环境当前`TENCENT_API_KEY`状态skipped，正常客户端也没有可用凭据；请求未发送，原因保存于[preflight](deepseek-opportunity-v1/preflight.json)。在环境中绑定凭据后可执行：

```sh
python analysis/card-assessment/2026-10-20/deepseek_queue.py run --limit 2
```

新任务询问价值驱动、好/坏出手窗口、持有损失、对手规避与替代卡，不请求最终Gold分。固定完整prefix用于缓存；先预热首请求，之后最多4并发；保存逐次payload/raw/错误/采纳前状态，不自动语义重试。结构校验按行保留可审查资料，结构通过仍不是语义通过。尚未实际跑通新协议，不能称质量或缓存命中率已验证。

旧[来源索引](reused-evidence.json)与[复用边界/疑点](reused-evidence.md)继续保留。下一步先复核新pilot与未覆盖高价值家族，不为了计数让程序把剩余706张效果设零，也不恢复旧模拟器作为前置。
