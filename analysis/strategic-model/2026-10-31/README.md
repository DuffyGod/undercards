# 共享机器学习主线

本目录把行动策略与终局价值变为共享可训练模型，同时保留规则合法性和机制组合。范围与预先验收见[协议](PROTOCOL.md)；实际结果写入`experiment-v01/`，后续报告不会把训练上涨当泛化通过。

程序只依赖Python3.11+和NumPy。旧研究源码/数据不改动。新运行默认拒绝覆盖，并检查源、协议、训练产物已提交。

```sh
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s analysis/strategic-model/2026-10-31 -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 python analysis/strategic-model/2026-10-31/study.py prepare --output analysis/strategic-model/2026-10-31/experiment-v01
# 提交设计后执行train；提交checkpoint后执行evaluate。
OPENBLAS_NUM_THREADS=1 python analysis/strategic-model/2026-10-31/study.py train --output analysis/strategic-model/2026-10-31/experiment-v01
OPENBLAS_NUM_THREADS=1 python analysis/strategic-model/2026-10-31/study.py evaluate --output analysis/strategic-model/2026-10-31/experiment-v01
OPENBLAS_NUM_THREADS=1 python analysis/strategic-model/2026-10-31/study.py replacements --output analysis/strategic-model/2026-10-31/experiment-v01
```

- `mechanisms.py`：机制描述、严格整段卡面编译、伤害与沉默原语。
- `environment.py`：复用旧随机资源内核，给所有政策提供相同合法行动和公开观察。
- `features.py`：无卡名/ID的局面与行动特征。
- `learner.py`：共享策略/价值网络、行为模仿、PPO、冻结与恢复。
- `agents.py`：因果政策和公开斩杀搜索、六种旧规则的合法性适配。
- `records.py`：执行前决策日志及HP终局标签，拒绝把旧摘要当训练集。
- `study.py`：先冻结设计，再训练、独立评价和相同模型的实体替换。

host依旧含聚合角色，无换牌/神器/种族/死亡链等完整覆盖；沉默对修改属性的清理按显式假设处理。本轮不宣称真实环境胜率或全卡池评价已完成。
