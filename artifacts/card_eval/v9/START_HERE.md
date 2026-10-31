# Undercards 卡牌评估程序 0.4.0

本包包含可安装程序、五个命名模型、示例、源码、必要输入和完整研究证据。**通用可靠评估目标尚未完成；完整实卡规则仍为20张及支持的语义组合。** 未知完整效果拒绝评分，不记成白板或零分。

## 安装与运行

Python3.11+，普通推理依赖NumPy。在解压后的顶层目录：

```sh
python -m pip install undercards_card_eval-0.4.0-py3-none-any.whl
card-eval models
card-eval assess Bench "Fishing Rod" --samples 8 --output results/reference
card-eval evaluate --input examples/planner-request.json --model entity-v9 --experimental-model --output results/planner
card-eval example --learned --output my-decks.json
card-eval evaluate --input my-decks.json --model entity-v9 --planner value --planner-margin 0.2 --planner-seconds 0.12 --experimental-model --output results/my-decks
card-eval catalog --output coverage.json
card-eval inspect Glyde
```

examples/planner-request.json包含本轮冻结主臂的完整搜索配置。自己的JSON可编辑25张牌表、实体替换位置、候选、对手牌组/SOUL/策略；模型对不同候选共享，不逐卡重训。普通参考比较使用examples/reference-request.json，不需实验选项。Glyde拒绝的非零退出码表示规则未支持，不是零分。

## 模型和输出

五个模型为legacy-v3、paired-v5、memory-v6、afterstate-v7和entity-v9，验证状态由models及收据明确展示，均未提升为可靠全池评分器。普通默认是声明参考策略，实验默认仍paired-v5；没有因模型较新就重选默认。

entity-v9学习实体/机制绑定和终局价值，但actor保留V5。仅加--model不改变该行动器；需要显式加planner才用后继价值改变行动。proof只接受规则证明的同回合斩杀；value另允许超门槛的价值选择。证明优先版本保护已经确定的攻击斩杀，未知抽牌和非终局回合边界停止展开。价值目标是冻结V5续局，不是新搜索策略自身V或最优Q。

输出有report.md、result.json、原输入、receipt.json和逐局games.jsonl.gz。保留未上手、等待、满格、受罚与预算未决；未决用0/1完成界。搜索与检查点的验证分开，配置和两种指纹都可复核；未经验证的搜索仍需实验模式，不给可靠方向推荐。

## 源码和证据复核

source/包含应用、冻结规则、模型、测试和V5/V6/V7/V8/V9必要输入与结果，另含复用所需V4基线。SOURCE_REVISION.json标记源码提交，顶层MANIFEST.json列出文件校验值。V7断连前后的原件哈希、完整3584分母和27未决都保留；V8开发尝试没有被隐藏或改名成最终通过。

在source/执行只读核对，无需重放旧游戏或重训：

```sh
python -m pip install '.[research]'
python -m card_eval.entity_audit --folder artifacts/card_eval/v9
```

本轮方法/指标/失败/下一问题见source/artifacts/card_eval/v9/REPORT.md。模型没有充分信念、对手最优反制或全部机制表示保证。神器、换牌、种族、死亡/生成链、服务器事件和沉默裁定仍有限制；安装和源码审计不是规则认证，也不是通用目标完成。

发行实现采用proof-first-3：同一观察的攻击搜索只计算一次，并将其耗时计入内部搜索预算。V9正式数据对应逐字保留的proof-first-2；不能把V9局部成绩重标为新版验收。新版只作软件/预算检查，策略仍实验。JSON的decision_seconds可明确指定整次决策预算；更宽预算的安装检查不计作同计算预算的策略验证。
