# V11研究交付：开发拒绝的策略原型

本轮没有升级默认策略或发布新的完整发行。最新完整包仍为0.4.1；V11是当前研究分支中的源码扩展、独立检查点和可复核实验。**主臂开发40%对V5 50%，不推荐用于可靠卡牌排序，通用目标未完成。**

## 在当前分支源码中复核接口

Python3.11+，推理只需NumPy。请使用当前Git分支源码；已发布0.4.1 wheel尚不包含V11模型加载器。

```sh
python -m pip install -e .
card-eval assess Bench --checkpoint artifacts/card_eval/v11/regret_mean-selected.npz --policies learned --experimental-model --samples 2 --output results/v11-actor
```

模型跨卡共享，没有按卡ID单独拟合。输出仍是声明规则、牌组、对手与策略下的替换比较，保留没上手、等待、满格和受罚路径。该原型的结果只标实验用途，不给可靠方向推荐；默认参考比较和paired-v5均未替换。

V11没有拟合通过验证的新actor自身V。`value_unfitted=true`检查点用于value搜索会在开局前被拒绝并返回空评分，避免将继承的V5 critic当作新策略自身价值。未知卡/机制继续拒绝评分；源/目标有序效果的模型容量仍为8，超长不截断成无效果。

`interface-verification.json`记录了仓库外独立源码副本+独立NPZ的实际检查：严格.25秒8槽位均终局，质量门槛、未拟合V拒绝和Glyde空评分均通过。这不是新版wheel安装验收，也不是8个新增独立策略样本。

## 不重放游戏的审计

```sh
python -m card_eval.suffix_audit audit --folder artifacts/card_eval/v11 --output results/v11-input-audit.json
python -m card_eval.suffix_audit development --folder artifacts/card_eval/v11 --output results/v11-development-audit.json
```

两项只读原始数据，不重训或重跑牌局；输出路径需新建。完整方法见METHOD.md，开发前冻结见BEFORE_DEVELOPMENT.md，拒绝判断见AFTER_DEVELOPMENT.md，结论与限制见REPORT.md。

333/335最终及自身critic拟合依预定门槛没有执行，不能重选控制臂后补跑并称本轮通过。已有训练/诊断/开发原件、全部epoch权重、7个预算未知、环境恢复与哈希均已保留。
