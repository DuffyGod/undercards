# 可直接使用的卡牌替换评估程序

最新为[V13配对策略续局更新](../artifacts/card_eval/v13/START_HERE.md)：预定开发未超过V5，追加新开发未复现相对冻结成本的优势，也未证明超过仅先验模仿；qualified=false，433/435最终及自身V未执行。源码、独立NPZ、未知/原始记录与全部对照保留，默认不升级。直接行动接口严格.25秒8/8终局，未拟合value搜索继续拒绝；不是新版发行，通用可靠目标尚未完成。

最新为[V12双续局路由器及自身价值研究交付](../artifacts/card_eval/v12/START_HERE.md)。预留最终1536槽位全终局，八背景平均64.45%对V5 66.60%、V11 55.27%，qualified=false；自身V留出误差也弱于旧V5，默认模型不升级。直接actor接口8/8终局，可选value搜索预算检查3/8超时、未通过。源码、独立NPZ、原始记录/未知及审计均保留；不是新版完整发行。

当前分支另含[开发被拒绝的V11研究扩展](../artifacts/card_eval/v11/START_HERE.md)，需源码安装并显式--checkpoint/--experimental-model，不属于已发布0.4.1 wheel。未拟合当前actor自身V的检查点会在value搜索前返回空评分与原因；不能把继承的旧critic当成新策略价值。V11没有升级默认模型或发布新完整发行。

0.4.1包含命名训练模型、规则快照、公开搜索、完整25张牌表输入和示例。普通比较默认采用声明参考策略；实验默认仍paired-v5，另可选择action-v10、memory-v6、afterstate-v7、entity-v9或保留的legacy-v3。**通用可靠评价尚未完成；未知完整效果拒绝评分。**

```sh
python -m pip install undercards_card_eval-0.4.1-py3-none-any.whl
card-eval models
card-eval assess Bench "Fishing Rod" --samples 8 --output results/reference
card-eval assess Bench --model action-v10 --experimental-model --samples 8 --output results/action
card-eval assess Bench --model entity-v9 --planner value --planner-margin 0.2 --planner-seconds 0.12 --experimental-model --samples 8 --output results/experimental
card-eval example --learned --output my-decks.json
card-eval check --input my-decks.json
card-eval evaluate --input my-decks.json --model entity-v9 --planner value --planner-margin 0.2 --experimental-model --output results/my-decks
card-eval inspect Glyde
```

Python3.11+，推理依赖NumPy。源码安装用pip install -e .，研究优化可用pip install '.[research]'。安装包包含规则原语、卡面快照、模型与示例，普通评估不需要研究目录。完整ZIP还提供源码、必要输入和证据，指引见artifacts/card_eval/v10/START_HERE.md。

JSON包含deck（25名称/ID/语义描述）、slots（替换实体位置）、candidates、soul、opponents（完整牌表/SOUL/策略）、samples、seed_start等。可使用完整包examples/planner-request.json运行本轮配置；也可编辑生成请求。未知卡/非法张数/未实现规则有结构化原因与空评分，不填零。双方SOUL当前支持INTEGRITY/KINDNESS。

action-v10直接学习同局面的行动差，并在actor冻结后另学其自身的终局价值；不加planner也会改变行动。其行动标签仍是“一步干预后接V5续局”，不是最优Q或新策略自身Q；有序源/目标效果也不等于完整局面或信念。模型容量为8项效果，超出时在开局前返回空评分与原因。训练/最终/失败见artifacts/card_eval/v10/REPORT.md。

entity-v9按共享语义学习实体和机制绑定的终局价值，没有每卡ID参数；actor保留V5，不加planner时不会产生更强行动器。afterstate-v7同样只改变critic。--planner proof只接受公开规则证明，value还按学习价值选择值得执行的后继；已经证明的斩杀优先。JSON可用"planner":{"mode":"value","margin":0.2,"seconds":0.12}，默认48节点、深度3、宽度4、内部.12秒。--checkpoint仍支持自定义模型，与--model二选一。

搜索只展开己方当前回合的确定公开动作；未知抽牌停止，非终局end不伪装成仍可行动的状态。V7/V9值目标是基线V5继续行动的胜率，V10自身critic目标是其冻结actor续局；两者均不是搜索策略自身V或最优Q。没有充分信念、对手回合搜索或最优反制保证。搜索不能继承基础检查点的验证状态，所有公开搜索仍需显式实验模式。

result.json、report.md、input.json、receipt.json及games.jsonl.gz按声明对手/策略给替换差、配对区间和未上手/未出场诊断。frozen_policy标记含搜索配置的策略，base_model标记模型；失败保留完成界。所有候选共用模型、实体牌序和座次，不逐卡重训；不平均为未知现实环境总分或Gold价格。--model较新、训练上涨或安装成功都不提升质量状态。

规则覆盖与策略质量独立：完整文本仍仅20张实卡及支持语法；完整神器、换牌、种族、死亡/生成链、服务器事件队列和沉默清理尚未认证。模型编码也不是完整机制/历史表示。V7原版和所有失败保留，V8未执行最终，V9完整结果见artifacts/card_eval/v9/REPORT.md；233/235及旧已读最终段不能用于重选模型。

发行实现采用proof-first-3：同一观察的攻击搜索只计算一次，并将其耗时计入内部搜索预算。V9正式数据对应逐字保留的proof-first-2；不能把V9局部成绩重标为新版验收。新版只作软件/预算检查，策略仍实验。JSON的decision_seconds可明确指定整次决策预算；更宽预算的安装检查不计作同计算预算的策略验证。
