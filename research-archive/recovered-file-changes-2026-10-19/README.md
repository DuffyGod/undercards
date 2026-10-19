# 2026-10-19：从导出记录补传源码材料

这是**文件变更记录的恢复归档**，不是paid0.32/API0.34完整运行环境，也不是原实验结果的重新生成。用户要求仅补传必要记录和源码，不上传本地大型轨迹。

来源为用户提供的`response.json`（2,744,249字节）。程序在本地解析，仅输出索引、计数和定向片段；没有把原始聊天全文载入交接文档。归档保留全部930条文件变更，非文件变更消息用占位项替代，原turn/item/change坐标不变。原响应的大小及SHA256见 [manifest.json](manifest.json)。

## 补传内容

`restored-source.tar.xz`共598个成员，包括：

- 234份新增初始快照，涉及198种原始文件名。
- 234份精确匹配补丁回放后的快照。
- 125条不能精确应用的原始补丁。
- 原还原清单及说明、原还原工具、仅含文件变更的可重放记录、完整文件索引。

已按导出记录重新做**文本转换**，593份快照／未应用补丁与本地已有还原件逐字节一致；全部598个归档成员已验证。没有导入这些快照中的研究代码，没有运行卡牌实验或旧测试套件。这里的文件完整性验证不能继承历史“734项检查”。

## 云端可直接查看的六个重点文件

原`.py`文件名和原始内容保留在归档的`restored-added-files/latest/`。下面是相同字节的文本镜像，避免把未验收历史测试混入当前测试发现流程。

| 文件 | 记录内VERSION字面量 | 已回放补丁 | 未处理补丁 |
|---|---|---:|---:|
| [board_tactics.py](selected/board_tactics.py.txt) | observed-board-adversarial-tactics-0.2.0 | 13 | 16 |
| [paid_board_tactics.py](selected/paid_board_tactics.py.txt) | declared-paid-board-search-0.5.0 | 29 | 30 |
| [combat_event_extensions.py](selected/combat_event_extensions.py.txt) | physical-combat-events-0.1.0 | 3 | 0 |
| [test_board_tactics.py](selected/test_board_tactics.py.txt) | — | 5 | 0 |
| [test_paid_board_tactics.py](selected/test_paid_board_tactics.py.txt) | — | 12 | 1 |
| [test_combat_event_extensions.py](selected/test_combat_event_extensions.py.txt) | — | 4 | 0 |

六个文本镜像均能语法解析；**没有待处理补丁不等于最终版本已恢复或依赖齐全**。例如事件模块引用的board接口可能来自尚未完整回放的后期修改。报告所述board0.6.1、paid0.32不能由这些VERSION不同的快照替代。

## “108张／734项”的可追溯程度

[historical-combat-report.md](historical-combat-report.md)是导出记录`latest/README__e000902.md`的原文字节副本。它记载：

- 正文编译支持104→108，新增#17、#163、#291、#526；不是实战有效卡牌数量。
- 734的历史构成为694项当前源码检查及40项来源相同复用；报告声称实际执行709次，含一次失败后15项模块重跑。这里没有重新认证这些数字。
- 引用了`research-runs/combat-event-v01/`、`inventory.json`、`regression.json`、`comparison.json`、`quotes.csv`等输出；归档中的生成、修复和发布脚本也保留了这些名称。

导出记录中没有这些完整原始实验文件的字节。三个名为`validation-history.json`的新增快照只是失败／修正历史，不能代替完整逐项检查收据。**仍不能声称找回108张全清单、734项逐项证明或对应完整轨迹。**

## 恢复边界

原记录仅有文件名，缺原目录；同名多次创建保留各自`__eNNNNNN`身份，不覆盖合并。清单中的176条修改没有创建基础，原diff完整保留在`file-change-records.json`，没有凭空构造缺失基础。73条已应用补丁省略了最后共同上下文，工具只处理实际提供的文本，不猜缺行。

不要把本归档直接覆盖到当前评分器，也不要为复现历史数字重跑旧实验。当前工作仍按方法和构筑报告推进，本归档仅补足源码考据和可恢复材料。

未读取或打包本地`analysis/monster-value-dynamic/`大型轨迹；不使用它们填补云端缺失实验。未包含API凭据或完整聊天消息。

## 离线查看／提取

从仓库根校验，无需密钥、网络或第三方包：

```sh
python research-archive/recovered-file-changes-2026-10-19/verify_bundle.py
```

需要源码原文件时提取到**不存在的新目录**，工具拒绝覆盖已有目录，先验证所有成员再写入：

```sh
python research-archive/recovered-file-changes-2026-10-19/verify_bundle.py --extract-to recovery-inspection-20261019
```

提取后的`file-index.json`列出每份文件大小与SHA256，并为234份快照关联原始记录坐标、已回放／待处理补丁。`restored-added-files/manifest.json`保留原始恢复记录。`restore_added_files.py`只用于从`file-change-records.json`重放文件文本，不负责运行实验。`prepare_bundle.py`用于本地准备归档，输入路径均可通过参数指定；云端读取／验证现有归档不依赖Windows路径。
