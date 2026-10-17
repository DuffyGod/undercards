# 研究续作检查点

**2026-10-17 更新：先读 [CURRENT_CHECKPOINT.md](CURRENT_CHECKPOINT.md)。** 当前可恢复内容与历史缺失产物的边界、证据复用规则及保存/恢复方法均在该页。下面是 2026-10-08 的原始记录，不代表已找回后续版本。不要无变化地重跑已有验证。

阶段日期2026-10-08。本文件用于云端新任务承接本地长期研究，不能视为目标已完成。

## 用户目标与硬约束

持续迭代低成本Undercards通用Value评分程序及可靠报告。以共享启发式Gold价格、时机、兑现条件、对手回应、构筑资源适配为主；不用完整对局模拟器作为短期前提。原凸包标准高估适用面窄和缺陷大的卡，必须改进敏感度和稳定性。

7/7相对6/7的额外ATK应明显低于旧0.77G；过量攻击贬值，击杀线可产生局部跳变。Glyde前期沉默的损失与后续压制、Terakota Archer的主动兑现和反击时机需机制级建模。禁止为Glyde、Archer、Piranhas、Broken Car、Blockler B、Lesser Dog或旧强牌名单专拟合。

四类对手任务：aggro（Ice Cap/Vulkin型攻击频率及自身HP）、control（Justice解场转化、抽牌质量/格子）、combo（压缩启动回合、格子和收益被组合技抵消）、midrange（双方共同高质量交换，可加入Soul）。规则快照2026-10-05，不等于实时meta；用户明确不要求不存在的单卡实战分析数据。

DeepSeek用于繁重辅助，用户明确要求更多派发且调用尚未饱和。每次一批卡、共同检查项/跨批复核、足够规则与fewshots，完整固定前缀独立复用。数值、概率先验和最终结论由主智能体决定。可派子智能体并行验证。

## 现有可复算工具

- `score_cards.py`：377个4–7费印刷身材的共同参考；Aaron6/5仅锚5 model-G；有效ATK含E[min(A,H)]与阈值，非强牌标签。
- `context_value.py`0.4.0：共享逐情境账本。纯增长、属性差、即时效果、现金和Dust实际减费等；复杂整卡仍partial。
- `combat_increment.py`/`coupled_magic.py`：一个当前Haste动作、一个合成回应、一个后续普通动作。Magic与早攻击共同选择；所有选择遵守同一目标域；终局拒绝Gold价格；其它友军尚未主动防守。
- `unified_value.py`0.3.1：主入口，默认72共同状态；有限等待0–3回合，费用一次扣除，满手额外烧牌成本；未支付状态不删后重权。
- `resource_profile_bridge.py`0.2.0：完整Gold/手数联合频率与独立场面交叉，每桶代表仅诊断；不是候选在手或真实比赛概率。
- `candidate_resource_observations.py`：物理副本的未抽/在手/烧牌/此前已用，以及在手条件Gold/手数频率；只观察费用策略，不给先前已用候选零分。已与原资源trace和种子核对。
- `finite_conditions.py`：当前区域和实际金币支出的有限Need/阈值/存活谓词，unknown不是true；尚未自动融入完整定价。
- `payment_frontier.py`：显式已知手牌报价的付款节省＋解锁净机会，不能另加整张身体。
- `batch_annotate.py`、`semantic_v6.py`：旧标注及冻结来源；结构合并不等于语义/数值批准。接口已便于云端读取。
- `deepseek_research_queue.py`：已实跑12请求（64新卡的8批＋2反例＋2模型审查），首任务预热后4并发。29条固定完整知识/示例前缀；12原始HTTP回复均正常stop，3任务整体结构通过；其余外壳/schema/引用问题不能误报为网络失败。下一轮按统一规范分派更多可复核的辅助工作，不重试直到一致。

## 已完成证据

1. `unified-pool-v03.json`完整运行404张4–8G普通怪物，404唯一ID，所有卡72状态/权重1；17张受限完整文字可报价、387张partial，尚不能作为全卡池强度榜。
2. `resource-comparison-v04/`三种抽象25牌费用分布，各1000次、相同deploy策略/seed/对手先验；三套17卡比较全部完成。Glyde差−2.485/−1.780/−1.229 model-G，仅资源适配，不能认定高费牌组更强。
3. `candidate-resource-demo/`是中费抽象分布中的两枚6费物理副本，演示身份条件统计，不是真实牌组推荐。
4. 历史151项检查通过；新增候选观察/有限条件各10、研究队列8、云端恢复3项，最终完整182项检查通过；仍以`stage-verification.json`实际tests_run及source hashes为准。
5. V6未见文本16张、四批网络成功，总80714tokens；结构通过但20探针存在真实目标域错误。一致性退出1不是没启动；保存错误，不重抽样直到一致。

详读`方法与验证-v04.md`、`resource-deck-review.md`、`coupled-integration-review.md`、`coverage-priorities-v03.md`、`holdout-v6-review.md`。

## 下一阶段关键问题

先读`growth-window-plan-review.md`。如果F是包含普通寿命的根身体价格，直接加U(grown)-U(printed)会把普通属性的正常攻击收益重复计价。推荐永久grown普通身体Pref归一：F(grown)+(U(actualGrowth)-U(Pref))+(U(growthKeywords)-U(actualGrowth))；只在可靠域实现。受伤HP modifier被沉默后的重置裁定未明，不能猜。原固定增长(1-q)*ΔF尚未改成这个新窗口。

机制覆盖按可复用对象/条件/选择器、生成物与属性覆盖、双边/可选抽牌、手牌费用子集、一次事件依赖推进。多数Add/Summon引用物自己有复杂文本，不能只用引用身体假装完整价格。Archer明确生成2/3 Clover，引用基础1/1不得代替；普通击杀与Bullseye精确击杀分开；Dust与Erase分开。

当前合成回应缺多敌攻击频率、真实反制随从本体和全额控制转化。阶段权重、平均抽牌净质量与事件概率均为先验；候选持有概率不直接乘进公共质量标尺，此前已使用也不等于失败状态。先独立展示，再设计可检验的构筑用值，避免递归自证。

## 恢复与继续

从仓库根运行`python tools/restore_stage_evidence.py`，再运行`python tools/verify_stage.py`。仅实际失败、来源变化或新增机制需要重跑检查；不要无缘由重做已保存API请求。旧大型对局模拟轨迹未迁移，本阶段改进不依赖它们，历史报告已保留。

云端任务先确认TENCENT_API_KEY和目标域名配置，然后按研究队列的已保存状态续跑，默认4并发、根据429/时延实际反馈调整。固定提示标准不随批次改变，API返回仅为待复核材料。最终成果必须比17张窄模板覆盖更接近通用随从质量评价；不能把局部green tests当长期目标完成。
