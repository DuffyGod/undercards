# 来源、版本与未知规则

本 Skill 是 2026-10-05 整理的便携知识包，不连接游戏服务器。参考来源可以追溯，社区规则与策略的证据级别保留。

## 本地来源

| 文件 | 提供的信息 | 边界 |
|---|---|---|
| data.json | 卡名／卡面、SOUL、关键词、状态、附魔、教学规则 | 文本不等于服务器事件代码；部分旧词条和特殊模式文本仍存在 |
| collection.json | 928 个 ID 的费用、攻防、牌型、稀有度、SOUL、系列、种族、状态 | 外层 collection 是 JSON 字符串；普通／闪卡各一份；quantity 不是构筑上限 |
| deck_sample.json | 八个牌组条目、79 个神器元数据、44 个神器列表条目 | 来源、模式、战绩未知；44 个列表不能仅凭名称断言是玩家持有或当前全部合法池 |
| survey.md | 用户提供的初步网络调研，作为核对线索 | 有旧 SOUL、版本混用、过强环境判断；不直接复制为规则权威 |

便携包 snapshot.json 保留关键记录与来源定位，移除持有量／闪卡冗余和网站剧情。其 provenance 中保存输入文件哈希；哈希对应原始输入文件，不宣称是官方发布校验值。

## 采用三层结论

1. **文本／元数据确认**：明确写在用户快照中，例如 4 格、7 手牌、当前 SOUL、Shock 的 After 与基础费条件。
2. **外部核对**：Wiki 规则或具名玩家解释，尤其初始 1G／留存、Ranked 一张 DT；注明没有当前实测。
3. **推导／未知**：操作建议、Integrity 11G 的具体实现、左右格公式、事件队列。避免用“官方确认”“实测必胜”等措辞。

冲突按**内容所属版本**处理：新的明确卡面优先于旧攻略；较旧官方补丁不自动覆盖更新卡面。用户提供现行实战证据后，可修订对应判断。

## 网络核对及明确冲突

| 来源 | 可采用 | 限制 |
|---|---|---|
| [Welcome](https://undercards.fandom.com/wiki/Welcome%21) | 起手三张、开局 1G、金币留存及回合收入解释 | 同页有旧 SOUL／段位，不能整页搬作当前规则 |
| [金币讨论](https://www.reddit.com/r/UnderCards/comments/1k3rcma/what_is_going_on_with_gold/) | 初始 1G 与第一回合收入分开；后手前九回合奇数补偿；第三回合 7／9 算例 | 2025-04-20 社区回答，不是当前服务器代码 |
| [DT 分类](https://undercards.fandom.com/wiki/Category%3ADT) | Ranked 总计一张 DT；不同模式限制有区别 | 列出的卡池可能旧；当前数量用本地快照 |
| [Abilities](https://undercards.fandom.com/wiki/Abilities) | Play／Summon、Turbo 过抽、效果代施法不触发 Shock 等补充 | Shock 时序旧，Transparency 与 Invulnerable 交互也只有 Wiki 证据 |
| [Version History](https://undercards.fandom.com/wiki/Version_History) | 转录 106.0，2025-04-30 将时限改 90 秒、Shock 改法术完成后 | 本次未直接取得官方该季原文；不等于验证特殊模式或后续所有变化 |
| [官网](https://undercards.net/)／[Updates](https://undercards.net/gameUpdates.jsp) | 核对时首页索引有 Season 123，Updates 索引有 Season 122 | 搜索缓存版本不同；不能由横幅推断用户快照季号 |

例：122 缓存的 Susie's Apron 是每四回合两个空敌格，本地 #78 是每三回合一个空敌格。保留版本差异，当前包采用用户快照。Wiki 的 Call for Help、Will to Fight、The Vessel 等卡面也不适合无核对覆盖本地数据。

survey 中 Bravery 低手牌额外补给、Perseverance 攻击施 KR、Justice 回合末随机伤害等不符合本地 SOUL；本 Skill 已使用本地定义。Spamton Poster 按法术费投放污染的评论不符合本地每 Shock 一张。Soulless Kris 的内生奖励有限；玩家意见不支持总体 tier list。

## 无账号 Discord 的访问范围

只定位了 [官方邀请](https://discord.com/invite/wVmCQk6)，没有取得频道历史或置顶。TrueHub 有 [公开玩家提及](https://www.reddit.com/r/UnderCards/comments/1k2iv4l/)，未读取其消息或当前牌表。不得声称本 Skill 基于 Discord 内部共识；Skill 本身也不意味着加入社群或对外发送消息的授权。

## 仍需专门裁定／实测的项目

- 当前服务器发 G、首回合完整流程、Integrity 11G 的执行时点、潜在余额数值上限。
- 同时死亡／同时致死、各种开始／结束触发器的队列；精确伤害和状态应用顺序。
- 满手 Add、满场 Summon、Catch 释放失败，手牌重排及返回牌库的全部字段保存。
- Silence 对基础修改、Copy／Exact copy、强制攻击与 Disarmed 的交互。
- Transparency 是否取消 Invulnerable；Turbo 过抽、效果代施法 Shock 的现行例外。
- 总回合上限、平局、特殊模式差异，当前模式的额外禁限。
- 现行环境使用率、胜率、可靠完整牌表；只掌握若干具名经验。

用户只要普通解释或基础分析时，不必为了这些边界重新搜索所有资料；涉及边界时才定向核对。制作模拟器必须明确假设，不能把缺口静默填成其他卡牌游戏的规则。
