# 卡牌替换评估

参照：Rock Pet。每项按同种子、双方座次配对，未上手和未出场都保留。

这些结果适用于输入牌组、声明对手和已实现规则；没有合成为真实环境总分或Gold价格。

## Bench

证据不足，暂不排序

| 对手 | 我方策略 | 替换差，百分点 | 配对95%区间 | 未收到/收到未出/已出 |
|---|---|---:|---:|---:|
| pressure | race | +0.00 | +0.00～+0.00 | 2/2/0 |
| pressure | guard | +0.00 | +0.00～+0.00 | 0/0/4 |

共16个比较槽位，0个未决；未决保留0/1完成界，不记作半胜。

跨全部条件的方向建议使用更严格的多重比较阈值；单行区间用于查看条件差异。

规则边界：Initial3 cards and first-turn natural draw；No artifacts/mulligan/tribal/death chains；Automatic callback order is a declared model rule；Silence modified-stat cleanup: retain。

本次比较使用声明策略，不代表最优对弈；牌序区间不覆盖规则误差或策略不足。
