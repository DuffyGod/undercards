# Undercards 通用 Value 建模

低成本、可解释、对数值差异敏感的随从评价研究。主智能体负责数值模型；DeepSeek承担批量机制拆解、跨批检查、反例提案和代码审查。当前模型是有明确边界的启发式报价程序，仍不是完整卡池强度榜。

先读 [CONTINUATION.md](CONTINUATION.md) 接续研究；云端配置见 [CLOUD_SETUP.md](CLOUD_SETUP.md)。规则在 `skills/undercards/`，当前工具与报告在 `analysis/monster-value-heuristic/`。

Python 3.11+，离线工具只需标准库。克隆后的首次启动：

```sh
python tools/restore_stage_evidence.py
python tools/verify_stage.py
```

完整数值结果、接口原始批次和研究证据保存在带哈希的 `research-archive/stage-evidence.zip` 中；恢复工具校验每个条目后写入原始相对路径。当前活跃源码和报告直接在仓库中。较早完整对局模拟的大型轨迹留在原本地工作区，不是本阶段云端运行所需输入；阶段归档清单记录实际内容。

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
