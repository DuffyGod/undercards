# 独立实现复核：攻击前沿、实体替换与信息边界

2026-10-30。在正式训练前读取`tactics.py`、`engine.py`、`test_tactics.py`和`PROTOCOL.md`。本文件作者没有改动任何源码，没有重跑旧正式对局。结论：**没有发现需要阻止当前冻结的数值规则、付费或隐藏信息错误**；这是有限实现复核，不是完整正确性或实战有效性证明。

## 逐项核对

- 攻击执行采用同时伤害，死者即时移除，攻击者只能使用一次；搜索允许第一次未击杀、第二次补刀。就绪标记明确排除召唤失调单位。动作以稳定原索引表示，再映射到真实UID，不会因中途死亡而移位。
- focus的搜索目标按攻击、当前HP、最低原索引破同分；决策先按UID排序，恰好对应基础引擎按攻击、当前HP、最低UID的强制目标。不能在未来增加自由目标牌时继续复用这个假设。
- 搜索只接收数值元组、己方持有且付得起的回应和公开HP等。敌方手牌、洗牌种子、牌序未进入选择。己方候选卡面由参数传入，敌方只看到已经在场的实际攻防；没有通过候选身份读取敌手。
- 己方候选在原UID0/1/2上替换手与库，未重新洗牌，也不按是否抽到决定替换。对手仍用原角色牌库。候选费用同时用于合法付款与部署选择；入场实际攻防用于战斗与脆弱阈值，未继续误用2/2模板。
- 基础回合顺序、收入、留存、Integrity奖励、Kindness处理、自然抽牌、疲劳与生命终结代码与旧引擎相同。候选实际付款、手牌移除、格子、累计支出/打出计数均进入原账本。源码复制意味着未来若只改其中一处，仍有漂移风险；目前没有发现这种数值差异。
- 新增`attack_frontier`保留旧回应决定，再只对攻击做协调搜索；它与完整`frontier_board/race`不同。这个消融可以区分攻击能力与联合施法的一部分影响；攻击改变公开目标后，使旧门槛随后触发是正常的策略路径差异，不是必须强行消除的混杂。

## 对“精确”与强度结论的限制

精确的是声明域内的普通攻击/至多一次回应的数值转移及枚举；端点偏好仍是启发式。搜索没有定价花掉回应后失去的部署/回复选择。一个动作执行后会重新规划，可能再用下一张回应，所以“每次搜索最多一张”不等于“每回合最多一张”，也不等于已经完整搜索多张组合。

Kindness只把回合末英雄+1计入当前可见压力约束；其治疗/增血对单位后续作用未计进端点排序。疲劳历史、尚未打出的己方回复与未实现即时干预同样未计。协议已公开这些遗漏，不能把“安全端点”说成真实完整存活保证。

攻击者/目标对称裁剪在当前无额外触发域内按相同攻防合并。下面有限oracle检查支持其数值端点保留，但不是对任意四格位置的证明。若加入种族、攻击触发、死亡触发、位置技能或其他身份效应，必须重新检查，不能只沿用该裁剪。

当前`candidate_wait`是**回合开始时手中存在候选**的回合数，立即打出也计一次；`candidate_slot_blocked_turns`是该时刻满格，随后通过攻击腾格仍可能打出。它们不是卡牌张数×等待回合，更不是已定价的机会成本。协议已经这样限定，后续表格也应保留这一叫法。

`greedy_trade`与联合前沿的收益差不能全归因于攻击协调；后者还会改变回应时机。`frontier_durable`另改部署顺序。只有宣告并比较这些差异，才适合讨论身体在不同打法下兑现如何变化。host含角色聚合，不能称现实合法构筑；选择出的有限混合也不是全游戏均衡。

## 新独立探针与原始结果

所有探针都在本轮新造小状态上执行。没有重新生成旧正式10000/20000/30000段或本轮正式训练/评价牌序。

第一项对18个确定性位置、无回应/群伤/单杀三种模式，逐条把搜索输出的计划交给基础`Game.attack/play`重放。为避免探针中提前结束使完整攻击叶没有定义，英雄HP设1000；这只核对攻击/回应转移，不检验完整游戏终结。单位使用非连续UID，覆盖索引映射。

原始stdout：

```json
{"new_deterministic_positions":18,"response_modes":3,"state_mode_pairs":54,"frontier_plan_engine_replays":118,"status":"passed","old_official_runs":0,"seed":935001,"scope":"all emitted plans in these finite probes; not proof of all states or full-policy optimality"}
```

第二项使用与前沿实现独立的穷举：直接复制基础Game，尝试每一个合法攻击/回应顺序，不做对称裁剪；然后把数值相同的单位身份归一化，与前沿的数值端点集合比较。四个手工位置覆盖重复攻防、focus同分目标和未就绪单位。12组状态/模式的81个数值端点全部一致。

原始stdout：

```json
{"new_handcrafted_positions":4,"response_modes":3,"exhaustive_engine_oracle_pairs":12,"numeric_endpoint_sets":81,"status":"passed","old_official_runs":0,"scope":"two-unit symmetry, disabled readiness and forced-focus ties; endpoints compared modulo interchangeable unit IDs"}
```

118与81是检查过的计划/端点数量，不是独立对局或模型准确率。新API调用0。上面两项可从仓库根目录按下面脚本复现；保存源码便于审阅，不要求接续时重复运行。

```python
import sys, random, copy
from pathlib import Path
sys.path.insert(0, str(Path('analysis/strategic-model/2026-10-30').resolve()))
from engine import Game, Config, Card, Unit, Policy
from tactics import frontier

def make(own, enemy, spell, seed):
    g = Game('wide', seed, Config(response_kind=spell or 'sweep'),
             (Policy('a'), Policy('b')))
    a, b = g.players
    a.hand = [Card(999, 'response')] if spell else []
    a.cash = 5
    a.hp = b.hp = 1000
    a.units = [Unit(100+7*i, 'small', atk, h, h, r)
               for i, (atk, h, r) in enumerate(own)]
    b.units = [Unit(200+11*i, 'small', atk, h, h, False)
               for i, (atk, h) in enumerate(enemy)]
    return g

rng = random.Random(935001)
checked = 0
for case in range(18):
    own = tuple((rng.randint(1,6), rng.randint(1,7), rng.choice((True,False)))
                for _ in range(case % 4))
    enemy = tuple((rng.randint(1,6), rng.randint(1,7))
                  for _ in range((case // 4) % 4))
    for spell in ('', 'sweep', 'focus'):
        for oh, eh, damage, cast, plan in frontier(own, enemy, spell, 3):
            g = make(own, enemy, spell, 935001+case)
            for action, i, j in plan:
                if action == 'response':
                    g.play(0, 999)
                else:
                    g.attack(0, 100+7*i, -1 if j == -1 else 200+11*j)
            a, b = g.players
            ah = tuple(next((u.h for u in a.units if u.uid == 100+7*i), 0)
                       for i in range(len(own)))
            bh = tuple(next((u.h for u in b.units if u.uid == 200+11*i), 0)
                       for i in range(len(enemy)))
            assert (ah, bh, 1000-b.hp, not a.hand) == (oh, eh, damage, cast)
            checked += 1
assert checked == 118

cases = [
    (((2,2,True),(2,2,True)), ((5,4),(5,4))),
    (((5,7,True),(2,2,True)), ((5,6),(2,2))),
    (((3,3,True),(3,3,True)), ((3,3),(3,3))),
    (((5,7,True),(3,3,False)), ((5,7),(5,7))),
]
total = 0
for n, (own, enemy) in enumerate(cases):
    for spell in ('', 'sweep', 'focus'):
        expected = set()
        def walk(game, cast=False):
            a, b = game.players
            ready = [u for u in a.units if u.ready]
            if not ready:
                expected.add((tuple(sorted((u.a,u.h) for u in a.units)),
                              tuple(sorted((u.a,u.h) for u in b.units)),
                              1000-b.hp, cast))
            for u in ready:
                for target in [-1] + [v.uid for v in b.units]:
                    nxt = copy.deepcopy(game)
                    nxt.attack(0, u.uid, target)
                    walk(nxt, cast)
            if a.hand and b.units:
                nxt = copy.deepcopy(game)
                nxt.play(0, 999)
                walk(nxt, True)
        walk(make(own, enemy, spell, 936001+n))
        actual = set()
        for oh, eh, d, c, plan in frontier(own, enemy, spell):
            actual.add((tuple(sorted((u[0],h) for u,h in zip(own,oh) if h>0)),
                        tuple(sorted((u[0],h) for u,h in zip(enemy,eh) if h>0)),
                        d, c))
        assert actual == expected, (n, spell)
        total += len(expected)
assert total == 81
print('54 replay pairs / 118 plans and 12 oracle pairs / 81 endpoints passed')
```

## 冻结判断

当前未发现必须修复后才能训练的实现错误。正式结果仍须检验：协调策略是否只利用较弱对手；改身体后部署偏好是否掩盖数值变化；共同信息与重选政策后，结论是否在新牌序、相同对手列上保持。有限探针与审阅通过不能提前回答这些问题。
