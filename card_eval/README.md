# 可直接使用的卡牌评估入口

0.4.0 完整运行包包含模型、规则快照、验证状态和示例。正常比较仍采用声明参考策略；实验默认载入随包 `paired-v5`，可按名称选择 `memory-v6` 或 `afterstate-v7`，无需研究目录或手动下载检查点。随包模型是否合格由各自记录决定，安装成功不改变质量门槛。

```sh
python -m pip install undercards_card_eval-0.4.0-py3-none-any.whl
card-eval models
card-eval assess Bench "Fishing Rod" --model paired-v5 --experimental-model --samples 8 --output results/first-run
card-eval example --learned --output my-decks.json
card-eval evaluate --input my-decks.json --model memory-v6 --experimental-model --output results/my-decks
card-eval assess Bench --model afterstate-v7 --planner value --planner-margin .1 --experimental-model --samples 8 --output results/public-search
```

生成的请求含完整25张己方牌表、替换位置、候选与对手，可自行编辑。遇到未实现的完整卡面会明确拒绝评分。`--checkpoint` 仍可加载自定义检查点，与 `--model` 二选一；Python API 可用 `card_eval.model_registry.checkpoint(name)` 取得随包模型路径。

`--planner proof` 只接受公开规则证明的同回合斩杀；`--planner value` 也允许动作后价值超过基线门槛时改动行动。JSON可用 `"planner":{"mode":"value","margin":0.1}`，默认48节点、深度3、宽度4、.18秒搜索界限；记录完整配置、搜索政策指纹与基线模型指纹。未知抽牌停止展开，非终局回合边界不估成同回合状态。`afterstate-v7` 的actor与V5相同，差别仅在critic；不加搜索不会产生更强行动器。价值属于冻结V5续局，不能称为新搜索策略的价值。示例门槛是输入示范；冻结主臂门槛见V7的development.json。

所有公开搜索配置目前都需显式实验模式，不能继承检查点本身的质量证明。搜索没有展开对手私手、随机牌序或下一回合，实测耗时与失败见 `artifacts/card_eval/v7/REPORT.md`；默认参考比较与模型未提升为可靠全池评分。

新观察会保留己方已知牌组的无序语义，以及双方实际公开出牌的机制摘要。它不读取敌方未打出牌或牌序，不等于完整信念状态。旧模型仍能使用新观察；`memory-v6` 缺失必要知识字段时会拒绝，不能把缺失历史当成零。

Python3.11+。在仓库根目录运行`python -m pip install -e .`，或安装发行wheel。已打包规则原语、卡面快照和共享模型，安装后不需要研究目录。

```sh
card-eval inspect Bench
card-eval assess Bench "Fishing Rod" --reference "Rock Pet" --samples 64 --output results/my-cards
card-eval check --input my-decks.json
card-eval evaluate --input my-decks.json --output results/my-decks
```

`assess`构造共同、合法张数的25张基准牌表和三类显式对手，**不是推荐卡组或现实环境分布**。`evaluate`读取用户自己的完整牌表。每个候选共用策略、实体排列和座次，不逐卡重训。默认检查三种语义参考策略，展示方向是否随对手或打法变化。学习模型未通过独立验证，正常入口拒绝把它当可靠评分器；加`--experimental-model`可查看共享模型诊断，结果不会作为方向推荐。

JSON请求包含`deck`（25个名称、ID或语义描述）、`slots`（要替换的实体位置）、`candidates`、`soul`、`opponents`（各含name/deck/soul/policy）、`samples`和`seed_start`。输入示例由`examples/card-eval-request.json`提供。双方SOUL目前支持INTEGRITY/KINDNESS。

输出目录有`report.md`、`result.json`、`input.json`、`receipt.json`、`games.jsonl.gz`。结果按对手和策略分别给终局差、配对区间、未上手/未出场与等待诊断；超时和未决保留完成界。不会把某张卡的未实现效果当零、只筛选成功出场样本，或平均成未经声明的全局Gold价格。

卡名/ID通过整段文本编译；受支持机制也可以直接用语义描述组合。`catalog --output coverage.json`列出完整支持与拒绝原因。任意新卡能进入输入检查，不代表任意卡面已经完整实现；不支持的卡返回结构化原因与空评分。

规则与质量必须分开看：规则引擎只保证声明模型内合法性，学习策略另有验证状态。当前仍缺完整神器、换牌、种族和死亡/生成链；沉默对修改属性的清理采用显式假设，不能声称已认证当前服务器。未知信息与不确定结论会保留，不强行输出一张全池榜。

0.2.1 支持载入关系式共享行动模型及独立的策略价值头。用 `--checkpoint path/to/primary-value.npz --policies learned --experimental-model` 显式运行新模型；源码及冻结试验见 `card_eval/relational_research.py` 和 `artifacts/card_eval/v4/`。模型文件在仓库随结果交付，默认模型未替换。推理仍只依赖 NumPy；复现实验的优化阶段需 `pip install '.[research]'`。价值头估计声明对手混合下该冻结策略的终局胜率，尚不直接改进行动，也不充当卡牌评分。

0.2.2 增加配对终局续局学习的行动差后端，入口同样使用 `--checkpoint artifacts/card_eval/v5/primary-value.npz --policies learned --experimental-model`。行动头按预测后续差决定是否偏离冻结基线；其混合续局目标与新策略自身的价值头分别训练，不能把其中一个叫作另一个的价值。源码、输入、失败和独立验收在 `artifacts/card_eval/v5/`；默认模型是否可升级以实际验收结果为准，不由安装成功或开发分数决定。
