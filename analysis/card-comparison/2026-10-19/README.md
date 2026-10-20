# 单卡条件比较：共同价格、真实替代与时机边界

续作已加入[自然金币、SOUL与多敌顺序攻击下的组合部署比较](../2026-10-20/README.md)。本文冻结结果保留，不需重跑；组合部署仍不是完整开局或组卡推荐。

本轮按用户要求暂停组卡。最新为[敌方回应、保命与留体用途报告](RESPONSE-REPORT.md)；前阶段的[共同价格与手牌研究](REPORT.md)保留。程序比较单卡，不输出牌组或无条件全池排名。当前仍是未实战校准的启发式模型。

## 直接查询已保存结果

Python标准库，无需安装依赖或API。下面命令只读冻结文件，不重跑实验。

共同致命敌4/2、己3HP、3G，比较能否保证保命：

```sh
python analysis/card-comparison/2026-10-19/compare_cards.py reply --ids 9 187 --case immediate_attack_needed
```

同为5/5，先比较只要求保命的条件，再比较要求至少留1体的用途：

```sh
python analysis/card-comparison/2026-10-19/compare_cards.py reply --ids 43 168 --case balanced_trade --price-setting central --cash-price .5
python analysis/card-comparison/2026-10-19/compare_cards.py reply --ids 43 168 --case balanced_trade_keep_body --results analysis/card-comparison/2026-10-19/reply-standing
```

`reply`仅包含一个普通敌体的一次可选攻击；初始己场为空、4格、敌英雄30HP。未达到共同HP/留体目标时不给数值替代。不能保证目标不等于不可打出，也不表示对手必然选最坏分支。完整限定、14卡支持集、独立标签核查及防护反事实见最新报告；`reply-examples.json`保留7条实际查询。

同为6G，背景Froggit＋Moldsmal，敌三个3/2、现金6、两格：

```sh
python analysis/card-comparison/2026-10-19/compare_cards.py compare --ids 530 984 --menu two_plain --board three_3_2 --cash 6 --slots 2 --price-setting central --cash-price .5
```

比较一整段现金残值及九组共同价格，而非自动挑各牌有利参数：

```sh
python analysis/card-comparison/2026-10-19/compare_cards.py compare --ids 9 377 --menu two_plain --board empty --cash 7 --slots 3
```

两个共同敌场的适用质量门槛（q为第二类敌场的假设质量）：

```sh
python analysis/card-comparison/2026-10-19/compare_cards.py compare --ids 530 984 --menu two_plain --board three_3_2 --second-board single_6_7 --cash 6 --slots 2
```

仅知道两期各50%机会时的单次兑现范围：

```sh
python analysis/card-comparison/2026-10-19/compare_cards.py opportunity-bounds --reward 4 --marginals .5 .5 --reference-value 3
```

缺少指定卡或共同资源条件时拒绝报价；不拿别的场景补齐、不补0。`all`价格设置表示有限共同压力点，不表示实战频率。输出的`both_suppressed_by_background_or_budget`说明两张卡在这一当前窗口都未增加背景菜单价值，不能当作整卡等价。

## 数据与证据

- [results/design.json](results/design.json)：17张焦点卡、价格/现金/格子/背景设计及假设。数值生产代码版本为`a8b8e9d`；原输入检查点另列，生产代码当时未提交的事实也明确记录。
- [results/card-conditions.csv](results/card-conditions.csv)：当前增益、相对参考替代价值及敏感度。
- [results/pairwise.csv](results/pairwise.csv)：全部21对同原生费用卡在共同条件下的配对范围。
- `results/curves.json.gz`：完整分段曲线、可见场景及物理付款菜单，可用上述查询程序读取。
- [examples.json](examples.json)：具名查询例；其中第三背景不同的例子是不同手牌条件，不是对局中免费加牌。
- [controlled-hand-probe.json](controlled-hand-probe.json)：同现金、格子、敌场，只向真实背景中增加一张Aaron的定向反事实；五张6G卡共同检查。
- [review-controlled-hand.md](review-controlled-hand.md)：独立中心手算及真实选择边界。
- [derived/findings.json](derived/findings.json)、[derived/all-background-mixtures.csv](derived/all-background-mixtures.csv)：从本轮冻结曲线推导，无再次执行物理核心。
- 独立数学核查原记录为`review-frontier-independent.json`；其发现的小边界错误及仅针对修复的17例复查保留在`review-frontier-boundary-fix.json`。

新增研究的生产脚本为`run_study.py`、`controlled_hand_probe.py`、`summarize_saved.py`；各自拒绝覆盖已有输出。旧方法试验、旧恢复快照及deck-lab保持原样。日常使用只查询，不为刷新报告重做这些计算。

静态`compare`的假设：当前有限截止；共同身体F保留普通残值；未来特殊能力储备为0；无敌方回应、玩家生存目标或跨回合手牌过程；部分无目标落地和召唤格子处理沿用旧稀疏菜单假设。新增`reply`不改变这些旧数据，只在新目录加入明确的回应和HP/留体目标，生产源为`response_window.py`、`run_reply_study.py`。两类条件值都不等于整卡携带分。日常使用冻结查询，不重新运行生产器。
