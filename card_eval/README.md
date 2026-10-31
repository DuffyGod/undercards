# 可直接使用的卡牌评估入口

Python3.11+。在仓库根目录运行`python -m pip install -e .`，或安装发行wheel。已打包规则原语、卡面快照和共享模型，安装后不需要研究目录。

```sh
card-eval inspect Bench
card-eval assess Bench "Fishing Rod" --reference "Rock Pet" --samples 64 --output results/my-cards
card-eval check --input my-decks.json
card-eval evaluate --input my-decks.json --output results/my-decks
```

`assess`构造共同、合法张数的25张基准牌表和三类显式对手，**不是推荐卡组或现实环境分布**。`evaluate`读取用户自己的完整牌表。每个候选共用同一模型、实体排列和座次，不逐卡重训。默认同时检查学习策略及三种语义规则，展示方向是否随对手或打法变化。

JSON请求包含`deck`（25个名称、ID或语义描述）、`slots`（要替换的实体位置）、`candidates`、`soul`、`opponents`（各含name/deck/soul/policy）、`samples`和`seed_start`。输入示例由`examples/card-eval-request.json`提供。双方SOUL目前支持INTEGRITY/KINDNESS。

输出目录有`report.md`、`result.json`、`input.json`、`receipt.json`、`games.jsonl.gz`。结果按对手和策略分别给终局差、配对区间、未上手/未出场与等待诊断；超时和未决保留完成界。不会把某张卡的未实现效果当零、只筛选成功出场样本，或平均成未经声明的全局Gold价格。

卡名/ID通过整段文本编译；受支持机制也可以直接用语义描述组合。`catalog --output coverage.json`列出完整支持与拒绝原因。任意新卡能进入输入检查，不代表任意卡面已经完整实现；不支持的卡返回结构化原因与空评分。

规则与质量必须分开看：规则引擎只保证声明模型内合法性，学习策略另有验证状态。当前仍缺完整神器、换牌、种族和死亡/生成链；沉默对修改属性的清理采用显式假设，不能声称已认证当前服务器。未知信息与不确定结论会保留，不强行输出一张全池榜。
