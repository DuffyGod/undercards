# 隐藏手牌下的比较：独立反例与精确界

2026-10-17。此目录只做独立复核，不导入主侧 `finite_game` 引擎或 belief 程序。以下数值是明确窗口的物理 HP，不是单卡通用分数、环境概率或人工 Gold。全部原生卡面及源 SHA 在 `independent-hidden-menu.json`。

## 1. 根行动不能先看隐藏牌：12 HP 是泄漏，确定性保证只有 9 HP

公开场面：己方 15 HP、5G、空场、手牌 Jerry #14（5G，4/5，Taunt，受到 COST≤4 怪物伤害减1）及 Aaron #15（5G，6/5，白板）。敌方 Lady Garf #246 已站场 3/6，printed/base/current COST 均4，Magic 已在此前完成；本窗口不再触发它的随机选牌。敌2G，隐藏手牌只有一张：Penetration #79（1G，Silence a monster），或 Worsening #86（2G，ATK−1/HP−2，完整 Delay 条件见快照）。

两张隐藏牌正式都为 **Generated**，可来自此前共同公开的 Bone Box #402：`Magic: Look at 3 random spells costing 3 or less GOLD and choose one. Add it to your hand.` 骨盒来源已经离场。**信息规则假设**：Bone Box 的 look/choose 结果未向对手公开。卡面未写 Reveal，但本地快照不能替代服务器 UI 观测实测；若实际客户端公开结果，这条生成历史就不能维持两个世界在同一信息集。反例的策略结论以输入声明该手牌身份未知为条件。Penetration 和 Worsening 属于不同 SOUL，若都说是同一公开 SOUL 的原生牌则构筑不合法；初始错误提案及原始输出保存在 `rejected-cross-soul-*`，不作为正式证据。正式 Generated Worsening 不触发“非 Generated 才 Add”的分支。

行动窗口：己当前部署/等待 → 敌完整行动 → 己完整行动 → 敌完整行动。无收入、无抽牌、无其他被动或神器。己方可以等待；没有强迫无收益打出。敌可以等待、攻击玩家或怪物、施法指定任一合法怪物，所有攻击/施法先后均枚举。

| 己根选择 | 隐藏 Penetration | 隐藏 Worsening |
|---|---:|---:|
| 现在打 Jerry | 9 | 15 |
| 现在打 Aaron | 12 | 9 |
| 当前不打牌 | 9 | 12 |

每个格子是固定根行动后的 **逐世界** 完整行动枚举值；不默认这些格子的未来策略天然能共同实现。因此先取各世界最优再取最差得到12，只能当 clairvoyant 上界。根行动必须共用时，上界是 `max(9,9,9)=9`。

存在一个无需看隐藏牌的共同策略闭合下界：现在打 Aaron，下一己回合若敌怪仍活就攻击它。该策略在两个世界的最差结果分别是12、9，保证9。因此确定性策略的上下界闭合为 **9 HP**。同样规则但现在打 Jerry 的两个保证为9、15，下一步攻击规则也完全相同，不使用世界标签。

手算关键线：

- Penetration 对 Jerry：Silence 后敌3/6先打脸3；下回合 Jerry 4ATK 不能杀6HP敌怪；敌下一回合仍能打脸3，己最终9。Aaron可6ATK换掉敌怪，只吃第一次3，最终12。
- Worsening 对 Aaron：Aaron变5/3，敌先打脸3；己若攻击，5ATK不足以杀6HP敌怪，且自身吃3反击死亡；敌再打脸3，最终9。
- Worsening 对 Jerry：Jerry变3/3；敌3ATK被COST4抗性减为2，Jerry剩1HP，反击把敌降3HP；己下一回合3ATK可击杀敌，己英雄始终15HP。

另单独执行 **原生** Worsening 单世界规则探针。若敌先攻击 Aaron，Lady Garf 被6反击杀死而 Aaron降至2HP；再用 Worsening 可将 Aaron 降至0，回合末确实生成副本。独立枚举实际看见5条含生成的历史；敌支付2G后为0G，副本仍需付2G，本窗口不能免费施放。该探针不与正式 Generated 隐藏菜单混算。

如果另定义“己方私有随机化的期望HP”，则不是上述物理HP保证。假设隐藏世界在抽签前固定，己用 Aaron 概率2/3、Jerry概率1/3，再用前述共同攻击规则，两个世界期望都恰为11。即使敌看见打出的牌后调整动作，这个保证仍成立。JSON还给出代数上界证明11；证明权重不是环境概率。禁止把期望11写成每次至少11，也禁止把确定性9误说成所有随机化效用的界。

## 2. 敌公开行为不同后，己未来可以合法适应：11 HP，错误全程绑目标只有10

起点位于敌方一个回合中途：敌已有 Moldsmal #4，3/2，**本回合已经用完攻击**，己当前15HP。敌剩5G、隐藏一张手牌为 Snowdrake #11（4G，4/4，Magic使友军+2ATK）或 Aaron #15（5G，6/5）。己手里仅 Gaster Blaster #351，4G，`Deal 8 DMG to a monster or you.`，己可用4G。

敌打完牌后己回合可观察公开卡牌、buff、位置与金币，再选择法术目标；之后敌完整攻击一次。新打出的 Snowdrake/Aaron 本来无 Haste/Charge，在先前敌回合不能攻击；原 Moldsmal 也已攻击，故不能再攻击。此处的“已经攻击”是明确公开前缀，不是给敌方剥夺合法攻击。

| 己未来目标 | 已公开 Snowdrake 给旧 Moldsmal +2ATK | 已公开 Aaron |
|---|---:|---:|
| 杀旧 Moldsmal | 11（剩新4ATK） | 9（剩新6ATK） |
| 杀新打怪物 | 10（剩旧5ATK） | 12（剩旧3ATK） |

两个公开历史已经不同，所以正确策略可在 Snowdrake-buff-old 分支杀旧怪，在 Aaron 分支杀新怪，保证11。强迫所有世界、整个未来使用同一目标，会错误得到10。额外完整处理 Snowdrake可buff自身（新6/4、旧3/2）及两菜单各自选择不出牌；前者观察后杀新怪得12，后者两个公开历史相同且都杀旧怪得15，均不降低11。

这证明策略应该绑定于 **己方观察历史/信息集**，不是永远绑定一条行动序列；也不是一见隐藏世界不同就全部允许分拆。

## 3. 敌行为相同但隐藏牌不同，仍不能拆己策略

为第1组加一个共同公开前缀：己原18HP，敌 Lady Garf #246打脸3到15HP，然后不施放隐藏法术并结束回合。两世界敌仍2G、手牌数1，牌仍分别是 Generated Penetration/Worsening。前缀中的攻击、伤害、结束回合完全相同。

`independent-information-sets.json` 序列化两世界的公开状态及完整共同公开前缀，两个 SHA 完全相同。在这个己行动节点，禁止根据世界标签选择“若79打Aaron、若86打Jerry”。该虚假分拆仍给12，合法共同策略保证仍9。“对手没有施放”不是足够的区分信号；没有经验证的行为模型时，不能据此捏造概率或排除世界。

## 可重复执行与边界

```sh
python analysis/monster-value-heuristic/research-runs/information-policy-v01/review/independent_hidden_menu.py
python analysis/monster-value-heuristic/research-runs/information-policy-v01/review/independent_information_sets.py
```

第一脚本逐动作独立枚举，给矩阵、最差行动见证、共同策略向量、实际生成分支与原生全卡面。第二脚本穷举第二例所有候选施法目标、打自己/等待，处理敌 Snowdrake 两个可见 buff 目标和 held 菜单；并比较第三例的完整公共序列化。两脚本不调用主模型，也不复用主模型评分。

尚未证明：SOUL/神器长期收益、完整牌库抽牌分布、跨整局的校准、这几个卡牌的通用构筑价值。这个窗口确证的是隐藏信息下的合法策略约束，不能直接转成世界发生率或全池排名。
