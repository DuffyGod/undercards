# 从单卡胜负转向携带优先级

先读[携带指南](GUIDE.md)：给出默认优先费用/角色区间、何时改变优先级，以及哪些建议仍是工作假设。重点是有效早场覆盖、实际支付费、单张牌持续转化资源的能力、关键交换阈值和主力落地时间。

当前筛选顺序是：先覆盖能独立兑现的早期行动；以实际3–6G站场兼即时作用/续航为主体候选；按高密度交换、回场或终结需求选特定高费。它不是已验证的最佳费用配比，程序也不生成卡组。

## 只读查询

以下命令只读冻结结果或求解析约束，不重跑战斗/旧实验/API。

9G主力最早付款窗口和不延后的先期支出余量：

```sh
python analysis/card-comparison/2026-10-20/carrying-priority/carry_math.py --anchor-cost 9 --seat first
python analysis/card-comparison/2026-10-20/carrying-priority/carry_math.py --anchor-cost 9 --seat second
```

25张、无换牌、均匀洗牌、已看4张时，8张有效开局牌的覆盖条件：

```sh
python analysis/card-comparison/2026-10-20/carrying-priority/carry_math.py --effective-openers 8 --seen 4
```

桥接与最早大怪的取舍；后手自动使用t3而非t4的大怪对照：

```sh
python analysis/card-comparison/2026-10-20/carrying-priority/query_sequences.py --question bridge-heavy --seat second --enemy mid_pressure
```

同费用下，Bench抽到的牌真正提前打出，是否值得放弃Aaron的1点攻击：

```sh
python analysis/card-comparison/2026-10-20/carrying-priority/query_sequences.py --question use-draw --seat second --enemy mid_pressure
```

`--question`还支持`timing`、`bridge-mid`、`self-draw`、`mid-versus-heavy`；`--horizon`为4或5，己方SOUL为Integrity或Kindness。九组共同身体/伤脸价格只在手牌价1处齐全，中心另保存手牌价0/2；查询不填补没有的组合。`--trace`返回完整选定行动见证。MAX/MIN只优化普通攻击，固定出牌脚本不等于最优自由出牌，先后手终点也不能混合成环境平均。

## 证据入口与延续规则

- [短序列结果说明](REPORT.md)、`sequence-results/`、`sequence-earliest/`：真实自然经济与到牌、己t4/t5普通战斗。后手更早主力是新增反事实，没有覆写旧结果。
- [carry-math.json](carry-math.json)：金币阶梯、开局覆盖条件和长期纯低费付款上界；`math-checks.json`保留独立组合枚举核对。
- [真实身体基准及排除理由](review-body-benchmarks.md)、[27条卡面记录](body-benchmark-candidates.json)：不抹掉自伤、衰减、补牌或启动代价。
- [默认费用建议的独立挑战](review-carrying-ranges.md)、[短序列范围审查](review-opening-sequence.md)：包括对后手延迟、补牌被闲置和截止偏差的批评。
- [独立保血上界手算](review-safety-proof.md)、`safety-probe.json`、`safety-bridge-heavy.json`：资产报价与用途保证的区别；高分不能补偿截止HP目标失败。
- `sequence-verification.json`：四项首次机制检查、两项随后新增针对检查的实际记录，不冒称最后重跑全套。

所有新结果随Git保存。已有[共同手牌12G研究](../README.md)、[19日单卡研究](../../2026-10-19/README.md)保持不变；不要为了刷新报告重做它们，也不要重建缺失的旧大型实验作为前置。后续优先尝试能推翻默认携带建议的真实机制与条件，而非扩充相同结论的场景数量。
