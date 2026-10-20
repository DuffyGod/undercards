# Undercards 通用 Value 建模

当前入口：[Agent主导逐卡多维模型](analysis/card-assessment/2026-10-20/README.md)与[数值标准/携带门槛](analysis/card-assessment/2026-10-20/MODEL.md)。研究流程已纠正为从全卡池读卡、推演用途和替代候选，再由通用端点账本定价/反证；不要求先实现对局机制。已有755卡目录、49卡条件档案和197卡旧DeepSeek材料索引，未审阅项不冒充裸体整卡分。DeepSeek新用途协议已备，当前凭据缺失，未发新请求。[联合开局](analysis/card-comparison/2026-10-20/joint-opening/README.md)及此前研究保留为辅助证据；暂停搜索推荐完整卡组。

低成本、可解释、对数值差异敏感的随从评价研究。主智能体负责数值模型；DeepSeek承担批量机制拆解、跨批检查、反例提案和代码审查。当前模型是有明确边界的启发式报价程序，仍不是完整卡池强度榜。

2026-10-19 更新：当前续作分支为 `research/local-method-lab-20261018`，包含 `f75d98c` 及此前全部云端提交；新增方法研究和构筑实验，见 [恢复核对记录](analysis/recovery-review-2026-10-19.md)。后期旧实验缺口仍不重跑补齐；当前通用评分按未实战校准的启发式解释，详见 [评估标准](analysis/monster-value-heuristic/evidence-status-2026-10-17.md)。输出的 `assessment_evidence` 区分机械支持与实证可靠性。

同日补传 `1a50ed9` 已接入：三份旧内核及测试的历史快照、原始变更和未应用补丁已归档，见 [补传说明](analysis/recovery-supplement-2026-10-19.md)。它们不覆盖当前模型，不代表完整旧实验已恢复。

先读 [CURRENT_CHECKPOINT.md](CURRENT_CHECKPOINT.md) 接续研究；云端配置见 [CLOUD_SETUP.md](CLOUD_SETUP.md)。规则在 `skills/undercards/`，最新工具与报告在 `analysis/card-comparison/`，早期启发式成果在 `analysis/monster-value-heuristic/`。

Python 3.11+，离线工具只需标准库。克隆后的首次启动：

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

本阶段离线182项检查通过（详见`stage-verification.json`）。新增DeepSeek队列已实际完成12请求：8批64张新卡、2个反例任务、2个模型审查任务；12个HTTP回复均正常结束，只有3任务整体结构通过，语义仍需复核。使用641553 tokens，接口报告459904缓存输入tokens；原始输出与失败分类完整保留。

研究派发支持固定完整知识前缀、首任务预热后4并发、冻结来源、持久化恢复及独立复核。新一轮使用新目录；旧轮无缺失任务时不会再请求API：

```sh
python analysis/monster-value-heuristic/deepseek_research_queue.py merge --queue analysis/monster-value-heuristic/research-runs/round01
```
