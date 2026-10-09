# 牌组与对局分析

按需使用：牌组审核、核心条件、资源转换、起手、解场／打脸、样本和玩家案例。以下是分析方法与快照案例，没有当前版本 tier list。

## 先检查牌表，再判断打法

核对 25 张、同名稀有度上限、法术 SOUL、TOKEN、Ranked 唯一 DT 位、神器的普通／传奇组合与可选标记。普通／闪卡同 ID 一起算；卡面数量未知或模式禁限未知时指出缺口。

然后寻找实际连接：

- **启动条件**：Need 检查哪个区域？Quest 要几次行动？是不同 ID、不同稀有度、已死亡牌还是持牌条件？必须保留 non-Generated 限定。
- **前期生存**：能实际打出的单位、即时解场、Taunt、治疗；不是只数低费牌。用先后手真实余额判断行动窗口。
- **资源转换**：G→场面、牺牲→Dust／任务、TOKEN→计数、死亡区→召回、污染敌库→后续伤害。关注手牌与四格容量。
- **终结方式**：持续场面、Charge／直伤、组合奖励、疲劳优势；长期资源很多不等于必然获胜。
- **失败状态**：核心未抽到、互相破坏条件、攒钱丢场面、过抽、满场、关键牌被沉默／捕获、花完 G 无法完成后续。

按用户目标给操作顺序与改牌理由，不把主题同名卡都塞进去，也不预设必须更换 SOUL。若需要推荐新环境牌组，再找带日期、作者和真实牌表的现行证据。

## 解场还是打脸

1. 先算本回合致胜与对方下回合致胜；把治疗、Taunt、Charge、保命、已见直伤加入估计。
2. 持续扩大资源的引擎通常比普通身材更需回应。不能因为攻击低就忽略它。
3. 杀敌且自己存活能保留下一次行动；Kindness 会提高这种交换价值。但 Dust、KR、Wanted 可以反转收益。
4. 对方大怪需要两只才能杀时，打脸可能更有利；若它有嘲讽、回血、反复攻击或组合能力，不能机械地放任。
5. 四格中留出召唤位，七张手牌中留出补牌空间，并预留 Program 等额外支出。

这些是决策检查，不是所有牌组的固定政策。玩家 burn／reach／initiative 用作伤害收尾与主动权的分析标签，不与正式 Burn 状态混同。

## 六副完整用户样本

用 `query.py deck --name <SOUL>` 获取完整牌表、张数、神器与卡面，来源／模式／战绩未知。

| 样本 | 资源路线与操作 | 关键限制 |
|---|---|---|
| BRAVERY | 小单位起场，Mystery Machine #502／Flameguy #812 牺牲友军换解场／抽牌；Lost Noelle #993 收集友方卡导致的死亡。Sandstorm #857 放在其他付费牌之后计算次数 | 牺牲前先兑现攻击／Support；别为任务牺牲最后的阻挡单位；G、格子、手牌都可能先耗尽 |
| DETERMINATION／Science | Science #12 开局的 3G TOKEN Blaster 满足 Berdly Plush #673／Berdlycoaster #671；TOKEN 投入换后续 Blaster。Tiny Tornado #667 击杀生成 Zephyr；先杀敌再用 Call for Help #702 复制该回合死亡敌怪 | Science 自己生成的 TOKEN 不增加其计数，但仍满足 Berdly 的持牌条件；Call for Help 预留格子。不是旧 Wiki 的复活己方一怪版本 |
| INTEGRITY | Investment #130 减费检索，Cloning #85 复制非 DT 生成基础 3/3＋Haste；Dust 单位积累死亡区，Crystal Tombstone #267 后期召回 | Cloning 是 Summon，不自动触发原怪 Magic。Golden Hit #257 花全部 G，再按溢出返还；先算目标 HP 与后续开支 |
| JUSTICE／全怪物 | 无初始法术满足 Bookshelf #466，以生成法术弥补法术包；Sheary #391 和高费怪物解场，Roaring Knight #935 收尾 | 生成法术不破坏“无非生成法术”条件；Justice 回合开始一伤改变受伤／精准击杀阈值；攒 20G 不保证能活到出 RK |
| PATIENCE／Starwalker | 没有 RARE／EPIC 初始牌，Starwalker #274 回库减费、Bird #297 抽三张、Aqua #970 检查当回合三次抽牌；Evil Plan #36 奖励打空手牌 | Draw 与 Add 分开；领取 Evil Plan 要在 Play 之后出现空手。前期全攒钱和后期大量生成都可能破坏启动 |
| PERSEVERANCE／双 Librarian | 仅 Librarian #185 两张重复，其余单张；抽出一张后剩余库已无重复，可满足手中 Librarian 的 Need；KR 支持交换与控制 | 不能把双 Librarian 直接视为矛盾；条件检查剩余库。原始重复牌送回库可能重新阻断，KR 需要识别实际击杀者 |

KINDNESS 样本只有 19 张：Kawkaw #990 加身材并麻痹，Cafe Table #641 清负面效果，Glitch #646 含 Disarmed 等多状态，存在组合方向，但缺六张，不能给完整牌组概率。MONSTER 空条目不证明可构筑第八职业。

## 有公开来源的玩家案例

以下材料补充“玩家如何考虑收益”，不是统计验证的推荐牌表。

### Kindness 场面进攻

2026-08-25 求助帖中，自称用所讨论牌组达到 Master 的玩家，起手找 2—3G 场面单位，利用治疗保留交换后的单位，再用强化、直伤、Charge 结束比赛。该原则针对其场面牌组，不直接迁移成控制套的无条件打脸表。[讨论](https://www.reddit.com/r/UnderCards/comments/1vyawau/i_seriously_need_help_winning_more_i_dont_even/)

### Spamton：死亡才是兑现

2026-09-20 牌组批评指出，Poster 缺法术、传奇太多、给 Pipis 加 HP，可能与污染目标脱节。Shop／Spamequin 供 Pipis，Pipis／Flying Heads 死亡污染，Cannon／Broken NEO 消耗污染收尾；楼主反馈修改后表现改善，未提供统计胜率。[讨论](https://www.reddit.com/r/UnderCards/comments/1wlfvof/i_would_like_to_know_your_thoughts_on_my_decks/)

本地 Pipis #753 死亡放两张 Hyperlink 到敌库顶，Poster #755 每次 Shock **一张**，不是评论声称的按法术费用投放。Shop #756 回合末 Program 再花 3G；Broken NEO #758 要敌库十张污染。引擎应同时计算死亡速度、余额和空格。

### Flowery／Need：条件限制有构筑成本

Firsty 的 2026-08-19 分析围绕可靠 Need 单位积累任务，然后获取带 Flowery Power 的资源。Seam 与 The Original 等条件会限制其他卡位；博客省略部分 non-Generated 限定，须用本地原文补回。[分析](https://thefirstyduelist.wordpress.com/2026/08/19/underground-strategy-report-mini-flowery/)

任务 #77 要六次条件成立的 Need Play，奖励取回已触发过的 Need 怪，放不下的入库。条件成立但没钱出牌、早期没有场面、手牌放不下奖励都可失败。Flowery Power 保证条件，不替玩家免费完成全部行动。

### Pink：削弱换进度，承担回合中自损

Firsty 的 2026-08-21 分析用 MMM 累积 Doki，优先削不依赖攻击或希望死亡的 Dust 怪，讨论 The Cure 的回合末清理。Pink 让 MMM 能指定敌人；Ghost 才有攻击削弱并复制敌怪的效果，博客一处写混。[分析](https://thefirstyduelist.wordpress.com/2026/08/21/underground-strategy-report-mini-pink/)

本地任务 #76 只在手里没有 MMM 时补一张，十五进度给 Ghost 并重置。回合末清理不能救回已经死亡的单位；不能把每次自损当作无代价。没有完整牌表和战绩证明。

## 慢速资源与快攻的适用模型

Soulless Kris #505 先用 Dark Fountain #34 达二十进度，奖励三张入库后变为 Dark World #65；后者二十计数，每张花两计数，内生奖励最多十张。这个很大的有限包不自动证明“无限资源”，循环要额外机制。

Royal Papyrus #716 的 Need 需要死亡区十个费用≥9G 的非生成怪，必须通过前期解场、治疗等活到进度完成，才能获得 Underground Army 资源。查 ID 对应快照，不从角色名猜卡号。社区对其“最强”和高段位占比的描述仅个人观察。[资源路线讨论](https://www.reddit.com/r/UnderCards/comments/1uk0v7g/what_is_strongest/)

Seam／Frog Zoo 玩家曾报告提前结束比赛更容易打慢速资源套；“十二回合前”是经验窗口，不是固定机制截止线。[经验帖](https://www.reddit.com/r/UnderCards/comments/1v2cg0b/new_player_advice/)

可采用“早期场面投资与后期引擎兑现的竞赛”来解释对局，但不能据几篇帖子产生当前环境胜率、占比或精确优劣表。
