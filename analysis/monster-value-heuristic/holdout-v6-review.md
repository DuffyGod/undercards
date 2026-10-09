# V6 holdout16 独立语义复核

日期：2026-10-08。只读审查 `annotation-runs/semantic-v6-holdout16/batch_000.json`～`batch_003.json` 与合并记录；未调用API、未重抽样，未修改schema、batch、主模型或价格文件。

## 工作确已执行；一致性失败另有含义

四个批次全部网络返回成功，`ok=true`，各有完整六条输出：4张requested＋两个重复探针。共24条观测、18张不同卡、16张非fewshot requested。结构校验 `invalid_tasks=[]`，`accepted_count=structurally_accepted_count=16`。

实际用量：prompt 71,733、completion 8,981、合计80,714 tokens。`all_batches_consistent=false`来自20探针的4种signature，**不是执行未启动、网络失败或16张没有输出**。49在四批中的signature一致。

审查发现：输出已经能提供不少可信的机制片段，但没有一张卡应仅凭 `parsed` 就自动获得完整定价许可。自然语言里正确保留的限定，经常没有进入typed字段；部分则是真实对象／条件错误。

## 实际模块覆盖

以下计数只针对16张requested，排除探针。统计的是生成的模块，不是全卡机制支持率，更不是实战触发次数。

| 维度 | 实际输出 |
|---|---|
| annotation_status | parsed 15，partial 1 |
| 模块总数 | 39 |
| 12类kind | damage 5；add 1；buff 7；combat 8；discount 3；copy 1；state_change 2；erase 1；summon 3；draw 6；kill 1；refund 1 |
| 9类trigger | magic 18；bullseye 3；passive 7；delay 1；support 3；shock 2；summon 1；dust 2；lose_dodge 2 |
| amount_basis | fixed 36；source_count 1；hand_size_after_play 1；ally_monster_count 1 |
| count_basis | fixed 38；source_count 1 |
|时点 | conditional 5；immediate 6；mixed 2；death 2；none 1 |

有实际结构证据的数量包括：434生成3个312；812抽2；其它draw模块的count通常1；757按实际event_erased数量除3取floor生成753；910按来源计数除2；984一次总伤害按打出后手数变化。658虽然使用了ally_monster_count，**缺Generated过滤，不能视作正确公式**。

target／recipient覆盖单个怪物、玩家、己／敌手牌、双方手牌、己／敌牌库、己方怪物、绑定输出集。但这些类型并非完全互换；下面的20探针和989正好证明了范围与对象误差。

## 20探针：这次有真实typed范围错误

| 批次 | recipient | condition_codes | unresolved | 分类 |
|---|---|---|---|---|
| 000 | targeted_monster | target_exists | 空 | typed收窄为怪物；额外条件标签变化 |
| 001 | other | 空 | 空 | 保留宽单目标，具体合法域来自ALL前提 |
| 002 | targeted_monster | 空 | 空 | typed收窄为怪物 |
| 003 | other | 空 | 英文ALL范围尚未枚举 | 额外重列已知K007疑问 |

四批均是damage2／magic／count1；金额和次数没有漂移。但 `recipient=targeted_monster` 按V6定义只能是所选怪物，排除玩家，而给定K007包含单个友敌怪物／玩家（排除触发本卡）。`target=other`和notes写宽目标，不能覆盖一个更具体且错误的recipient。

因此这次不能将所有分歧都解释为表述漂移：000／002是真实typed范围错误；003是已知规则疑问治理失败；target_exists标签差别是结构性条件标签漂移。不能直接通过合并signature将targeted_monster与other当同义词。

修正应依据ALL前提作具名、可追溯纠正或语义隔离，不靠再次抽样多数投票。未来可给宽单目标一个明确recipient，而不是让other同时承担“已知多域”与“完全未知对象”。本次审查未修改任何记录。

## 16张非fewshot逐条完整性审查

| 批次／ID | 可相信并录入的片段 | 仍须补充／隔离的限定 |
|---|---|---|
| 000／833 | Magic与Bullseye各有敌怪2伤害＋玩家1伤害，共4模块；没有把两个触发互相替代 | 最低HP选择器仅condition，不能选最有利敌怪。notes称Bullseye要求“这2DMG”精确击杀，将触发来源收窄；Bullseye奖励不只因其2点Magic触发，普通攻击造成精确击杀也不能排除。timing只conditional遗漏即时部分，应mixed |
| 000／434 | 左分支Add3／ref312，右分支+1/+1；amount=null/count3避免先前数量乘9；左右分支guards互斥正确 | 右分支card_ref=null、recipient=other，仅evidence／notes保留“全部Ponman、手与场”；过滤与区域联合集合未typed，不能给所有友军增益 |
| 000／989 | COST−3、ATK−3、HP−3分别保留，比V5漏费用改善；复制source=targeted_monster而非主体 | **Delay guard=actor_survives错误**：“it”指Magic所选目标，主体死亡／离场不应自动取消Delay。HP最低1只在notes，未typed clamp；non-DT只有condition。复制目标身份与跨区保存仍有合理疑问，partial正确，但guard错误仍需纠正 |
| 000／909 | Support+2/+2、Support关闭0、Shock重开1都完整，trigger及state_key正确。这是未见文本上的实质迁移改善 | silence=future遗漏已经获得的自身+2/+2可被删除，应含body。触发量与时点可录入，不能据此估计平均多次触发 |
| 001／757 | ref665擦除；实际event_erased(a)除3、floor产生753；输出Charge绑b。数量依赖与输出修饰正确 | count=9是上限，不是实际擦除数量；cap-mode与匹配可用量仍未typed。须根据实际成功擦除数量给event_erased，不能直接按9推导保证召唤3个 |
| 001／899 | 基础抽1，ATK-buff guard再抽1，HP-buff guard给主体Darkspawn。两条件与受益主体正确 | draw recipient=player_self与hand_self存在约定漂移但拥有者方向清楚。body_and_future不能被解释为本卡提供额外ATK／HP增益；那些buff是外部前置状态，此卡自己只授予Darkspawn |
| 001／812 | kill友军目标＋draw2，效果代价没有再被unknown丢失；两项数量正确 | 两模块均无成功依赖，不能在无友军／未完成kill时自动抽2。需要同事件目标／成功条件绑定，防止只加抽牌收益，不扣牺牲身体。notes提overkill不重要，不能替代代价条件 |
| 001／153 | 触发确为summon，抽1，future暴露正确 | **手牌≤5门遗漏**：branch_guard与condition都空，hand_size仅卡级标签，typed执行会无条件抽。必须补当前手数阈值，不得认为summon事件本身保证条件成立 |
| 002／910 | 来源dustpile、每2个分组floor、+1/+1、自身Haste均已表达，优于非法basis的V5 | `unique COST`直接选distinct_cost，没有独立裁定：distinct费用种数与只出现一次费用可能不同，需确认含义。来源还缺“怪物”过滤，不能统计dustpile所有法术。不能以parsed作正确公式许可 |
| 002／112 | Dust、1个Ice、ref10、对方方向正确 | recipient=player_opponent表示接收拥有者而非棋盘集合，和enemy_monsters需要统一kind兼容解释；不能因此加入己方。召唤收益要扣对方身体及其能力，不能只看主体6/9 |
| 002／908 | Support draw最多1、Shock给牌库减费−1，事件分类比V5 magic错误改善 | “up to1”是选择性上限，typed count1尚没有可选模式。牌库顶怪选择器没有typed，不能给全牌库降费或降下一张任意牌；平均兑现需要实际后续使用 |
| 002／683 | LoseDodge触发抽1；+2/+2明确绑定draw输出b，修复V5遗漏 | “抽Plug”过滤只在原文，输出未typed过滤；Dodge(1)模块amount=null，次数只有evidence。可录入失去Dodge→抽后增益的联动，不能自行认定抽任意牌或Dodge任意次数 |
| 003／984 | 打出后手数×1、单次伤害、Bullseye召唤ref375、future暴露及精确击杀条件正确 | **明确ATK2／HP3覆盖遗漏**：ref375印刷1/1不代表召唤仍1/1。卡面明确指定2/3，不是需要随机解释的疑问，应为输出stat_set ATK2／HP3；当前输出只保留ref并反而列规则不明。不能按1/1给价 |
| 003／846 | −4COST，Dust，recipient=hand_both，已正确识别双边收益；最高费用并列疑问可具名保留 | 每侧最高费用选择器只有notes/evidence；hand_both不能按“双方所有牌各降4费”执行。对方收益仍须反向计，不是固定自己的4G收益 |
| 003／658 | Haste、Magic Earn GOLD乘数1、玩家收入方向准确，future暴露考虑Haste | **Generated过滤遗漏**：ally_monster_count统计所有友军，与“Generated ally”不同。notes写过滤不修复typed公式。是否包含Generated的主体已有allycount包含主体的前提，不能只因自身份不明重复列规则疑问；Generated身份应是状态输入 |
| 003／985 | Taunt、持续buff+2/+2、future光环暴露较V5 body误写改善 | **相邻＋Plant过滤未typed**：friendly_monsters会给全部友军收益。timing=none与存在能力的约定冲突，不能据此当空白文本。光环生命周期疑问需规则资料查核，但绝不能将它执行为永久全体Magic增益 |

## 什么可以作为可信录入依据

**可以入机制账本但仍保留原文审核链接的部分：**

- 已明确的固定数值与方向，例如909+2/+2、846−4、989三项−3、833的2＋1；这些不是Gold价格。
- Support／Shock／Summon／LoseDodge的named trigger提取，以及909的关闭／重开门状态。
- 757实际擦除事件→分组召唤→输出Charge，683抽到输出→+2/+2这类明确前序联动。
- 双边手牌846、对方召唤112的方向；使用时仍需选择器和对方收益账本。
- 984的手数总伤害公式；召唤2/3限定还必须补齐。

**只能作为人审线索、不能直接执行或发布卡牌完整分数的部分：**

- targeted_monster与宽单目标混用、actor与所选目标存活混用。
- 区域＋过滤＋选择器：Ponman／Plant／Generated／Plug／怪物类型、最高／最低／正前方／牌库顶。
- 上限与可选数量：up to9擦除、up to1抽牌；实际成功计数与意图计数必须分开。
- 魔法多步骤的成功代价条件、HP最低值、召唤覆盖属性、base/current字段与跨区身份。
- 未独立裁定的unique COST，以及不应重列未知的明确召唤指定身材。

这些是规范与提取的边界，不要求搭建完整游戏模拟器。最小补充可以是固定过滤器、选择器、数量模式、guard主体和输出属性覆盖；主模型仍自己按统一标准定价。

## 后续处理建议

1. 先集中纠正明确错误：20范围、989guard主体、153手数门、658Generated过滤、9842/3覆写。保留原始输出与修改理由。
2. 对其余结构缺口设置模块级执行支持状态，而不是丢掉整个卡面或让自然语言fallback默认执行全体。
3. 使用这16张冻结未见样本作为下一规范的确定性回归；不要重跑来掩盖失败，不按任何卡牌预期排名拟合。
4. 请求成功、结构通过、探针一致、语义完整、执行器支持和价格可靠分别报告。此次前两项已经完成，后几项不能合并成一个consistency布尔值。
5. 本审查没有输出自由Gold分数，也没有更改schema或API程序。AI结果用于减轻文本机制录入负担，不能自行提供权重、报价或可兑现概率。
