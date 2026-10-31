# Undercards 卡牌评估程序 0.3.0

本包包含可安装程序、命名训练模型、示例、源码、当前实验所需输入和完整结果。**通用策略验收尚未通过，完整实卡规则仍为20张及支持的语义组合。** 未知卡面明确拒绝评分，不填成白板；实验模型不会作为可靠方向推荐器。

## 安装后直接运行

需要 Python3.11+，普通运行只依赖NumPy；pip会按声明安装依赖。在解压后的顶层目录：

```sh
python -m pip install undercards_card_eval-0.3.0-py3-none-any.whl
card-eval models
card-eval assess Bench "Fishing Rod" --model paired-v5 --experimental-model --samples 8 --output results/first-run
```

此命令用同一个随包模型完成候选替换，不需要研究目录或重新训练。`paired-v5`有先前局部正向证据，仍未通过全部条件；`memory-v6`是本轮合法知识/当前基线续局对照，也未通过。普通评估默认采用声明参考策略，实验默认使用随包V5；不会因包装成完整包就升级质量状态。

## 使用自己的牌表

```sh
card-eval example --learned --output my-decks.json
card-eval evaluate --input my-decks.json --model memory-v6 --experimental-model --output results/my-decks
card-eval catalog --output coverage.json
card-eval inspect Glyde
```

编辑请求中的己方25张牌、替换位置、候选、对手牌组/SOUL/策略。`examples/`也提供学习策略和参考策略两种完整请求。普通参考比较可去掉实验模型选项，并使用reference-request.json。未知或非法输入返回结构化原因与空评分；`inspect Glyde`的非零退出码是明确拒绝，不能解释为程序给了零分。

输出目录包含人读`report.md`、机器`result.json`、原请求、运行收据及逐局结果。未上手、等待、满格、受罚均进入分母；未决保留0/1完成界。结果只适用于声明牌组、策略和模型规则，不是全卡池榜或真实环境Gold价格。

## 源码与复核

`source/`含应用、冻结规则原语、测试、模型、V5复用输入及V6新续局/训练/最终结果，另含V6所需V4基线。`source/SOURCE_REVISION.json`标明对应Git源码提交；顶层`MANIFEST.json`给出所有交付文件校验值。历史更早实验请查Git仓库；本包不会补造其缺失资料。

在source目录可安装研究依赖并复核保存的证据，无需重放旧实验：

```sh
python -m pip install -e '.[research]'
python -m card_eval.memory_audit --output artifacts/card_eval/v6
```

`artifacts/card_eval/v6/REPORT.md`解释方法、否定结果和下一关键问题。新实验必须另建目录并使用新的最终留出；旧1210000/1310000/1330000/1610000/1630000及本轮1810000/1830000已用最终段均退休，不能调参重选。源码快照在无Git环境会报告`archive:<源码提交>`，不冒充新的Git提交。

目前缺完整神器、换牌、种族、死亡/生成链等；沉默与服务器队列仍有声明假设。公开机制记忆是无序摘要，不是完整信念状态。只训练一个随机种子，牌序区间不覆盖训练方差。后续继续优化，不宣称通用目标已完成。
