---
name: undercards
description: Explain Undercards gameplay and analyze its cards, deck construction, resource economy, and tactical decisions using a bundled rules and card snapshot. Use for Undercards questions, deck reviews, or game-state reasoning; distinguish verified text from unresolved rulings and current-meta claims.
---

# Undercards 玩法与分析

使用本 Skill 快速建立 Undercards 的对战模型，按需查询具体卡牌和裁定。解释默认使用用户的语言；英文卡名、SOUL、关键词及 ID 保持可检索。资料整理于 **2026-10-05**，对应用户提供的数据快照，**不是自动同步的线上规则库**。

## 首先掌握的游戏模型

- 双人回合制卡牌对战，通常双方初始 **30 HP**，将对方降至 0 获胜；Determination 等效果可能阻止第一次死亡。
- 构筑：**25 张牌 + 1 个 SOUL + 2 个普通神器或 1 个传奇神器**。BASE／COMMON／RARE 同名最多 3，EPIC 最多 2，LEGENDARY／DT 同名最多 1；Wiki 另确认 **Ranked 整副最多 1 张 DT**。
- 怪物共享，初始法术限所选 SOUL；局中可以获得其他 SOUL 法术。TOKEN 通常不能初始构筑；Generated 表示本局未从初始牌组开始，二者独立。
- 每侧棋盘 **4 格**，手牌上限 **7**，有序牌库、有序手牌、独立 dustpile。满手抽牌会 Erase；空库抽牌产生递增疲劳 **1、2、3……**。
- 回合骨架：开始领取 G／抽牌／开始效果 → 自行安排出牌与攻击 → 结束效果 → 对方回合。细节队列未确认，不能据此编造完整结算顺序。
- 通常怪物入场当回合不能攻击，通常每回合自主攻击一次；可选择敌怪或玩家，**不是四条固定对攻通道**。怪物交战相互按 ATK 造成伤害，HP≤0 死亡。Taunt 限制怪物攻击，Charge 可立刻打玩家，Haste 只能立刻打怪物。法术目标按文字判断。

## 金币：新增收入与余额分开

双方开局各有 **1G**，未花掉的 G 跨回合保留。n 是玩家**自己的回合序号**。

| n | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 起 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 先手本次新增 G | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| 后手本次新增 G | 2 | 2 | 4 | 4 | 6 | 6 | 8 | 8 | 10 | 10 |

即先手 `min(n,10)`，后手仅在 n=1、3、5、7、9 多领 1G。无支出、无额外效果时，首回合余额 **2／3G**，第三回合 **7／9G**。10 限制基础回合收入，不限制余额；攒钱可以打高于 10G 的牌。

收入表有本地教程支持；初始 1G／留存／累计算例经 Wiki 与玩家说明交叉核对，**没有当前服务器代码或实战确认**。Integrity 的“第十回合后 cap=11”解释为第十一回合起基础收入 11G，仍属有文本支持的解释。其条件性回合末 1G 奖励另算。[详见规则与经济](references/rules.md)

## 七 SOUL 的当前快照

SOUL 是被动与专属法术包，没有统一的主动英雄技能。不要从职业名字推断效果。

| SOUL | 被动 |
|---|---|
| DETERMINATION | 第一次本应死亡改为 5 HP；开局带 Save，利用死亡费用计数产生 Lost Soul |
| PATIENCE | 每偶数回合末，手未满且手／库均无 Change of Winds 时，将其加到牌库顶 |
| BRAVERY | 每三回合开始加 Recruitment 入手；手满则改加 Draft 入库 |
| INTEGRITY | 回合末，支出超过上回合则赚 1G，首回合除外；十回合后 cap=11 |
| PERSEVERANCE | 回合开始给没有 KR 的最高 ATK 敌怪 KR |
| KINDNESS | 第三回合起，回合末自己和受伤友军各治疗 1；无受伤友军则最右友军 +1 HP |
| JUSTICE | 回合开始，对最低 HP 敌怪造成 1 伤害 |

`soul-monster-*` 是特殊对战文本，不能由样本的 MONSTER 空条目推断第八个常规职业。

## 分析中最容易弄错的语义

- **用户于2026-10-05确认的裁定优先**：Magic不能选择触发它的怪物自身；固有效果自动作用于自身不属于自选。Undyne的DMG not dealt仅指因没有目标而剩余的伤害次数；对Armor等目标仍逐次结算，不智能绕开，受阻伤害不转成长矛。
- **Play ≠ Summon**：Magic 一般由打出触发；效果召唤除非明写，不自动触发 Magic。
- **Draw ≠ Add**：抽牌触发 Turbo；加入／生成到手牌不自动视为抽牌。
- **Die／Kill ≠ Erase／Catch／Return**：死亡触发 Dust、进入死亡区；Erase 不进死亡区；返回不算死亡。跨区字段保存按单卡文字处理。
- **Shock**：施放基础费用至少 2G 的法术**之后**触发，看基础费而非支付费。免费不等于不触发；效果代施法的排除条件只有 Wiki 补充证据。
- **KR 不是持续扣血毒**：临死前给击杀者 +1/+1；没有击杀者，或击杀者在拥有者回合内死亡，则给另一个随机敌怪。
- **Need 检查当下指定区域**，不是一律检查初始牌表。仅两张 Librarian 重复的牌组，抽出一张后剩余牌库就无重复。
- **Delay** 在打出当回合末执行，卡提前离场仍有效；**Support** 在另一友军攻击前触发；**Bullseye** 要恰好打到 0 并击杀。
- 当前／基础费用、当前／最大／基础 HP、Copy／Exact copy、TOKEN／Generated 均保留区分。`target=ALL` 不等于 AOE；描述里的关键词可能属于它操作的另一张牌。

## 按任务读取资料

| 当前任务 | 读取／执行 |
|---|---|
| 查关键词、战斗边界、金币、开局、构筑与状态 | [references/rules.md](references/rules.md) |
| 查某张卡、神器、SOUL、附魔或样本牌表 | `scripts/query.py`；先看 [数据与查询](references/data-guide.md)，避免把全部 JSON 载入上下文 |
| 评价牌组、起手、打法、交换／打脸与启动条件 | [references/deck-play.md](references/deck-play.md)，再查询实际核心卡 |
| 需要裁定、完整模拟器或“当前版本／最强／T1”结论 | [references/evidence.md](references/evidence.md)，必要时再查有日期的现行来源 |

查询使用 Python 3 标准库；路径按本 Skill 目录解析，与原项目位置和当前工作目录无关。例如：

```text
python <skill-dir>/scripts/query.py card --id 351
python <skill-dir>/scripts/query.py card --soul INTEGRITY --type spell --pool ordinary_non_token --limit 20
python <skill-dir>/scripts/query.py keyword --name shock
python <skill-dir>/scripts/query.py artifact --name Science
python <skill-dir>/scripts/query.py deck --name PATIENCE
python <skill-dir>/scripts/query.py gold --turn 3
```

Python 不可用时，按 ID 或名称定向搜索引用数据，不必为解释规则安装依赖。

## 如何形成有用的判断

牌组分析围绕**启动条件 → 前期存活 → G／手牌／格子／死亡区的转换 → 终结方式 → 失败状态**展开。先查核心卡的真实效果，再推导组合；按用户需要说明关键行动顺序。保存金币、牺牲友军或给对手死亡收益有时是主动兑现，不能只按裸身材判断。

区分三种结论：本地文本／元数据直接支持；具名社区裁定／经验支持；自己的推导或未知。提供的数据没有总体环境使用率或胜率，六副完整样本也不是已验证的最强推荐。现行用户卡面或实战证据若更新，优先对齐那个版本，明确与快照的差异。未实际读取 Discord 频道，不能引用所谓内部共识。
