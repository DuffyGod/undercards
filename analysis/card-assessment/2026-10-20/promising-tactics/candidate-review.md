# 16 张新增潜力怪物：可直接实现的打法端点

日期：2026-10-20。来源为仓库内 [snapshot.json](../../../../skills/undercards/references/snapshot.json)，整理日期 2026-10-05、线上版本未知。以下 16 张均为 `ordinary_non_token` 怪物，均不在本任务开始时的 49 个 PROFILES 中。只筛选能给出具体动作、数字和失败条件的候选；没有调用 DeepSeek、运行旧实验或修改主程序。印刷文本逐字摘自 `effect_readable`。

优先不是再做一套全池模拟器，而是把下列可达路径写成端点：固定金币/手牌/位置，保存动作顺序、己敌残体、实际英雄回复、实际消耗卡牌及尚需付费的回收牌。所有普通战斗目标默认无 Armor/Dodge/Taunt/Dust；单独写出的防御反事实例外。英雄不处于任一中间步骤的致死边界，额外 Draw 有足够牌库、手牌空间；新增怪物有合法空格。未确认的致死触发与溢出生成不纳入确定结果。

## 第一优先：同样资源，仅顺序/目标就能改变结果

### 1. Sheary #391｜6G，5/5，BASE

`Magic: Deal 1 DMG to a monster. If it's damaged, deal 4 DMG instead.`

**可实现路线**：己方有 7G，手有 Loox #7 与 Sheary，敌方普通 7/5 满血。先 1G Loox 对敌人打 1，令其变为受伤的 7/4；再付 6G Sheary 打 4，敌怪死亡。终点新增 Loox 1/2、Sheary 5/5，支付 7G、用两张牌、移除一个 7/5。

**同根反序**：先 Sheary 对满血目标只打 1，再 Loox 打 1，敌方仍是 7/3；金币、出牌数和两个新身体完全相同。此差值直接来自预先制造 damaged，而非免费借用额外伤害。`instead` 不应实现成先打 1 再因受伤补 4。

**携带倾向与反例**：己方本来就有廉价补伤或 ready 小怪时值得优先比较；没有准备手段、环境目标多数满血时不能当通用 4 伤体。记录目标当前/最大 HP、准备动作费用、Sheary 实际伤害、完整终点；普通目标即可先验证。

### 2. Pancakes #868｜5G，4/5，COMMON

`Magic: Fully heal a monster and heal the same amount of HP to you.`

**可实现路线**：己英雄 20 HP，有 ready 的 6 攻、当前/最大 8/8 HP 友军；敌方 3/5。先用友军攻击并击杀敌人，自己变 6/5；再出 Pancakes 恢复友军 3 HP、英雄恢复 3 至 23。终点旧友军 6/8、新 Pancakes 4/5、敌怪死亡，支付 5G。

**同根反序**：先在满血友军上治疗，实际恢复 0；再攻击，终点旧友军 6/5、英雄仍 20。两序差为旧友军多 3 HP 与英雄多 3 HP。若回击达到 8，旧友军已经死亡，不能拿“完全治疗”复活它。

**携带倾向与反例**：有厚血大体可反复交换且英雄也需要回复时优先；全是易被一击杀死的小体、或英雄/怪物经常满血时不优先。先用普通在场友军，Magic 不能指定刚触发它的 Pancakes 自己。记录实际缺血，不按最大 HP 全额给英雄回血。

### 3. Shyren's Agent #437｜7G，5/7，COMMON

`Magic: Heal 7 HP to a damaged ally monster. Excess healing is dealt as DMG to the monster in front of this.`

**直接路线**：已有友军仅缺 1 HP。将 Agent 放在敌方普通 6/6 正对格，选该受伤友军：恢复 1，溢出 6 打死正前方敌人，留下 Agent 5/7。伤害落点是 **Agent 正前方**，不是被治疗者正前方。

**可主动准备的 8G 路线**：原友军满血且 HP>1，先 1G Loox 对它打 1；Loox 因命中友军得到 +1 ATK，成为 2/2。再按前述位置出 7G Agent，治疗 1、溢出 6。完整终点是旧友军回满、Loox 2/2、Agent 5/7、敌 6/6 消失；两张牌、两个新增格子、总支付 8G，不能只报 Agent 单卡 7G 效率。

**边界与反例**：受伤友军缺 7 HP 时无溢出；满血友军不是卡面要求的合法 damaged 目标。正对格无敌人或被 Armor/Dodge 防住时，溢出不能改射最有利目标。记录缺血 d、有效恢复 `min(7,d)`、溢出 `max(0,7-d)`、对位与防御后的伤害。这个家族可以立即量化“少量受伤目标有时比重伤目标更适合解场”。

### 4. Ambyu-Lance #654｜6G，5/7，RARE

`Magic: If you have less than 15 HP, gain +1 ATK and Haste. If you have less than 10 HP, gain Candy and Taunt.`

**可实现顺序**：选不提供怪物治疗的 SOUL 作基准。英雄 9 HP，9G，手中 Lance 与 Shyren #22（3G 2/4，`Magic: Heal 4 HP.`），敌方普通 3/6。先 Lance，获得 6/7、Haste、Candy、Taunt，攻击杀敌后剩 4 HP；再 Shyren 给英雄回复 4 至 13。己末 Candy 治疗 Lance 3，回到 6/7。

**同根反序**：先 Shyren 把英雄回到 13，再 Lance，仍获得 +1 ATK/Haste，但没有 Candy/Taunt。攻击同一 3/6 后剩 6/4，己末无 Candy。两序都付 9G、两张卡、英雄最终 13，只有顺序改变了防御状态与怪物有效回复。

**反例与参数**：15 HP 不满足第一条件，14 才满足；10 HP 不满足第二条件，9 才满足。不能为了触发条件无代价卖血；也不能把已获状态误写成英雄后来回到 15 就自动丢失。记录入场时英雄 HP、随后回复时点、攻击后的损血与 Candy 实际治疗。优先比较低血回场/回复混合构成，不把低血状态本身当好处。

### 5. Mantis Dancer #964｜6G，3/7，COMMON

`Magic: Deal 3 DMG. If it kills, cast Carousel [#458].`

引用 Carousel 精确文本：`Deal 1 DMG to all monsters. If any died, repeat.` 这不是免费增加 4G 支付，Mantis 的 Magic 是代施放效果；只记录实际 6G。

**目标选择路线**：己方已有 2/2，敌方四个普通怪，当前 HP 从左到右为 **3、1、2、3**（攻击力不影响这里的非战斗群伤）。出 Mantis，用 3 伤杀第一个 3 HP 目标；留下 1→2→3 的死亡阶梯。Carousel 第 1、2、3 轮依次有敌怪死亡，己方 2/2 在第 2 轮也死；第 4 轮无人死亡才停止。终点敌方全清，旧友军死亡，Mantis 自己也被打 4 次，只剩 **3/3**。

**同根坏目标**：先杀唯一的 1 HP 目标，剩下 3、2、3 HP；Carousel 第 1 轮无人死亡，立即停。终点敌方 HP 为 2、1、2，旧友军 2/1，Mantis 3/6。不能把“触发了 Carousel”一概报价成清场。

**边界与参数**：检查每轮致死后是否再打一轮，不能在最后一个敌人死时提前停；己方与新 Mantis 一样承受群伤。先支持无 Dust、无复杂防御目标，再加单独 Armor/Dodge。保存每一轮包数与死亡集合，便于手算复核。目标选法、原生命阶梯与己方代价已经足以产生有意义的打法比较。

### 6. Searby #852｜7G，5/4，EPIC

`Magic: Deal 5 DMG to the monster in front of this. Bullseye: Draw a card with -2 COST.`

**可实现路线**：敌方正对位置有 6 HP 普通怪，先 1G Loox 对其打 1，再在相应位置出 7G Searby，恰好造成剩余 5 伤击杀，抽 1 张并给其 -2 COST。总付 8G，新增 Loox 1/2、Searby 5/4，额外留存 1 张折扣牌；后续真的打出该牌时才兑现其实际省费。

**反例**：目标原本 4 HP，5 伤虽然击杀，却不是 Bullseye；不能领抽牌。Armor 使 5 点输入实际减为 4，原 5 HP 不再能恰杀，原 4 HP 才可能恰杀。不能任意选择不在正前方的敌怪。

**可量化量**：位置、结算后的恰 0 HP、有效抽牌与手限、折扣牌原费和真正下一支付。抽到后尚未使用的 -2 COST 不是已经到账的 2G；禁止同时把“已使用折扣牌效果”和完整手牌价值重复计价。它无 Haste，不追加本体即时攻击。

## 第二优先：立即回场与回复可以按实物端点比较

### 7. MTT Fountain #163｜5G，2/5，COMMON

`Haste. After this takes DMG, heal the DMG taken as HP to you.`

**路线**：英雄 20，敌 4/2。Fountain 入场攻击，杀敌、自己剩 1 HP，同时把实际承受的 4 点恢复给英雄，英雄至 24。端点只有一个 2/1 残体；不能同时保留 2/5 原体和“承受伤害收益”。

**反例**：敌人改为 4/3，2 ATK 杀不掉；治疗并不解决留下的高攻威胁。遭遇 Erase/直接 Kill 不等于承受 DMG。互相致死时“After takes DMG”是否仍触发、过量伤害如何统计需另证；第一批只做非致死伤害实例。与 Knight Knight 比较时注意：这里回英雄，Knight 回自己；Fountain 受到敌方伤害也在文字范围内，不只主动攻击。

**参数化**：每个实际受伤包、怪物当前/最大 HP、英雄缺血、是否仍活着、杀敌是否成立。适合英雄回复缺口大且对手存在≤2 HP 目标的世界，不作为通用大攻击解法。

### 8. Dancer Mettaton #201｜7G，4/7，EPIC

`Haste. After this attacks and kills a monster, heal 4 HP to you and summon a Mettabot [#359].`

Mettabot #359 是 **1/1、Haste**；由效果召唤不另付印刷 1G。

**路线**：英雄 20、没有其他友军、敌方 3/4 与 1/1。Dancer 打死 3/4，剩 4/4，英雄回至 24；生成 Mettabot 后，用它撞剩下的 1/1，双方死。终点仅 Dancer 4/4、敌方全清、英雄实际治疗 4、支付 7G。若不使用 Mettabot，终点是两个身体、仍留对方 1/1；两条合法动作都保留。

**反例与边界**：敌目标变 3/5，第一击不杀，治疗和 Mettabot 都不触发。死亡同归时是否还能执行攻击后奖励另留置；首批限制 Dancer 回击后存活。满场生成规则未知，路线要求攻击后至少一个空格。不要在已让 Mettabot 送掉时还保留它的身体价。

**参数化**：4 ATK 击杀阈值、反击后 HP、有效治疗、生成空格、Mettabot 可即时处理的 1 HP 目标与最终去向。比“7G 4/7+固定奖励”更能解释实际回场竞争力。

### 9. Baking Queen #579｜10G，6/6，LEGENDARY

`Magic: Kill a damaged monster. Heal HP to you equal to its ATK.`

**路线**：英雄 20，敌方满血普通 8/8。先 Loox 打 1，再 Queen 对受伤 8/7 施放 Kill，英雄回 8 至 28。总付 11G、两牌、留下 1/2 与 6/6；若场上已有其他合法伤害准备，Queen 的增量支付才是 10G。

**反例**：不能对原满血敌人无准备直接 Kill。相同受伤程度、目标攻击改为 1，则只能回复 1；英雄已 29 时，即使杀 8 ATK 怪也只有效回复 1。可选友军不意味着牺牲免费，若杀友军须扣该身体和其他服务。直接 Kill 不依赖 Armor/Dodge，但 Dust 照常可能触发；第一批用普通目标。

**参数化**：damaged 标记、准备成本、目标击杀前 ATK、英雄实际缺血、目标 Dust、10G 的机会窗口。适合高攻厚体与生命压力同时出现的条件，不以“高费怪价值高”替代这些条件。

### 10. Clover Hydra #266｜9G，3/3，EPIC

`Haste. Magic: Deal 3 DMG, draw 3 cards, and heal 3 HP to you.`

**路线**：英雄 20、敌普通 2/6，出牌前 4 手、至少剩 3 张库牌。Magic 对敌打 3、抽 3、英雄回 3 至 23；再用 Haste 的 3 ATK 补死剩 3 HP，自己剩 1 HP。终点 3/1、敌消失、额外三张确实入手，支付 9G；手牌从 4 经出牌降 3 再升 6。

**反例**：把敌 ATK 改为 3，补刀后自己也死，不能继续保留 3/3 身体；Magic 已兑现的抽牌与回复不因此变没。出牌前 6 手则只能装 2 张，第三张过抽；空库致死与三项效果的中断顺序不在首批确定路线中。

**参数化**：3+3 击杀线、Haste 回击存活、3 次实际入手/过抽、英雄有效治疗和剩余金币。多用途叠加可能很强，但只有 3 HP，本体交换风险必须与资源收益共同入账。

### 11. Knightdyne #892｜9G，5/7，EPIC

`Magic: Deal 1 DMG to the lowest HP enemy monster 4 times. For each enemy killed, summon a base ATK 2/HP 3 Spear [#574] with Taunt.`

**路线**：己方空场，敌普通 3/1、2/1、1/1。前三包各杀一个，生成三只 2/3 Taunt；第四包没有敌人，不再生成额外东西。终点 Knightdyne 5/7 加三 Spear，占满四格，敌方全清，支付 9G。与 Undyne 不同：这里按击杀数生体，**无目标余包不转为更大的 Spear**。

**防御反例**：敌方为 1/1 Armor、2/2、3/3，最低血 Armor 单位会把每包 1 都减为 0，连续四包可以全部被吸住，没击杀、没 Spear。移除该 Armor，则可杀 1 HP 及 2 HP 两只，最后一包使 3 HP 敌怪剩 2，生成两只 Spear。

**参数化与边界**：每包最低 HP 目标、击杀集合、可用格数、实际生成数。初批最多需要三只 Spear；四次击杀会溢出四格上限，必须标为未决而非静默截断。最低血并列而结果不等价时保存分支；上面三只一血都会被杀，次序不影响终点。

## 第三优先：回收、攻击免伤和延迟重建

### 12. G Machine #609｜6G，5/5，EPIC

`Taunt. Haste. Delay: If this is dead, add a Gaster Blaster [#351] to your hand.`

**路线**：Haste 撞普通 5/5，互死；同一回合 Delay 给手中一张 Gaster Blaster。端点自己无 Machine、敌方无目标、持有一张回收牌，支付 6G。Delay 不要求原体继续在场。

**反例**：敌方改为 4/5，Machine 杀敌后剩 1 HP，Delay 时未死就没有回收；这不是活体+奖励都领。回收牌精确为 **4G 法术，`Deal 8 DMG to a monster or you.`**，不能打敌英雄，也不能把它当已兑现的 8 点伤害/4G 现金；再次使用需支付 4G。

**参数化与歧义**：目标 A/H 决定主动死亡、手中剩余容量、Delay 时是否真死、回收牌的下一目标与支付。首批要求手有空位，满手 Add 的统一规则尚未确认；Erase/回手不能自动登记为 dead。

### 13. Cool Papyrus #254｜9G，6/9，LEGENDARY

`Haste. After this attacks and kills a non-DT monster, add a base COST 3/ATK 4/HP 5 copy of it to your hand.`

**路线**：攻击普通无能力的 5/6，击杀后本体剩 6/4，拿到已知 3G 4/5 副本。9G 端点是“6/4 + 一张有再次支付要求的牌”；若还有 3G 并实际打出副本，12G 端点是“6/4 + 4/5”，不再同时计那张手牌。两种都可交给同一账本。

**反例**：目标血改为 7，不能一击杀，奖励不来；目标为 DT 即使死也不复制。首批限制回击<9 以避免互死触发时序。普通副本没有额外能力；复制有能力目标时，应分别保留复制能力与新基础身材的关系，不偷换为原大体原费。

**参数化**：非 DT 身份、6 ATK 击杀、剩余 HP、手牌容量、奖励牌身份、下一次 3G 支付/格子。适合连续资源交换，不应只拿一张通用牌价宣称回收的全部质量都已解决。

### 14. Martlet #880｜8G，5/7，LEGENDARY

`Magic: Switch: Deal [左侧] 7 DMG to the monster in front or [右侧] 1 DMG to all enemies and gain Haste. Bullseye: If this is alive, return to your hand with -1 base COST.`

**左侧精确线**：对正前方普通 7 HP 目标，7 伤恰杀、Martlet 活着返回手、base COST 变 7；终点不保留 5/7。改成 6 HP，仍击杀但不恰杀，不触发这一回收，5/7 留场。目标多 1 HP 反而切换留场/回手形态，不能按杀敌数给固定奖励。

**右侧精确线**：敌普通 2/6，群伤 1 后剩 5，Haste 攻击恰杀，Martlet 承受 2 后仍活着，触发回手减费；若目标改为 2/7，则群伤后剩 6，5 ATK 只打到 1，不恰杀、自己剩 5/5 留场。需要保留两种路线，左右合法落点不能随意改。

**边界**：多目标群伤同时产生多个 Bullseye 的回手/减费队列未确认，首批不要给它累计多次 -1。低血英雄被右侧 1 伤致死也会引入中断，先排除。记录真实 return、唯一新手牌实体与 base COST，不同时保留身体。

### 15. Trashy #632｜4G，2/5，RARE

`This has +2 ATK on the enemy turn and takes no DMG while attacking.`

**后续主动路线**：已经存活到可攻击窗口的 Trashy 对普通 10/2 发起攻击，杀敌且自己完全不受反击，仍 2/5。不是 10 点敌攻一律无效，而是仅在 **自己攻击期间** 免伤。目标改成 10/3，则没杀掉；若它下一敌回合攻击回来，Trashy 可以正常承受致死伤害。

**阶段反例**：该牌没有 Haste，部署当回合不能生成上述主动清理路线。敌方回合它有 4 ATK，己方回合只有 2；不能选有利数字把它当“永远 4/5、攻击又免伤”。与低攻厚体对比时，要同时记录两个相位的实际 ATK。

**参数化**：当前所属回合、ready、目标 HP≤2、主动攻击时实际免除伤害、敌回合反击 ATK=4、是否活到窗口。适合可主动整理尾血的构成；缺补伤又面对高血怪时不能靠免伤解决击杀。

### 16. Trial Ralsei #975｜7G，5/4，EPIC

`Delay: Summon a ATK 3/HP 3 copy of all non-DT ally monsters that died this turn.`

**路线**：本回合开始有 ready 的普通非 DT 6/2、2/2，敌方普通 2/6、2/2。两个友军分别主动交换、双方各死两只；然后才出 Trial Ralsei。己末 Delay 仍检查“本回合死亡”，生成两只 3/3 副本。终点 Ralsei 5/4 加两只 3/3，敌方空，支付本次新牌 7G；旧两友军的消失必须从 own_before 扣除。

**反事实与顺序**：相同死亡若发生在上一敌回合，不属于“this turn”，本次不补回。可以先交换再打 Ralsei，避免把“本回合死过”误实现成“打出后才开始计数”；本体不赋 Haste，生成的普通副本也不能当作已打出带 Magic。若原目标有能力，副本能力要另审。

**边界与参数**：保存当回合死亡实体、是否非 DT、生成时空位、每个副本身份及 3/3 基础。路线最多三次普通死亡且留足格；更大复活集合的满场规则不猜。Delay 在本体离场后仍会执行是通用文字规则，但本体死亡是否加入自己的复活集合可另设分支；首批让 Ralsei 活着，避免靠此歧义造强度。

## 交付优先级与最小实现合同

先实现 **Sheary 顺序、Pancakes 先交换、Agent 缺 1 HP 溢伤、Lance 先锁状态、Mantis 目标选择、Searby 恰杀** 六组。这些不依赖新概率标注，且每组都已经给出同资源反序/反目标；可以快速输出“同一手牌更好打法到底多保留了哪些资产”，而非继续罗列优缺点。

然后实现 Dancer、Queen、Hydra、Knightdyne 四个即时端点，最后接入回手/延迟/后续存活类。每条记录至少存：`source_text`、金币/手牌/位置前提、`actions`、`valuation_stage`、双方 before/after、实际治疗、留存牌实体、实际额外支付、未定价能力和裁定分支。多卡路线必须包含所有新卡费用与手牌承诺；保留实体奖励时只记其可兑现资源价，奖励真正出场后改记身体与已支付费用，二者不能双计。

本报告没有给未知机会分布填数。若只有某种局面赚，携带建议应继续写为该窗口联合兑现率与持牌/构筑替代成本的门槛；具体更好打法则可以先用上面的确定端点比较交付。
