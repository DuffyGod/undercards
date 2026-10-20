# 新潜力卡与具体打法比较

本轮从完整卡池主动挑选了 **29张原49档案以外的怪物**，新增183条条件动作端点、16组同根反事实比较，累计78张条件档案。这里的数字是可审查范围，不能解释成独立对局数量、正确率或78张完整实战总分。

先看[打法报告](REPORT.md)。[原始动作表](results/actions.csv)、[逐卡账本](results/dossiers.json)、[价格/身材敏感度及致死反例](results/recommendations.json)可直接复核。主查询程序`../assess.py`已经合并读取本目录的新增档案，旧673条记录保持原样。

29张为：Bomb、Igloo、Echo Fish、River Person、MTT Fountain、Elder Puzzler、Dancer Mettaton、Microwave、Cool Papyrus、Clover Hydra、Sheary、Bloxer、Shyren's Agent、Spade Chain、Soul Cage、Long Sink、Snoring Monsters、Sadmobile、Baking Queen、G Machine、Tasque、Trashy、Ambyu-Lance、Casual Guard 2、Flameguy、Searby、Pancakes、Knightdyne、Mantis Dancer。Loox等配合牌只作为实际消耗的动作输入，不额外冒充完成其整卡档案。

## 数值约定

沿用冻结的BodyScale和模型G尺度，中央价格为生命`.25`、有效手牌`1`、实际金币`1`。本轮另列：

```text
J = 双方场面资产差 + p×实际生命差
    + ρ×(获得/抽入/回手 − 全部打出 − Erase − 对手新得牌)
    + λ×(实际兑现金币 − 实际支付金币)
```

这是**包含实际手牌库存变化的动作净值**，用于同一局面下比较不同出牌数的打法。`conditional_gross_before_played_cards`和`payment_margin_before_played_cards`仍保留未扣打出牌库存的G/N，供解释。生成后已打出的牌，获得与打出抵消；折扣只有真正少付时才计实际金币。

旧档案的N将共同一张焦点牌的承诺作为基线；直接与J混比会少扣一张牌。因此查询明确拒绝跨这两种口径直接比较，也拒绝把本轮J直接套入`max(0,J)`携带门槛。负J不能推导“不该建场”，详见报告中的标尺反例。

所有端点附带条件、路径、兑现阶段、消耗卡、未定价项。普通探针敌人无Dust/护甲等能力；特殊Armor反例单列。默认BRAVERY、当前开始效果已结算、无相关神器，英雄20HP、对手30HP、初始手牌不超过4；记录的具体条件覆盖默认，例如Long Sink的27HP、River的5/7手牌。单位列表表示实体，不冒充四个物理格编号；正前方/入场空格必须满足记录的额外位置条件。

## 使用

```sh
# 查看合并后的755张目录或78个条件档案入口；不修改旧目录文件
python analysis/card-assessment/2026-10-20/assess.py catalog --modeled-only

# Agent轻伤1HP时，治疗与6点溢伤的完整端点
python analysis/card-assessment/2026-10-20/assess.py card 437 --root agent_missing_1

# 同一5/5：Searby vs Loox+Soul Cage
python analysis/card-assessment/2026-10-20/assess.py compare tactics/852/one_5_5/magic_0 tactics/506/one_5_5/loox_then_soul_cage

# 身命价值变化会翻转Long Sink的动作选择
python analysis/card-assessment/2026-10-20/assess.py card 509 --root sink_hero27_tiny --face .15

# Mantis的逐目标端点；群伤每一轮保存在dossiers的features
python analysis/card-assessment/2026-10-20/assess.py card 964 --root carousel_target
```

源码在`build_tactics.py`、`resource_routes.py`；通用记账在`tactic_core.py`，后者不按卡名定价。修改新机制后只运行受影响的新检查；本轮13个定点检查及结果保存于[verification.json](results/verification.json)，未重跑旧开局模拟或历史测试。需要重新生成新算术结果时运行：

```sh
python analysis/card-assessment/2026-10-20/promising-tactics/build_tactics.py
python analysis/card-assessment/2026-10-20/promising-tactics/derive_recommendations.py
```

卡面来自2026-10-05快照，未确认当前服务器版本。DeepSeek当前正常客户端缺少凭据、环境绑定skipped，新HTTP请求0；既有95批队列未假报为完成。独立候选阅读保留于[candidate-review](candidate-review.md)；其中Martlet/Trial Ralsei仍是未建模候选，不能算入这29张。资源路线有另一Agent独立编写；最终机制与账本由主Agent复核，检查通过不等于服务器裁定或实战校准通过。
