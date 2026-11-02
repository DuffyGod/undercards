# V13源码与共享行动模型

本轮实现两次策略更新，并在完全相同的当前策略局面/行动上对比更新续局目标与冻结旧续局目标。质量结论见[REPORT.md](REPORT.md)、[validation.json](validation.json)，**不能把可加载模型或训练下降当作通用评价完成**。默认参考比较与paired-v5不变，最近完整发行仍0.4.1；已发布wheel不含本轮源码扩展。

Python3.11+，推理只需NumPy；从当前研究分支源码运行：

```sh
python -m pip install -e .
card-eval assess Bench --checkpoint artifacts/card_eval/v13/updated-selected.npz --policies learned --experimental-model --samples 2 --output results/v13-replacement
```

`updated-selected.npz`是始终冻结的主臂；`frozen-selected.npz`是旧续局控制臂；`phase0-selected.npz`是第一次更新。三者都是固定epoch64，共享语义输入，无按卡牌ID重训。源/目标最多8个有序机制效果；未知卡/机制或超容量保持拒绝/空评分，不填零或静默截断。

这些NPZ自带V5基础模型，推理不需访问训练目录。共享模型分别在原牌与候选替换牌上重新决策，保留没上手、等待、满格、受罚路径；结果仅是声明规则、完整25张牌组、对手与实验策略下的条件差。未通过模型必须显式experimental开关，不能给可靠方向推荐。

本轮学习终局续局代价的行动排序，分数不是校准Q*或π2自身V。检查点value_unfitted=true，继承的V5 critic不能标成新策略自身价值；调用value搜索会在开局前返回空评分与unfitted_value。不能沿用V12已拟合router的critic，因为actor已经改变。

## 复核材料

```sh
python -m card_eval.policy_iteration_audit --output artifacts/card_eval/v13
```

审计只读原始输入/决策/反事实结果/权重，核对共同前缀断言、在线停止根、两臂共同warm-start及更新预算、标签掩码、固定模型、开发全分母、区间与门槛，不重放牌局、重训或补标签；收据会刷新。需保持原工作树时，先复制完整交付目录。

design.json、METHOD.md冻结实验；p0阶段复用V12 value-train前64/value-dev前16原件，不能计作80新开局；p1阶段另80新开局。所有源文件以Git路径+哈希引用，未引用V12的383/385最终。每个episode文件原子保存完整输入、必要逐决策、停止根、采样动作、两个续局标签及未决原因。全部16/32/64epoch权重保留，训练选择只取64，不根据曲线重选。

target-activation-audit.json区分“终局整体平移”和“行动差改变”，并在相同已知标签掩码下核对梯度差。off-action-order-probe.json仅是规则可核对的当前表示反例：当前行动矩阵相同但End已知赢/输不同；两状态先治疗都能赢，因此不证明最优策略必须不同。较早观察可能支持RNN记忆，完整序列恢复尚未检验。该反例不进训练/选择，解释纠正也原样保留。

433/435最终是否执行以final-status.json为准；开发不通过则保持未读，不挑更好控制臂补跑。当前规则仍20张完整实卡及支持语法，不是完整卡池、服务器裁定、完整信念或对手最佳反制。

仓库外源码副本+独立NPZ的软件检查见interface/verification.json，不是新发行包或策略质量样本。以下复现命令要求新输出目录：

```sh
python -m card_eval.suffix_interface_verify --folder artifacts/card_eval/v13 --output results/v13-interface --checkpoint-name updated-selected.npz --seed-start 4391000
```
