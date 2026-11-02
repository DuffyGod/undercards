# V12源码与检查点使用

这是共享续局策略路由器及自身价值模型的研究交付，**不等于通用可靠卡牌评价已完成**。质量结论、失败、未知和完成界以[REPORT.md](REPORT.md)、[validation.json](validation.json)为准。默认参考策略及实验默认paired-v5均未替换；最近完整发行仍0.4.1。已发布0.4.1 wheel不含本轮加载器，须用当前研究分支源码。

Python3.11+，推理只需NumPy；从仓库根安装与调用：

```sh
python -m pip install -e .
card-eval assess Bench --checkpoint artifacts/card_eval/v12/primary-value.npz --policies learned --experimental-model --samples 2 --output results/v12-replacement
```

模型在基准牌与候选替换牌上共享，不按卡牌ID重训。默认输出显式25张牌组、对手、规则假设及策略下的条件差，保留未上手、等待、满格、受罚路径；不承诺可靠全池排序。缺少显式experimental开关时，未通过验证模型被质量门槛拒绝，空评分不会被写成零。

`robust-selected.npz`、`base_target-selected.npz`、`own_target-selected.npz`使用同一份4464新增参数，内嵌冻结V5与V11模型，独立NPZ无需访问训练目录。主臂始终robust，没有看最终再换模式。它们的value_unfitted=true，继承的旧critic不能当当前路由策略自身V；用于value搜索会在开局前拒绝并返回空评分。

`primary-value.npz`保持robust行动指纹，另拟合其自然完整轨迹终局价值。直接行动接口严格.25秒8/8终局；可选价值搜索检查3/8超时，**未通过相同预算软件门槛**，原件及完成界保留，没有加宽预算补跑。价值搜索是另一策略，不能继承主actor的任何质量结论，搜索后的自身价值也未校准；以下仅示明实验入口：

```sh
card-eval assess Bench --checkpoint artifacts/card_eval/v12/primary-value.npz --policies learned --experimental-model --planner value --samples 2 --output results/v12-value-search
```

未知卡（如Glyde）、未知机制与超过8个有序效果的输入保持拒绝/空评分；规则仍是20张完整实卡及已支持语法。不是完整服务器机制、完整信念或对手最佳回应模型。

## 只读复核

```sh
python -m card_eval.continuation_audit --output artifacts/card_eval/v12
```

该审计读取原件，核对公开动作/冻结策略、在线根、四格共同前缀断言、未知完成界、模型选择和原始开发/最终指标，不重训、不重放游戏、不补缺测标签。审计收据被刷新；若需保持工作树原样，先复制整个交付目录再审计。

`design.json`和METHOD.md冻结总体方案，before-value-and-final.json在383/385最终前冻结行动与价值拟合方案；全部epoch候选、输入、逐决策roll-in、必要反事实结果、价值轨迹与失败原样保留。原V11的333/335最终从未执行，不伪称已读；本轮383/385一经执行即退休，不可用于接续调参或重新选模型。

`interface/verification.json`对应仓库外独立源码副本及独立NPZ的软件检查：直接actor通过，fitted-value预算失败。初次runner因失败提前抛出，收据由reconstruct_receipt.py只读已保存输出重建；未重跑游戏，临时导入路径原文没有保留。它不是新发行包安装验收，也不是独立的策略质量证据。复现该检查需新输出目录；失败会保存收据并返回非零：

```sh
python -m card_eval.suffix_interface_verify --folder artifacts/card_eval/v12 --output results/v12-interface --checkpoint-name robust-selected.npz --fitted-checkpoint-name primary-value.npz --seed-start 3891000
```
