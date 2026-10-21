# Undercards 通用 Value 建模

研究首先遵循[整体研究原则](RESEARCH_PRINCIPLES.md)。主Agent自主形成对随机、部分可观测、双方策略相互作用的整体认识，再选择能检验关键未知的方法；不以逐卡端点、模拟器支持名单或用户举例决定长期范围。历史理论已有正确框架，执行曾偏向累计局部评分，本次纠正与证据标准已记录并由根目录[AGENTS.md](AGENTS.md)接续。

现有工具包括[逐卡多维账本](analysis/card-assessment/2026-10-20/README.md)、[随机联合开局](analysis/card-comparison/2026-10-20/joint-opening/README.md)及有限信息研究。755卡目录、78个条件档案与旧DeepSeek材料是辅助证据，不是完整实战强度榜或整体目标进度。暂停搜索推荐完整卡组；方法、结构与候选选择均可按研究证据调整。当前工作状态见[CURRENT_CHECKPOINT.md](CURRENT_CHECKPOINT.md)。

最新研究：[随机资源、相互提防与模型内终局](analysis/strategic-model/2026-10-20/REPORT.md)。机制角色模型将开局到牌/资金、付费惩罚与恢复连接起来，随后依据反例修订评价目标，并在新牌序下继续到模型内全部HP终局。结果表明提前击杀、截止存活和最终获胜不可互换；当前不按单一生命差默认推荐通用强度。[程序/数据入口](analysis/strategic-model/2026-10-20/README.md)保留全部原始记录和边界，尚不能外推真实费用核心或全卡池榜。

低成本、可解释、对数值差异敏感的随从评价研究。主智能体负责数值模型；DeepSeek承担批量机制拆解、跨批检查、反例提案和代码审查。当前模型是有明确边界的启发式报价程序，仍不是完整卡池强度榜。

2026-10-19 更新：当前续作分支为 `research/local-method-lab-20261018`，包含 `f75d98c` 及此前全部云端提交；新增方法研究和构筑实验，见 [恢复核对记录](analysis/recovery-review-2026-10-19.md)。后期旧实验缺口仍不重跑补齐；当前通用评分按未实战校准的启发式解释，详见 [评估标准](analysis/monster-value-heuristic/evidence-status-2026-10-17.md)。输出的 `assessment_evidence` 区分机械支持与实证可靠性。

同日补传 `1a50ed9` 已接入：三份旧内核及测试的历史快照、原始变更和未应用补丁已归档，见 [补传说明](analysis/recovery-supplement-2026-10-19.md)。它们不覆盖当前模型，不代表完整旧实验已恢复。

先读 [CURRENT_CHECKPOINT.md](CURRENT_CHECKPOINT.md) 接续研究；云端配置见 [CLOUD_SETUP.md](CLOUD_SETUP.md)。规则在 `skills/undercards/`，最新工具与报告在 `analysis/card-comparison/`，早期启发式成果在 `analysis/monster-value-heuristic/`。

Python 3.11+；基础账本/开局工具只需标准库，新策略矩阵分析另需NumPy、SciPy，导图需Matplotlib。克隆后的首次启动：

```sh
python tools/restore_stage_evidence.py
```

早期数值结果、接口原始批次和研究证据保存在 `research-archive/stage-evidence.zip` 中；恢复工具写入原始相对路径，不重跑实验。当前活跃源码和新结果直接在 Git 中。较早完整对局模拟的大型轨迹未迁入；不能声称此归档包含后来缺失的实验。已有有效检查无需每次启动重跑。

常用命令：

```sh
python analysis/monster-value-heuristic/unified_value.py --compact --output results/updated-pool.json
python analysis/monster-value-heuristic/build_resource_comparison.py --trials 1000 --output results/resource-comparison
```

API调用另需云端网络配置和 `TENCENT_API_KEY`。接口脚本为 `tools/test_llm_api.py`；密钥不在仓库。冻结的旧批次、失败输出和未支持机制不得被静默改写或当作已完成定价。

以下是早期阶段记录，不是当前策略研究的请求/验证统计：离线182项检查通过（详见`stage-verification.json`）；当时DeepSeek队列完成12请求：8批64张新卡、2个反例任务、2个模型审查任务；12个HTTP回复均正常结束，只有3任务整体结构通过，语义仍需复核。使用641553 tokens，接口报告459904缓存输入tokens；原始输出与失败分类完整保留。本轮策略研究新API请求为0。

研究派发支持固定完整知识前缀、首任务预热后4并发、冻结来源、持久化恢复及独立复核。新一轮使用新目录；旧轮无缺失任务时不会再请求API：

```sh
python analysis/monster-value-heuristic/deepseek_research_queue.py merge --queue analysis/monster-value-heuristic/research-runs/round01
```
