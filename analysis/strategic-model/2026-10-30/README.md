# 真实白板身体、协调攻击与机会兑现

本目录在20日的机制角色模型上，增加逐卡真实费用/攻防、协调攻击、已知手牌付款等待及训练/评价分离。实卡入口严格限五张无额外能力怪物；host其余部分仍是聚合角色。**不能称现实合法卡组或全卡池强度榜。**

先读[结果报告与条件建议](REPORT.md)，再按需查[冻结协议](PROTOCOL.md)、[卡面与来源](real-body-bridge.md)、[独立反例](policy-challenge.md)、[实现审阅](policy-implementation-review.md)。93312训练记录与132480新评价记录均已完成，原始压缩输出及[冻结策略结果](experiment-v01/summary.json)、[固定规则比较](experiment-v01/fixed-policy-comparisons.json)、[上手/出场分母](experiment-v01/opportunity.json)、[训练选卡与评价](experiment-v01/body-recommendations.json)均保存在`experiment-v01/`。共享牌序不能按记录数当独立样本，负结果未删。

程序分工：

- `tactics.py`：本回合普通攻击/一次已持有且付得起回应的精确可达端点；端点选择偏好是启发式，非全局价值函数。
- `engine.py`：保留旧规则，三槽实体配对替换；实际候选费用、攻击、HP进入部署/攻击。六政策含只改攻击的消融、联合施法以及存钱等待。
- `experiment.py`：先训练48个新牌序，再冻结有限池混合，最后评价128个全新牌序至模型内HP终局。不重跑旧数据，不猜未决赢家。
- `opportunity.py`：只读取保存的评价，分开未收到候选、收到未打出、至少打出一次；诊断不是已定价机会成本。
- `query.py`：只读条件剖面与预先指定的配对比较，默认不输出全局排序。虚构数值反事实要显式打开。
- `fixed_policy.py`：从同一评价提取相同策略规则下的身体对照，不把策略适配差混成裸身体效应。
- `recommendations.py`：只用训练选择五张实卡中的条件候选，先提交，再报告新评价；明确保留选卡失败。
- `verify_saved.py`：只读核对原始网格、终局、守恒收据、查询和文档，不再模拟。

只读查询：

```sh
python analysis/strategic-model/2026-10-30/query.py --world sweep_integrity_seat0 --host wide
python analysis/strategic-model/2026-10-30/query.py --world focus_integrity_seat1 --host anchor --compare Aaron 'Rock Pet'
python analysis/strategic-model/2026-10-30/query.py --body Rock_health4 --counterfactuals
```

运行依赖Python3.11+、NumPy、SciPy。正式`train`/`evaluate`拒绝覆盖已有实验，且要求源码/协议与选择先提交。无需启动时重跑。`pilot.json`是288条开发轨迹及运行检查，早于攻击消融/等待行；不混入正式证据或独立样本计数。

周期执行的用户要求与阻塞状态见根目录[RESEARCH_AUTOMATION.md](../../../RESEARCH_AUTOMATION.md)。此文或本地运行本身不会创建持久定时任务。
