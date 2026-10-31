# Undercards 卡牌评估程序 0.4.1

完整包提供安装程序、六个命名模型、示例、源码、必要输入、原始结果与失败。**通用可靠评估目标尚未完成，规则仍仅20完整实卡和支持的语义组合。** 未知效果不填零。

## 安装并比较替换

Python3.11+，推理依赖NumPy。在解压后的顶层目录执行：

```sh
python -m pip install undercards_card_eval-0.4.1-py3-none-any.whl
card-eval models
card-eval assess Bench "Fishing Rod" --samples 8 --output results/reference
card-eval evaluate --input examples/action-request.json --model action-v10 --experimental-model --output results/action
card-eval example --learned --output my-decks.json
card-eval check --input my-decks.json
card-eval evaluate --input my-decks.json --model action-v10 --experimental-model --output results/my-decks
card-eval inspect Glyde
```

自己的请求中编辑完整25张牌表、替换实体位置、候选、对手牌组/SOUL/策略和样本数。不同候选共用一份模型，不逐卡重训；没上手、等待、格满、受罚与预算未决均计入分母。Glyde的非零退出码和空评分表示规则未支持。模型的8效果输入上限也在开局前明确拒绝，不截断成无效果。

`action-v10`本身改变行动排序，并在冻结actor后学习自身终局价值，无需加planner。它预测的是一个行动后接V5续局的相对结果，不是最优Q，也没有充分信念或反制保证。自身critic与actor的目标、验证结果分开记录；本轮critic不驱动搜索。默认参考策略、实验默认paired-v5均未自动替换。

保留的entity-v9自身actor仍为V5；只有显式planner才用其价值搜索。需要对照时执行：

```sh
card-eval evaluate --input examples/planner-request.json --model entity-v9 --experimental-model --output results/planner
```

输出含report.md、result.json、input.json、receipt.json和games.jsonl.gz，指纹、预算和模型验证状态可核对。实验模型不产生可靠方向推荐，参数较新或软件检查通过不提升质量等级。

## 不重放游戏的证据审计

source/包含V4必要基线、V5至V10的必要输入/原始结果、权重、失败和源码。顶层MANIFEST.json列出文件哈希，source/SOURCE_REVISION.json标记源码提交。

在source/运行：

```sh
python -m card_eval.action_audit --folder artifacts/card_eval/v10
```

审计只读数据，核对开局权重、完整槽位、未知结果、配对区间和actor/critic对应，不重训或重放旧实验。研究方法见METHOD.md，结论/限制/下一关键问题见REPORT.md。旧0.4.0包与V9证据保留，不能把不同版本的搜索表现合并或重标成新模型通过。

神器、换牌、种族、死亡生成链、服务器事件与沉默裁定仍有限制；没有真实天梯频率、全卡池榜或最优反制认证。
