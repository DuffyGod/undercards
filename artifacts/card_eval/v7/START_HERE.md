# Undercards 卡牌评估程序 0.4.0

包含可运行程序、四个命名训练模型、完整牌表示例、源码、必要输入和本轮证据。**通用可靠评估目标尚未完成；完整实卡规则仍为20张及受支持语义组合。** 未知卡面拒绝评分，不当作白板。策略结果与失败见source/artifacts/card_eval/v7/REPORT.md。

## 安装和评估

需要Python3.11+，推理仅依赖NumPy；在解压后的顶层目录：

```sh
python -m pip install undercards_card_eval-0.4.0-py3-none-any.whl
card-eval models
card-eval assess Bench "Fishing Rod" --model paired-v5 --experimental-model --samples 8 --output results/base
card-eval assess Bench --model afterstate-v7 --planner value --planner-margin .1 --experimental-model --samples 8 --output results/planner
card-eval example --learned --output my-decks.json
card-eval evaluate --input my-decks.json --model memory-v6 --experimental-model --output results/my-decks
card-eval catalog --output coverage.json
card-eval inspect Glyde
```

模型均保留未达标状态，只作实验。V7改变价值头，不单独改变V5行动器；必须显式加planner才使用动作后价值选择。示例门槛.1是输入示范，冻结主臂门槛见development.json；任意配置不能叫作该主臂。`proof`只用确杀证明，`value`另用基线续局价值。未知抽牌/非终局回合边界停止展开，不读取实际私手或牌序；没有充分信念或对手行动搜索。搜索需要更长实际用时，仍受共同决策上限约束。

普通参考比较可使用examples/reference-request.json且去掉实验选项。编辑25张牌表、替换位置、候选、SOUL和对手；未知输入返回结构化原因与空评分。Glyde拒绝的非零退出码不是零分。

输出包括report.md、result.json、input.json、receipt.json和逐局games.jsonl.gz。保留未上手、等待、满格、受罚和未决完成界，不合成为全池Gold或现实环境胜率。

## 源码和复核

source/含程序、冻结模型、规则原语、V5/V6复用输入、V7新训练/开发/最终证据，另含V6所需V4模型。源码提交见SOURCE_REVISION.json，文件校验值见顶层MANIFEST.json。完整历史在GitHub研究分支。

在source/执行只读核对，不重放旧局或重训：

```sh
python -m pip install '.[research]'
python -m card_eval.planner_audit --folder artifacts/card_eval/v7
```

原始标签、缺失原因、优化状态、每个最终槽位、运行失败和接续判断均保存。内部核对不是服务器认证。换牌、神器、种族、死亡/生成链、完整事件顺序与沉默裁定仍有限制。
