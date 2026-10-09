# V5 pool batch_000～015 独立语义审查

审查日期：2026-10-08。只读检查 `annotation-runs/pool-v5-complete404` 的已完成16个批次；未调用API，未修改程序。以下结论以这些冻结批次为范围，不将尚未运行的后续批次算作模型失败。

## 结论

20／49探针的**数值与typed主体语义在全部16批一致**。20的3种完整signature来自两条违反已给定K007前提的“ALL目标范围尚未知”，不来自伤害、目标类型、次数或时点改变。49完整signature只有一种。因而这次没有证据说应重抽样来寻找更好的探针数值标准。

但探针稳定并不能验证其它机制。抽查32张非探针，发现数值公式、触发类型、受益主体、同一互斥分支多动作、效果遗漏和沉默暴露等系统性问题。优先修字段表达力、规范与确定性审核规则，然后对受影响条目集中修订；不建议整批重新生成。

当前输出不能直接进入定价。格式通过与语义正确必须分开；`unresolved=[]` 也不代表typed字段已经完整表达卡面。

## 可复算范围和数量

- 16批，每批10条：160条观测，130张不同卡，其中128张非探针。
- 对冻结 `annotator_source.py` 的枚举与 `validate` 函数作只读AST提取，逐行重新验证：146条格式／现有检查通过观测，119张不同卡；14条失败观测详列于下文。
- merger输出的 `accepted_count=118`：比上述119少20这一个探针，因为它仍有完整signature分歧。故这个数不是纯粹的字段合法性计数。
- merger仅接收到20的14条、49的15条合规观测：20在008有额外字段、014缺notes；49在014缺notes。审查另外读取这些原始观测，确认它们typed核心仍一致。
- `known_rule_resolutions=[]`，两条ALL疑问没有被规则解析器消除。不能把“resolver已执行”当作已经正确归一化。

逐行校验复核先使用卡面快照作为exact-text依据；探针signature按冻结源码字段构成复核。没有通过重新请求LLM改善任何条目。

## 两个探针逐批审计

核心typed字段顺序：kind／trigger／target／amount／basis／stat／count／repeat／choice／card_ref。

- **V**：`damage / magic / other / 2 / fixed / none / 1 / none / null / null`；condition_codes=`target_exists`，timing=`immediate`，silence=`none`。
- **G**：`buff / magic / self / 1 / hand_size_after_play / both / 1 / none / null / null`；condition_codes=`hand_size`，timing=`immediate`，silence=`body`。

| 批次 | 20核心 | 49核心 | 真正差异及字段问题 |
|---|---|---|---|
| 000 | V | G | 无；condition／notes不同措辞不进入数值标准 |
| 001 | V | G | 无 |
| 002 | V | G | 20增加“ALL但卡面未明确怪物或玩家”疑问；已给定K007前提，不应重新列未知 |
| 003 | V | G | 无 |
| 004 | V | G | 20增加另一措辞的ALL范围疑问；仍是同一已知前提问题 |
| 005 | V | G | 无 |
| 006 | V | G | 无 |
| 007 | V | G | 无 |
| 008 | V | G | 20额外 `target_metadata` 字段，违反冻结schema；核心语义没有改变 |
| 009 | V | G | 无 |
| 010 | V | G | 无 |
| 011 | V | G | 无 |
| 012 | V | G | 无 |
| 013 | V | G | 无 |
| 014 | V | G | 两个探针均缺notes；核心语义没有改变 |
| 015 | V | G | 无 |

全部16观测：V核心一种，G完整signature一种；20完整signature为标准14批、002一批、004一批，共3种。两种ALL疑问的中文表述没有被当前signature规则归成同一问题：002包含“目标为”但不含规则要求的“类别／范围／可选”。这是问题归一化遗漏，不能解释成两种不同的目标语义。

20这两条疑问更准确的分类是**已知规则应用失败**；常规condition和notes变化只是**表述漂移**。真正语义错误与表达漂移不能一并算为数值标准不一致。

## 已发现的字段合法性失败

| 批次／ID | 冻结校验器报告 | 处理建议 |
|---|---|---|
| 004／571 | 非空文本却modules为空 | `WAITING FOR A NEW EFFECT`是占位符，不是可靠能力；允许明示placeholder状态或规范unknown条目，不能虚构效果来满足检查 |
| 005／664 | 两项basis=`dustpile_composition`不在枚举 | 确实缺来源数量表达式；不能机械改为fixed后继续定价 |
| 008／20 | 多余target_metadata | 可移入审计metadata，不影响提取本体；不需要重抽整批 |
| 009／530 | exact_kill无卡面依据 | 是语义错误；普通kill允许过量，删除错误条件并核对整个kill家族 |
| 009／910 | basis=`dustpile_composition`不在枚举 | 缺数量来源、过滤、每2个一组等表达结构 |
| 013／201 | exact_kill无卡面依据 | 是语义错误；它的自然语言还明确说普通kill允许过量，typed与文字互相矛盾 |
| 014／804、824、489、683、557、985、20、49 | 缺notes共8条 | 空字符串可以作为确定性格式修复，但修复后必须继续逐字段审查；不能将这些条目视为语义合格 |

014／985还有timing=`passive`不在枚举，冻结校验器因先遇缺notes而提前continue，没有报告后续错误。这说明需要在一条记录内收集所有检查结果，而非修完一个格式问题才暴露下一层。

## 非探针抽查：32张卡

以下是人工逐项对照卡面与原始模块。不是全量准确率估计；“未发现明显错误”也不保证复杂互动裁定已经解决。

| 批次／ID | 审查结果 |
|---|---|
| 000／833 | Magic和Bullseye各拆出2点敌怪＋1点玩家伤害，数量正确；最低HP选择器只在notes，typed目标仍不完整。Bullseye条件被写成“本卡攻击”，存在将Magic造成的精确击杀排除的风险，不能把Bullseye统一限定成attack |
| 001／434 | 数量／buff正确；add同时amount=3/count=3，应定义生成量只使用count，不能乘成9。左右分支单动作可表达，但右侧覆盖手牌和场上仅在自然语言 |
| 002／989 | **遗漏COST−3**，仅有ATK/HP−3；新增副本是目标的exact copy，target=self不足以绑定目标副本。不是新的Gold估值问题 |
| 002／503 | **空手格数误写成hand_size_after_play，amount=null**。正确函数为7−打出后手牌数；ALL疑问也违反已给定前提 |
| 003／193 | 减费只应该作用于被转化的法术；discount的target=hand、condition空，若执行为全手牌会错误。需绑定转化输出集 |
| 003／909 | Support增益已提取，但Lose／Regain门状态没完整表达；Shock被passive掩盖。unknown只说明当前词典不足，不能据此计连续触发 |
| 003／143 | +1ATK正确；silence=body遗漏未兑现Support能力，按当前定义应包含future。Support仅passive，typed仍不能直接执行 |
| 004／153 | 召唤后手牌≤5的抽牌条件和count=1基本正确；需要summon事件触发字段，不能把passive默认成每回合触发 |
| 004／571 | 占位符被诚实地留为无可靠能力；当前校验规则误将这种诚实保留当成遗漏效果 |
| 004／984 | 手数乘数1、一次伤害、Bullseye召唤引用375正确；这是未发现明显数值错误的样本，不能因其熟悉而给其它家族背书 |
| 005／664 | basis枚举非法；同时缺Erase数量到Add数量、Add失败数量到buff数量的事件引用。Erase是否触发Dust已经由Skill明确区分，不应列为未知 |
| 005／138 | Dust Earn GOLD 2提取为refund、amount=2，未发现明显错误。refund应是收入类型，不是再降paid_cost |
| 005／807 | 四种触发都有记录，但Shock被passive替代；新Pipis带Haste这一输出修饰只在卡面，没有结构模块 |
| 006／812 | 牺牲被明确保留unknown，抽2张正确；属于未支持的联合代价，不能只给draw加分而不扣被牺牲身体 |
| 006／899 | 第二次抽牌条件明确，但获得Darkspawn用unknown；“silence=none”遗漏后来可以删除的自身Darkspawn。未支持与沉默暴露要分开 |
| 007／958 | **all enemies漏对方玩家伤害**；Lose/Regain Shock门遗漏。Full heal是治疗，不是HP增益，body_and_future不能直接解释为长期身体buff |
| 008／948 | Delay时点正确，但instead是由精确死亡条件决定的目的地，不能允许玩家任意挑choice_group分支；需强制分支guard |
| 008／880 | **右侧AOE＋Haste被同组逐模块互斥**，会只能拿一个；all enemies漏玩家；返回＋降基础费被写refund，混淆金币收入、跨区移动与费用字段 |
| 009／530 | 链伤害amount=1/count=1/repeat=on_kill正确；exact_kill是实质错误，而不是措辞差异 |
| 009／910 | **枚举及公式不足**：来源是dustpile，需COST过滤及每2个一组。仅填dustpile_composition不能表达最终增益；unique COST含义若未裁定，必须具名保留 |
| 009／112 | 为对方召唤Ice，recipient=opponent与ref10正确；未发现明显方向错误 |
| 010／757 | 保留数量公式unknown比误当常量安全；但每3张Erased召唤一张的分组结构应可表达，不能只靠中文condition |
| 011／775 | **Shock被错误标成magic**，即会把施法后攻击误执行为打出时攻击；自然语言条件正确不能挽救typed触发错误 |
| 011／908 | **Shock降顶怪费用被错误标magic**；source是牌库顶怪，target=self没有表达受益牌。抽牌附加“牌库有牌”可能错误隐藏空库疲劳，不能当完整合法性条件 |
| 012／394 | **同一左分支buff＋Armor被拆为同组互斥**；silence=none遗漏自身buff／Armor暴露；“召唤副本是否触发Magic”已经由K003给出默认规则 |
| 013／201 | heal4＋召唤359提取正确，但exact_kill与卡面及自身notes矛盾；you被self折叠，执行时需明确玩家 |
| 014／683 | **遗漏抽到Plug后的+2/+2**；“抽到具体牌号不确定”是正常抽牌随机性，不是规则未知。Turbo／drawed-output绑定词典要补 |
| 014／985 | aura仍依赖当前施法者，silence应保留删除光环的未来暴露，不能因增益在其它友军身上就等同已兑现Magic；timing=passive非法 |
| 015／21 | AOE和玩家伤害量正确；silence=none忽略自身Haste。卡级时点immediate也不能据此推断全部效果已经完成 |
| 015／471 | **遗漏COST+1**；notes却声称已单列。you玩家伤害和LostSoul输出buff／Haste都写self，结构会将收益加到主体本身 |
| 015／658 | refund乘数1正确，但basis=ally_monster_count只表示全部友军；Generated过滤只有文字，未经过滤不能直接交evaluate_amount |
| 015／846 | 方向文字包含双方，typed target=hand没有区分己方／敌方，不能只计自己的减费收益；并列最高费用确可作为具名裁定保留 |

抽查中的错误集中在现有schema无法表达的地方，不是改变抽样随机种子就能解决。尤其“精确evidence存在”不保证效果条目完整，也不保证target／trigger正确。

## 应修规范而非重抽样的规则

1. **Bullseye与普通kill**：普通kill不能自动exact；Bullseye不能仅限定自主攻击，应保存造成精确击杀的事件来源。530、201可作typed对照反例。
2. **已知规则疑问**：在输入已经明确ALL、Erase≠Dust、Summon默认不Magic时，统一检查冲突；真正服务器队列或未裁定互动仍保留。当前中文子串匹配归一化不足。
3. **持续能力与沉默**：先按每个模块记录未兑现能力与自身可移除增益，再聚合卡级暴露。Haste/Taunt/Dodge即使搭配即时Magic，仍不能因此标整卡none；光环不等于已经给出的永久Magic增益。
4. **触发及门状态**：Shock/Support/Turbo与被动状态分开；Lose/Regain等是触发能力的开关。不能用passive或magic作为万能容器。
5. **对象与生成输出**：you玩家、this怪物、当前回合玩家、抽到或生成的牌、牌库顶怪，需要明确不同recipient；card_ref只是卡牌种类，不能承担实例绑定。
6. **数量与分支**：Add/Draw/Summon数量只用count，不同时乘amount；一个分支内可有多个联动动作。forced instead分支与自由选择分支分开。
7. **遗漏检查**：逐段覆盖COST、ATK/HP、状态、all enemies、跨区动作。989、471、683、958等在现有格式通过后仍有明确漏项。
8. **确定性格式修复与发布门禁**：notes缺失可补空，附加metadata可移走，但不能清空unresolved、补猜测数值或跳过语义审核。占位卡用明确状态而非伪造能力。

## 最小V6 schema提案

目标仅是容纳这些已经失败的样本，不引入自由脚本，不生成价值参数。

### 1. 分支捆绑

保留 `choice_group`，新增 `choice_branch`（null或短字符串）。同一group选择一个branch，该branch下所有modules一起执行。394：左branch包含buff+Armor，右branch包含summon；880：右branch包含AOE+Haste。

在group元数据注明 `selection_mode=player_choice|position|condition`。forced instead用有限guard代码＋布尔预期，例如 `exact_death_this_turn=true`；不可将forced条件组作为可随意最大化的菜单。暂不支持的guard直接隔离。

### 2. 来源、受益者与实例绑定

- `source`：产生效果的事件／主体，有限枚举，如this、spell_cast、ally_attack、draw_this、received_damage、lost_dodge。
- `recipient`：player_self、monster_this、player_opponent、hand_self、hand_both、enemy_monsters、event_output等有限枚举。
- `card_ref`：仍仅为明确卡牌种类ID，可为空，不是实例身份。
- 必要时用短 `module_id` 与 `recipient_ref` 绑定前面模块的输出，如471的生成牌buff引用add输出，193的降费引用transform输出。引用只允许同条注解中更早的module_id，没有任意执行代码。

保留旧target作粗分类兼容，但进入执行前必须解决recipient。you与this不再共用一个可执行self；当前回合玩家可以用明确的current_turn_player，不再猜己方。

### 3. 触发补缺与简单门状态

trigger补 `shock, support, turbo`，以及实际出现的 `summon, damage_taken, lose_dodge, death` 等有限事件；attack再明确before／after阶段，或用单独phase字段。普通持续状态仍为passive。

Lose／Regain使用小型状态操作模块 `state_change`，只允许具名能力 `enabled=false|true`。775和908必须shock，不允许凭中文condition把magic重新解释为shock。

### 4. 有限数量表达式

保留fixed／hand_size_after_play／other_monster_count等现有basis，补 `hand_empty_after_play`，无需支持任意表达式即可表示503的7−H。

另补 `source_count`：只允许 `count_source`（dustpile、board、hand、prior_event_outputs／prior_event_unadded等）、有限 `count_filter`（card_ref、Generated、tribe等）、正整数 `count_divisor` 和明确floor分组。664可以表示Erased数量及未加入输出数量；910可表示确认过含义的COST过滤与每2个分组。过滤含义未裁定时留unknown，不能自创unique COST语义。

数量输出用count或 `count_basis`，不再将数量公式塞进伤害amount。伤害的amount依旧表示单次伤害常量或乘数，保留count=1，避免把一段动态总伤害误拆成多实例影响Dodge。

这些有限字段足以阻止本轮主要误解。V6落地后应先用已保存失败样本做确定性回归，再局部集中修订；无需为修字段重新跑全部404张。
