# 快照、字段与定向查询

入口脚本 `scripts/query.py` 仅使用 Python 3 标准库，不连接网络、不写文件。路径相对脚本定位；整份 Skill 可以复制给其他 Agent，不依赖原项目绝对路径。

## 数据规模

`snapshot.json` 是本地提取结果的精简版，移除了账号持有量、闪卡重复、界面与故事文本，保留卡面、机制、神器标记和实际样本牌表：

- 卡牌文本 938 个 ID，其中 928 有元数据、10 个数值未知。
- 普通非 TOKEN 755：671 共享怪物、84 职业法术；每 SOUL 12。TOKEN 173：80 怪物、93 法术。
- 六种普通稀有度：BASE 35、COMMON 248、RARE 223、EPIC 155、LEGENDARY 72、DETERMINATION 22。
- 84 种神器效果、79 种神器元数据；44 个 ID 符合初选可用标记（29 普通、15 传奇），35 个 unavailable，5 个无元数据。
- 八个样本条目：六副 25 张完整牌表，KINDNESS 19 张，MONSTER 0 张。完整样本均通过可见构筑限制检查；不是服务器认证牌表，没有统计战绩。

统计是**这一快照的数量**。不保证所有普通牌在当前线上模式合法。`unavailable` 不表示局中效果被禁用。数据源文件的版本未标注；整理时间不能充当卡面发布日期。

## 查询示例

用 `<skill-dir>` 替换本 Skill 所在目录，路径有空格时加引号。

```text
python <skill-dir>/scripts/query.py card --id 185 274 297 466
python <skill-dir>/scripts/query.py card --name "Roaring Knight" --full
python <skill-dir>/scripts/query.py card --soul JUSTICE --type spell --pool ordinary_non_token --limit 20
python <skill-dir>/scripts/query.py card --tribe PLANT --rarity COMMON --limit 30
python <skill-dir>/scripts/query.py card --text "Dust" --cost-max 3 --limit 15
python <skill-dir>/scripts/query.py artifact --id 12 34 65
python <skill-dir>/scripts/query.py artifact --selectable --limit 50
python <skill-dir>/scripts/query.py keyword --name shock
python <skill-dir>/scripts/query.py status --name kr
python <skill-dir>/scripts/query.py enchant --name "The Cure"
python <skill-dir>/scripts/query.py soul --name BRAVERY
python <skill-dir>/scripts/query.py deck --name PERSEVERANCE
python <skill-dir>/scripts/query.py gold --turn 11 --integrity
```

结果输出 JSON，带匹配总数、返回数量和截断标记。默认最多 20 个，按需增加 `--limit`，上限 200；查完整大池应按类型／稀有度／费用拆开查询。`--pool ordinary_non_token` 限普通非 TOKEN 记录；不指定则也会查到 TOKEN 和仅文本牌，不能把全部匹配当可构筑牌。`--full` 展示全部记录字段，普通查卡则突出费用、身材、稀有度、职业、种族和效果。`--name` 为忽略大小写的子串；卡牌同时匹配本地文本名与元数据名；`--id` 精确匹配。

金币查询同时给出本回合基础收入与一直无支出的余额，明确排除其他效果。`--integrity` 的 11G 收入带“解释、未实测”标签，不包含支出比较奖励。

## 卡牌字段

| 字段 | 含义 |
|---|---|
| id／name／metadata_name | 用 ID 联结，两套名字可能有命名差异，保留别名检索 |
| cost／attack／health | 从 originalCost／originalAttack／originalHp 提取的基础卡面；缺元数据写 null，不猜 |
| card_type／soul | monster／spell；无 soul 的普通怪物共享，普通法术有专属 soul |
| rarity／pool_category | 普通六种稀有度、TOKEN、text_only；不是当前服务器合法性认证 |
| set | BASE 表示 Undertale 系列，区别于 rarity=BASE；另有 DELTARUNE、UTY |
| tribes | 元数据种族标签；不能从效果提到某种族反推自身种族 |
| effect_readable／effect_raw | 展开的英文卡面／原始宏；原始宏保留精确词条与引用 |
| keyword_mentions／tribe_mentions | **文字提及**，不表示所有提及都是本牌自带能力／种族 |
| base_statuses | 序列化基础状态；列表可能未显式包含 DT 沉默免疫等隐式规则 |
| target | 粗目标枚举，实际目标取卡面文字；ALL 不等于 AOE |
| source_key／source_line | 原 data.json 定位线索；Skill 不需要原文件才能查询 |

神器查询将效果与传奇／可用／类型标记联结。字段 `cost` 是界面购买类字段，**不当作每场战斗装备的 G 费用**。样本里普通／闪卡归并同 ID，持有量从 Skill 移除，因为它不是构筑上限。

## 更新原则

已有更近的用户数据时按 ID 联结并标注新快照。保持缺失值为未知，保留版本冲突，不用旧 Wiki 卡面覆盖新的用户卡面；重新计算数量与样本约束。仅更新某张牌时不需要读入全部卡池给模型。数据来源、哈希和外部核对边界见 [evidence.md](evidence.md)。
