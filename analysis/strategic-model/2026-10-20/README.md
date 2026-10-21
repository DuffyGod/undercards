# 从随机资源演化连接到相互提防的策略研究

先读仓库[研究原则](../../../RESEARCH_PRINCIPLES.md)。本目录是依据该思想自主选择的一次方法辨别，不固定未来研究题，也不尝试把少数角色当真实全卡池。

已有工作分别拥有随机开局和有限信息付费回应证据。此次用可修改的机制角色连接二者：从30HP/1G/随机起手出发，双方在真实资源约束下部署、攻击、补牌、回复、留牌与支付惩罚，继续观察受罚后恢复；比较固定立即回应与有意识保留，以及我方针对它的策略改进。详见[协议](PROTOCOL.md)。

模型不使用BodyScale、F/J或外部卡价作为目标。优化的是明确的期限生命差，另外保留实际胜/负/未结束。对手隐藏手牌真实从牌库抽取，政策看不到它。A的提防基于公开现金与未见回应，是启发式，不冒充行为后验；矩阵解只覆盖声明的策略池，不是完整游戏均衡。

源码/协议先提交，正式训练与评价牌序分离，保存每个种子的结果和可重放配置。公开0回应、不可支付、不同群伤阈值、同成本单体Kill、首抽与期限变化均有对照。不是卡牌档案数量的扩充，也不是旧实验重跑。

## 入口与复现

- [证据桥接](evidence-review.md)、[独立方法挑战](independent-challenge.md)、[抽象审查](modelling-audit.md)、[实现复核与修复](review-implementation.md)。
- `model.py`：机制角色与纯观察策略；`run.py`：冻结执行、共同种子与原始结果；`policy_game.py`：有限矩阵求解及数值上下界；`analyze.py`：训练选择后在独立牌序评价，不按隐藏世界挑策略。
- 结果入口是`experiment-v01/manifest.json`和`experiment-v01/derived/summary.json`；原始种子级JSONL采用gzip保存，全部随Git交付，不依赖未上传大型轨迹。完整行动见证在summary中。

```sh
# 只读条件结果，不运行模拟
python analysis/strategic-model/2026-10-20/query.py --world sweep_integrity_seat0 --against hold_two
python analysis/strategic-model/2026-10-20/query.py --world focus_kindness_seat1 --policies
```

新模型用Python标准库，矩阵求解/分析另需NumPy和SciPy。修改后仅运行受影响检查；不要为了接续而重复已有实验。若因新问题确需新的正式研究，先修改并提交协议/源码，再用新的目录执行：

```sh
python analysis/strategic-model/2026-10-20/run.py --out <新的冻结目录>
python analysis/strategic-model/2026-10-20/analyze.py --experiment <该目录>
```

执行器拒绝覆盖已有批次，也拒绝在数值源码未提交时执行。结果只能支持这些抽象条件下的研究判断；将其映射到实际卡、构成或对手，需要继续挑战缺失的常见机制、政策充分性与外部效度。没有把这一验证步骤称为完成全部建模。
