# 卡牌替换评估

参照：Rock Pet。每项按同种子、双方座次配对，未上手和未出场都保留。

这些结果适用于输入牌组、声明对手和已实现规则；没有合成为真实环境总分或Gold价格。

使用模型：prototype。验证状态见本报告结尾及 result.json。

## Bench

学习模型未达标，仅作实验诊断

| 对手 | 我方策略 | 替换差，百分点 | 配对95%区间 | 未收到/收到未出/已出 |
|---|---|---:|---:|---:|
| pressure | learned | +25.00 | +0.00～+50.00 | 2/0/2 |

共8个比较槽位，0个未决；未决保留0/1完成界，不记作半胜。

跨全部条件的方向建议使用更严格的多重比较阈值；单行区间用于查看条件差异。

规则边界：Initial3 cards and first-turn natural draw；No artifacts/mulligan/tribal/death chains；Automatic callback order is a declared model rule；Silence modified-stat cleanup: retain。

学习模型尚未通过独立验证，上述数值仅作实验诊断。
