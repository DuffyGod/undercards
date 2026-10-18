# 辅助API审计与采用边界

这是候选发现和反例工具；最终牌表、计算、模型边界由本地研究决定，不以LLM“core/flex”票数形成卡牌价格。

本次实际20个请求，模型`deepseek/deepseek-flash`、thinking disabled，最多4并发。使用用户提供的`TencentClient`；密钥由客户端自身读取，不进入请求payload、产物或日志。每次调用之前先落attempt，传输重试为0，防止重复计费及语义重试。

固定前置为13条独立messages：任务系统标准、完整Skill与规则及六锚、助手确认、5组问答few shots。20个payload均逐项验证前13条相同，未把每轮候选反馈不断追加到这个前缀。用户任务和本轮卡文本放在之后，适用服务端前缀缓存。实际缓存103,936 prompt tokens；不是将整个输入都算命中。

| 阶段 | 请求 | 输入范围与职责 | 验收 |
|---|---:|---|---|
| pool-screen | 14 | 六共同锚＋每批最多48张新怪物，固定shuffle seed20261018；提名附条件和真实文本 | 14响应内层可解析；不自动批准候选 |
| coverage_repair | 1 | 只补原输出遗漏的49个ID | 49行恰好覆盖要求ID |
| 全表draft | 2 | 汇总候选后独立起草Bookshelf与Librarian牌组 | 均拒绝：JSON不合法且提取counts后均26张 |
| bounded-review | 3 | root完成25张后的限定反例和神器审查，最多2500输出tokens | 仅作为待核验意见；存在语义和非法替换错误 |

首轮输出pool_01遗漏#144、夹入两个额外ID；pool_10未按约定提供screen字段，被视为48张缺行。没有将“有返回”视为完成，补充任务只修49个遗漏。六锚由每批共同检查，非锚665张完成覆盖；原始异常行及额外ID仍保留于证据。

观察到的错误及处理：

- 把Fire Fountain的格子附魔当潜在正收益：独立读取`enchant-the-flame-desc`，明确是己方负债；最后首测移除它，另保留受控比较表。
- 忘记TOKEN与Generated独立、误称Lib随机生成法术会阻断Book：按Skill定义纠正；新生成牌不影响这两个非Generated条件。
- 面对B仅2 Lib重复，仍泛称抽到一张不一定就绪：本构筑且无非Generated改库时，剩余库同名至多1，条件确定成立；用组合程序核验。
- B审查提出Piranhas→Normal NPC或Napstablook→Shyren，但B已各有这张单例：拒绝这两条替换，避免新重复阻塞Lib。
- 错报Napstablook费用、属性，以及把Flame消除后的伤害继续重复计算：与原始卡面及附魔文本逐项对照，不采用这些说法。
- 两次大候选上下文起草均26张、偏低ID旧牌，还伴随格式损坏：不修成“模型成功”，完整记录拒绝；转用root自主构筑、短输出反例审查。无法由一次现象证明位置偏差的因果，但足以否定直接交付。

本次总usage：prompt325,289、completion79,287、cache103,936。没有胜率样本或实际牌组对局；这些tokens不能作为性能证据。

`api-evidence.json.gz`包含各阶段manifest、固定前缀、payload、attempt、raw、可解析候选、拒绝/部分提取物、summary与coverage audit。`api-evidence-index.json`列出每项原始字节SHA256，可逐项验证。拒绝输出也保留，任何卡片措辞以仓库快照及`selected-source.json`为准。

在云端复现无需重新请求API；先运行确定性producer。若需要再次调用，`pool_screen.py`接受helper路径；其他两个本地辅助runner仍指向用户原来的Windows客户端位置，应先复制为新批次并配置当前环境客户端。不要把本地密钥文件提交到仓库，也不要覆盖已有attempt来强行重跑。
