# 两段窗口与账本接入快速复核

2026-10-08。只读复核 `combat_increment.py` 0.2.0、`context_value.py` 0.3.1 和 payment_frontier 0.1.0；未修改程序、未调用API、未运行完整对局。仅写本报告。

审查时源码 SHA256：combat=`75b3269f3f7cb59c39621b689eb9e95c3b821bbb5d94b0075d5a94892918b597`；context=`0e46d0227531e4b5725ef8a011413cf00987def16c20cb846e6699804346adb2`；payment=`4f01afc90727688f7b644161f80f2f2172f0e633461d47873be76b651af5f961`。

## 当前默认面板结论

**未发现阻断默认24个context交付的具体重复计价或非法攻击。** 4～8G完整支持中，实际接入combat的只有Tsunderplane（21）与Sad Dragon（168）。默认敌方合成身体攻击至少2且没有防护状态；下面两个合法性反例均属于外部泛化输入，不会由这两张牌在当前默认面板产生。

已检查：

- Haste最多一次当前怪物攻击；双方存活主体下一回合最多一次正常攻击。空场不能当前Haste打脸。计划共用`legal_own_targets`，当前及下一回合遵守敌方Taunt；零攻击我方不能行动。
- 第一段计划在回应前固定，下一回合行动只读取回应后的状态，未发现未来信息泄漏。
- Tsunderplane的Magic先改变`combat_enemies`和对方HP，再将相同初始世界传给普通／关键词两路。自定义1HP敌怪被Magic移除后，在两路的全部回应中均保持死亡；Magic脸伤仅一条账本。该检查的Haste premium与component_deltas之和均为0。
- 关键词项只加入`special−ordinary`，没有再加击杀、额外攻击或独立Dodge奖金。现金差分明确是对手资源效用，不是我方到账。
- 任意正权重合法候选涉及终局时，premium留空，而非用资源Gold给终局定价；接入层拒绝这种数值化。默认30HP和目前两张完整combat牌不触发该边界。若未来自定义面板出现终局，建议按context返回“无法资源估值”，避免整个批次因异常中断。
- flags严格bool、Dodge非负整数且排除bool、数值有限、回应键和权重校验，已修复之前的字符串／小数闪避／NaN问题。

## 外部泛化输入仍存在的两个反例

### 1. 0攻击敌怪仍能发起接触

输入：我方3/3、Taunt，敌方0/2，0G，aggro，`enemy_face=1`。当前特殊路线让0攻击敌怪“被Taunt强迫”攻击我方、吃3点反伤死亡，然后我方下一回合打脸3；普通路线需要花自己的攻击击杀它。结果`premium=0.54`。

正确的0攻击敌怪不能发起这个攻击；两路不应因此产生免费反击收益。`trade(...,attacker_is_actor=False)`与`reply`需排除0攻击敌方攻击者。这是独立原语的真实合法性缺口，当前默认面板不触发；在今后加入减攻至0的场景前应修复。

### 2. Magic直接扣HP，未处理敌方Armor／Dodge

使用真实Tsunderplane模板，外部context敌方为3/1、Armor。正确的一次1点Magic伤害由Armor减至0，敌怪存活；`combat.hurt`离线返回HP1。接入代码却直接将HP降至0，两路均把敌怪视为已死亡，Magic账本也据此获得移除收益。Dodge有相同类别风险。

当前默认敌怪没有防护状态，所以不影响当前输出。最便宜的处理是：接入层显式拒绝带状态的敌方Magic目标并标为部分支持。若要支持这些场景，应由同一个伤害原语生成Magic前后状态，伤害账本也使用同一前后身体差分；不能只修combat输入而仍按未抵消伤害给Magic计价。

## 支付前沿与旧mask的关系

quoted分支确实**替代**旧mask条目，不是叠加。离线对同一Lesser Dog事件手，旧账本仅有`dust_actual_payment_savings`；添加一致的quotes与共同play caps后，新账本仅有`dust_quoted_payment_frontier`。

测试quote采用`gross=cost+0.5`、caps=[2,2]：direct=2G、unlock=0、total=2，外层只记`.45×.70×2=0.63`；没有再加direct、整手降费或完整生成身体。实现的分解恒等式也检查total=direct+unlock。

**默认`make_contexts()`有0个quoted context。** 因此默认Lesser Dog评分仍采用旧mask，前沿是显式报价面板下的可选能力，不能描述成已替换全部默认评分。CLI限制文字仍说“不估额外行动”，应限定为“无quotes的默认面板”；显式前沿能够估计调用方报价下的可支付净选项，但不估战斗、目标、格子或实际构筑最优策略。

后续为手牌提供quotes时，应使用gross收益且保留来源与共同时点。前沿内部已扣实际费用，外层只加净改进；不可再把同一批未来手牌身体或节省金币另加一次。

## 交付判断

当前版本可以按明确的“默认24情境条件部署诊断”范围交付。0攻击敌方行动、带防护敌方的Magic前处理应作为下一次泛化前的修复项。没有发现现有默认调用把Magic、关键词交换或支付前沿的收益重复累加。
