# 怪物质量构筑实验

先读 [REPORT.md](REPORT.md)：完整25张主表、替代表、条件性强度数据及局限。

- 首测：[A_early.json](A_early.json)，Justice＋Health/Power，双Bookshelf，6张2G。
- 单例补牌对照：[B_library_singletons.json](B_library_singletons.json)，只有双Librarian重复，单Bookshelf。
- 更重即时攻击对照：[A_quality_bookshelf.json](A_quality_bookshelf.json)。
- 同费清理格子负债：[A_safe_slots.json](A_safe_slots.json)。
- 与首测同25张、换SOUL：[A_kindness.json](A_kindness.json)。

结果索引：

| 文件 | 内容 |
|---|---|
| [structural-comparison.json](structural-comparison.json) | 费用、抽样、复制条件、Gold留存 |
| [answer-access-compact.json](answer-access-compact.json) | 报告使用的主要需求覆盖行 |
| [answer-access.json.gz](answer-access.json.gz) | 完整864行访问网格，无需API即可重算 |
| [exchange-ledgers.json.gz](exchange-ledgers.json.gz) | 24张卡×6身体×3手数的全部可选短线 |
| [worked-examples.json](worked-examples.json) | 四条已核对顺序及无阻挡伤害时钟 |
| [selected-source.json](selected-source.json) | 所选卡、引用物、Justice/Kindness法术、相关神器及规则原文 |
| [API-AUDIT.md](API-AUDIT.md) | 辅助模型使用范围、失败与拒绝案例 |
| [api-evidence-index.json](api-evidence-index.json) | 93项API证据SHA256及usage |
| [api-evidence.json.gz](api-evidence.json.gz) | 无损原始payload、返回、失败与审计材料 |

确定性复现只需Python标准库，不需要密钥：

```powershell
python -X utf8 analysis/deck-lab/2026-10-18/build_decks.py
python -X utf8 analysis/deck-lab/2026-10-18/evaluate_decks.py
python -X utf8 analysis/deck-lab/2026-10-18/worked_examples.py
python -X utf8 -m unittest discover -s analysis/deck-lab/2026-10-18 -p 'test_*.py' -v
```

压缩证据中的每个文档带相对路径、字节数、SHA256和原始UTF-8文本。先解包到临时位置核验，不覆盖当前产物。API runner已有attempt则不会重复发送；需要新研究应新建批次并冻结其输入。

本目录为新增的构筑方法分支，不修改旧机制引擎、恢复材料或云端开发路径。结果是可检验研究候选，不是天梯胜率证明。
