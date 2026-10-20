# 联合开局：程序与证据入口

先读[携带/打法指南](GUIDE.md)，再读[完整结果与可靠性](REPORT.md)。这是当前主线；[此前固定部署研究](../carrying-priority/README.md)继续保留。新程序不运行旧缺失实验。

## 程序如何配合估值

- `model.py`：15种真实卡的资源/战斗/到牌环境，策略只能接收当前View；局部攻击完整枚举、部署启发式。
- `tactical.py`：同一当前手持Plane的确定性出牌/攻击顺序比较，不投影抽牌。
- `prioritize.py`：按期限、用途、风险上限比较五种冻结组成，输出目标频率、区间及经验Pareto。
- `query.py`：查询一格或成对差值；未知/缺失组合拒绝，不插值或补零。
- `analyze.py` / `milestones.py`：只读逐样本统计、配对区间、条件分母及早期时间截面。
- `audit_saved.py`：不导入引擎的独立保存数据守恒审计；不是全部游戏规则验证。
- `run_study.py`：新实验运行器，源码先提交、每组持久保存、失败即停、拒绝覆盖。旧完成结果日常不重算。

静态F仍是行动策略的共同体价代理；联合结果用来寻找其忽略的早场、时机、容量和压力兑现条件。它不会从这些自造对手中自动得到实战Gold，也不将各组平均值变为单卡强度榜。真实费用、目标和手牌结构决定比较条件。

## 日常查询（不模拟）

```sh
# 自身存活风险较严格的目的
python analysis/card-comparison/2026-10-20/joint-opening/prioritize.py --opponent large_reply --seat first --max-death .25 --conservative

# 同时要求一定进攻兑现；阈值由使用者指定
python analysis/card-comparison/2026-10-20/joint-opening/prioritize.py --opponent large_reply --seat first --min-objective .25 --max-death .35 --conservative

# 第四回合把对手压至15HP的用途，读取已存轨迹
python analysis/card-comparison/2026-10-20/joint-opening/prioritize.py --opponent mid --seat second --turn 4 --objective pressure15

# 一个卡位组替换的配对差（两阶段共享完全相同基线世界）
python analysis/card-comparison/2026-10-20/joint-opening/query.py --stage extension --composition small_reach --compare-stage tactics --compare-composition small_draw --intervention public_tactics --seat second --metrics killed dead first_turn_no_opener

# 固定牌序移除敌英雄回复；保留其单位回复/成长
python analysis/card-comparison/2026-10-20/joint-opening/query.py --stage counterfactual --composition small_draw --intervention no_foe_hero_heal --compare-intervention base --seat first --metrics killed opponent_hp
```

本轮实际输出见[query-examples.json](query-examples.json)。核心查询只依赖Python标准库；绘图脚本另需matplotlib，PNG/SVG已保存。

## 保存与接续

`main/`等七阶段各自保留design、组gzip、receipt。累计204格、每格128；重复基线明确去重，不能累加成独立证据。pilot单独保存未混入正式统计。确切源版本是各设计文件指向的Git提交；v0.1未提交试跑另存准确源码。所有参数、实体位置和策略假设可追溯。

[summary.csv](derived/summary.csv)为便于比较的均值表，[summary.json](derived/summary.json)含水平Wilson区间、配对差值近似区间及条件分母，[两类对手策略图](derived/outcome-plane-pressure.png)可与指南图对照。[audit.json](audit.json)汇集独立守恒结果；初始审计工具拒绝新标签与首次回放日志错误均保留历史及修复说明，没有改写成从未失败。

七个选定种子补存[完整动作回放](witnesses/index.json)，与冻结终点和半回合轨迹完全相同，不是新增统计样本。不要重放全部完成组来凑覆盖。后续只为新机制、策略或真实反例建新目录/阶段；重要结果提交并推到`research/local-method-lab-20261018`才算交付。
