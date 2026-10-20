# 自然金币、SOUL与大小怪部署比较

续作：[携带优先级指南](carrying-priority/GUIDE.md)与[短开局程序](carrying-priority/README.md)已将研究推进到早出/等待、真实到牌、补牌加速和保血需求；本页固定12G数据保持原样，不需重算。

2026-10-20。先读[研究结果与边界](REPORT.md)。组卡继续暂停；本轮比较同一可见手牌内的完整出牌菜单。新增多敌顺序攻击、三个局部SOUL被动、自然金币账本、到牌见证及现金/手牌价格区间。当前是启发式条件比较，不是完整开局或胜率模拟。

## 直接查询冻结结果

日常查询只需Python标准库；不执行战斗、旧实验或API。默认使用有六张到牌见证的`arrival-results/`。

12G、空敌场，两Aaron与单Royal Guard 1，在手牌机会价2.1时是否稳健：

```sh
python analysis/card-comparison/2026-10-20/compare_packages.py --case guard/INTEGRITY/empty/keep1 --left 15 15 --right 38 --hand-price 2.1
```

面对敌10/1，比较至少留1体的用途；换SOUL查看Kindness对阈值的影响：

```sh
python analysis/card-comparison/2026-10-20/compare_packages.py --case guard/INTEGRITY/one_large_hit/keep1 --left 38 --right 15 15
python analysis/card-comparison/2026-10-20/compare_packages.py --case guard/KINDNESS/one_large_hit/keep1 --left 38 --right 15 15
```

面对两个5/7，查询所有可用组合中的最优，而非只比较预选两组：

```sh
python analysis/card-comparison/2026-10-20/compare_packages.py --case guard/INTEGRITY/two_durable/keep1 --hand-price 2
python analysis/card-comparison/2026-10-20/compare_packages.py --list-cases
```

`--left`/`--right`是实际出牌多重集合，不是整副牌。缺牌、超预算、无共同用途保证时不补0或别的场景。两种资源价格是条件输入，不是已测真实价格。输出九组共同价格的各自最优、精确菜单差平面及浮点优势多边形，不能将设置数当作投票。

## 源码与证据

- `package_model.py`：金币账本、受支持身体、完整普通敌体攻击顺序/目标/停手、SOUL阶段、资源价格区域。
- `run_packages.py`：原始7张条件手牌的新增物理研究，小批先行，拒绝覆盖结果。原始手牌未证明能在指定开局自然抽齐；不能拿它作正常开局推荐。
- `derive_arrival.py`：从冻结菜单精确限制为有到牌见证的6张手牌，更新留手与价格区域，**不重跑战斗**。
- `arrival-results/design.json`与`packages.json.gz`：默认查询输入，包含全部初始条件、卡面、生产提交和派生提交；原始`results/`、`pilot/`保留。
- [arrival-examples.json](arrival-examples.json)：8条实际六张到牌查询；早期7张查询另保存在`examples.json`，标有原默认目录与重放命令。
- [arrival-derived/findings.json](arrival-derived/findings.json)、[优势区间图](arrival-derived/resource-regions.svg)：只从冻结结果推导。较早`derived/`保留7张条件版本，不作为自然到牌版本。
- [经济输入审查](review-opening-economy.md)、[到牌投影审查](review-arrival-projection.md)、[独立手算反例](review-package-counterexamples.md)、[搜索复核](review-package-search.md)。
- `review_package_oracle.py`与原始receipt：独立普通战斗小oracle及部署守恒核对；`review_price_regions.py`核对保存多边形，不导入物理生产器。
- `verification.json`、`query-receipt.json`、`review-price-regions.json`保留针对检查的真实范围。绘图可选，需要已有matplotlib/numpy；查询和生产不需要这两个库。

不要为刷新报告重跑生产器。需要新规则、手牌或敌手牌回应时使用新输出目录，先做有明确用途的小批；旧17卡静态比较和14卡单敌研究在[前一轮目录](../2026-10-19/README.md)，无需重做。
