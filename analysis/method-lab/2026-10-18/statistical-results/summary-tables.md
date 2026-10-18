# 自动生成的统计摘要

单位均为 model-G。原始卡池及资源统计不等于实战分布；参数范围不等于置信区间。

## 共同净报价 E[Q] − cost

| 卡牌 | 满血低费三体 | 中费单体 | 高费单体/沉默 | 空场发展 | 受伤低费三体 |
| --- | --- | --- | --- | --- | --- |
| Glyde | -1.194 | -1.753 | -1.849 | -1.070 | -1.194 |
| Terakota Archer | +0.579 | -1.286 | -0.638 | -2.821 | -0.359 |
| Piranhas | +1.018 | -0.588 | +0.186 | -0.748 | +1.866 |
| Broken Car | +1.553 | -1.200 | -0.824 | -1.599 | +1.124 |
| Blockler B | +1.187 | -0.013 | +0.221 | +0.223 | +0.980 |
| Lesser Dog | -0.307 | -0.839 | -0.466 | -0.183 | -0.307 |
| Woshua | +0.958 | -0.392 | +0.111 | -0.367 | +0.591 |
| Aaron | -0.132 | -0.692 | +0.000 | -0.000 | -0.132 |
| Tsunderplane | +0.323 | -1.472 | -0.974 | -1.938 | +1.233 |
| Vulkin | +1.114 | -0.181 | +0.735 | +0.125 | +1.296 |

## 配对属性边际（其余输入相同）

| 场景 | 卡牌 | +ATK | 固定原当前计划+ATK | +HP | 计划改变质量 |
| --- | --- | --- | --- | --- | --- |
| aggro_wide | Woshua | 0.5546 | 0.5546 | 0.4295 | 0.0000 |
| aggro_wide | Aaron | 0.2275 | 0.2275 | 0.6019 | 0.0000 |
| aggro_wide | Vulkin | 0.4042 | 0.4042 | 0.5772 | 0.0020 |
| aggro_wide | Broken Car | 0.9489 | 0.6664 | 0.4060 | 0.4297 |
| aggro_wide | Blockler B | 0.6155 | 0.3437 | 0.4404 | 0.4512 |
| control_silence | Piranhas | 1.3110 | 1.3110 | 0.6053 | 0.0000 |

## 同一组参数的配对分差

| 场景 | 左 − 右 | 中央差 | 11组参数最小 | 11组参数最大 | 配对MC标准误 |
| --- | --- | --- | --- | --- | --- |
| aggro_wide | Glyde − Terakota Archer | -1.773 | -2.145 | -1.404 | 0.0367 |
| aggro_wide | Broken Car − Piranhas | +0.536 | +0.294 | +0.591 | 0.0425 |
| aggro_wide | Blockler B − Lesser Dog | +1.494 | +1.064 | +2.227 | 0.0146 |
| midrange_single | Glyde − Terakota Archer | -0.467 | -0.593 | -0.341 | 全体枚举/无抽样 |
| midrange_single | Broken Car − Piranhas | -0.612 | -1.372 | -0.520 | 全体枚举/无抽样 |
| midrange_single | Blockler B − Lesser Dog | +0.826 | +0.613 | +1.350 | 全体枚举/无抽样 |
| control_silence | Glyde − Terakota Archer | -1.212 | -1.321 | -1.102 | 全体枚举/无抽样 |
| control_silence | Broken Car − Piranhas | -1.010 | -1.185 | -0.983 | 全体枚举/无抽样 |
| control_silence | Blockler B − Lesser Dog | +0.687 | +0.525 | +0.942 | 全体枚举/无抽样 |
| empty_development | Glyde − Terakota Archer | +1.751 | +1.583 | +1.919 | 全体枚举/无抽样 |
| empty_development | Broken Car − Piranhas | -0.851 | -2.479 | +0.776 | 全体枚举/无抽样 |
| empty_development | Blockler B − Lesser Dog | +0.406 | -0.540 | +1.352 | 全体枚举/无抽样 |
| wounded_wide | Glyde − Terakota Archer | -0.835 | -1.151 | -0.520 | 0.0427 |
| wounded_wide | Broken Car − Piranhas | -0.741 | -0.870 | -0.651 | 0.0426 |
| wounded_wide | Blockler B − Lesser Dog | +1.287 | +0.992 | +1.933 | 0.0185 |

## 只换共同资源结构

| 资源 | 场景 | 卡牌 | 净报价 | 可支付率 | 可放弃部署的机会指数 |
| --- | --- | --- | --- | --- | --- |
| lower | aggro_wide | Lesser Dog | -0.354 | 0.408 | 0.005 |
| lower | aggro_wide | Glyde | -2.242 | 0.408 | 0.000 |
| lower | aggro_wide | Terakota Archer | -0.219 | 0.408 | 0.136 |
| lower | control_silence | Lesser Dog | -0.501 | 0.408 | 0.001 |
| lower | control_silence | Glyde | -2.633 | 0.408 | 0.000 |
| lower | control_silence | Terakota Archer | -1.476 | 0.408 | 0.011 |
| lower | wounded_wide | Lesser Dog | -0.354 | 0.408 | 0.005 |
| lower | wounded_wide | Glyde | -2.242 | 0.408 | 0.000 |
| lower | wounded_wide | Terakota Archer | -0.400 | 0.408 | 0.192 |
| final | aggro_wide | Lesser Dog | -0.307 | 0.451 | 0.001 |
| final | aggro_wide | Glyde | -1.194 | 0.451 | 0.003 |
| final | aggro_wide | Terakota Archer | +0.579 | 0.451 | 0.423 |
| final | control_silence | Lesser Dog | -0.466 | 0.451 | 0.000 |
| final | control_silence | Glyde | -1.849 | 0.451 | 0.000 |
| final | control_silence | Terakota Archer | -0.638 | 0.451 | 0.083 |
| final | wounded_wide | Lesser Dog | -0.307 | 0.451 | 0.001 |
| final | wounded_wide | Glyde | -1.194 | 0.451 | 0.003 |
| final | wounded_wide | Terakota Archer | -0.359 | 0.451 | 0.227 |
| higher | aggro_wide | Lesser Dog | -0.499 | 0.494 | 0.000 |
| higher | aggro_wide | Glyde | -0.456 | 0.494 | 0.039 |
| higher | aggro_wide | Terakota Archer | +0.786 | 0.494 | 0.538 |
| higher | control_silence | Lesser Dog | -0.610 | 0.494 | 0.000 |
| higher | control_silence | Glyde | -1.296 | 0.494 | 0.000 |
| higher | control_silence | Terakota Archer | +0.187 | 0.494 | 0.334 |
| higher | wounded_wide | Lesser Dog | -0.499 | 0.494 | 0.000 |
| higher | wounded_wide | Glyde | -0.456 | 0.494 | 0.039 |
| higher | wounded_wide | Terakota Archer | -0.567 | 0.494 | 0.122 |

## 身体攻击边际的数据来源

| A/7 → (A+1)/7 | P(目标HP>A) | 有效攻击增量 | F增量 |
| --- | --- | --- | --- |
| 2 | 0.9736 | 0.9789 | 0.6539 |
| 3 | 0.9093 | 0.9274 | 0.6729 |
| 4 | 0.6883 | 0.7506 | 0.5936 |
| 5 | 0.4015 | 0.5212 | 0.3929 |
| 6 | 0.2012 | 0.3610 | 0.2762 |
| 7 | 0.0407 | 0.2326 | 0.1138 |
| 8 | 0.0190 | 0.2152 | 0.1027 |
| 9 | 0.0000 | 0.2000 | 0.0826 |
| 10 | 0.0000 | 0.2000 | 0.0814 |

## Lesser Dog：死亡时折扣菜单的先验敏感度

以下是已发生Dust后的支付菜单增量；牌尚在场时只按tail保留，不等于整卡得分。

| 资源 | 未来cash | 每张未来卡净质量先验 | 折扣菜单增量 |
| --- | --- | --- | --- |
| lower_cost | 3 | 0.0 | 1.387 |
| lower_cost | 3 | 1.0 | 1.834 |
| lower_cost | 3 | 2.0 | 2.280 |
| lower_cost | 5 | 0.0 | 1.766 |
| lower_cost | 5 | 1.0 | 2.171 |
| lower_cost | 5 | 2.0 | 2.576 |
| lower_cost | 8 | 0.0 | 2.076 |
| lower_cost | 8 | 1.0 | 2.352 |
| lower_cost | 8 | 2.0 | 2.628 |
| middle_cost | 3 | 0.0 | 1.309 |
| middle_cost | 3 | 1.0 | 1.760 |
| middle_cost | 3 | 2.0 | 2.211 |
| middle_cost | 5 | 0.0 | 1.800 |
| middle_cost | 5 | 1.0 | 2.264 |
| middle_cost | 5 | 2.0 | 2.729 |
| middle_cost | 8 | 0.0 | 2.393 |
| middle_cost | 8 | 1.0 | 2.867 |
| middle_cost | 8 | 2.0 | 3.342 |
| higher_cost | 3 | 0.0 | 0.988 |
| higher_cost | 3 | 1.0 | 1.351 |
| higher_cost | 3 | 2.0 | 1.713 |
| higher_cost | 5 | 0.0 | 1.484 |
| higher_cost | 5 | 1.0 | 1.880 |
| higher_cost | 5 | 2.0 | 2.276 |
| higher_cost | 8 | 0.0 | 2.122 |
| higher_cost | 8 | 1.0 | 2.588 |
| higher_cost | 8 | 2.0 | 3.053 |

## Gold锚的外部信息有多稀疏

文字及初始状态均为空的普通怪物只有6张；种族、稀有度与设计强弱仍混杂，未拟合。

| 卡牌 | 印刷费 | 身材 | F | F−费用 |
| --- | --- | --- | --- | --- |
| Froggit | 2 | 2/3 | 2.238 | +0.238 |
| Moldsmal | 2 | 3/2 | 2.160 | +0.160 |
| Aaron | 5 | 6/5 | 5.000 | +0.000 |
| Candy Dish | 3 | 2/6 | 3.449 | +0.449 |
| Tiny Froggit | 0 | 1/1 | 0.986 | +0.986 |
| Rock Pet | 2 | 3/3 | 2.662 | +0.662 |

## 共同付费菜单的顺序选择权

候选与2G Froggit都必须打出，同付费同背景；这是孤立顺序增量，不加入主分。

| 资源 | 场景 | 卡牌 | 顺序毛增量 | 可支付顺序增量 | 联合可支付质量 |
| --- | --- | --- | --- | --- | --- |
| lower_cost | aggro_wide | Glyde | 0.0000 | 0.0000 | 0.2203 |
| lower_cost | aggro_wide | Terakota Archer | 0.4436 | 0.0255 | 0.2203 |
| lower_cost | midrange_single | Glyde | 0.0000 | 0.0000 | 0.2203 |
| lower_cost | midrange_single | Terakota Archer | 0.0363 | 0.0012 | 0.2203 |
| lower_cost | control_silence | Glyde | 0.0000 | 0.0000 | 0.2203 |
| lower_cost | control_silence | Terakota Archer | 0.0240 | 0.0009 | 0.2203 |
| lower_cost | wounded_wide | Glyde | 0.0000 | 0.0000 | 0.2203 |
| lower_cost | wounded_wide | Terakota Archer | 0.6112 | 0.0737 | 0.2203 |
| middle_cost | aggro_wide | Glyde | 0.0000 | 0.0000 | 0.3587 |
| middle_cost | aggro_wide | Terakota Archer | 0.6968 | 0.2049 | 0.3587 |
| middle_cost | midrange_single | Glyde | 0.0000 | 0.0000 | 0.3587 |
| middle_cost | midrange_single | Terakota Archer | 0.0907 | 0.0192 | 0.3587 |
| middle_cost | control_silence | Glyde | 0.0000 | 0.0000 | 0.3587 |
| middle_cost | control_silence | Terakota Archer | 0.0481 | 0.0127 | 0.3587 |
| middle_cost | wounded_wide | Glyde | 0.0000 | 0.0000 | 0.3587 |
| middle_cost | wounded_wide | Terakota Archer | 0.7244 | 0.3019 | 0.3587 |
| higher_cost | aggro_wide | Glyde | 0.0000 | 0.0000 | 0.3803 |
| higher_cost | aggro_wide | Terakota Archer | 0.7891 | 0.2895 | 0.3803 |
| higher_cost | midrange_single | Glyde | 0.0000 | 0.0000 | 0.3803 |
| higher_cost | midrange_single | Terakota Archer | 0.2115 | 0.0868 | 0.3803 |
| higher_cost | control_silence | Glyde | 0.0000 | 0.0000 | 0.3803 |
| higher_cost | control_silence | Terakota Archer | 0.1198 | 0.0538 | 0.3803 |
| higher_cost | wounded_wide | Glyde | 0.0000 | 0.0000 | 0.3803 |
| higher_cost | wounded_wide | Terakota Archer | 0.5305 | 0.1898 | 0.3803 |
