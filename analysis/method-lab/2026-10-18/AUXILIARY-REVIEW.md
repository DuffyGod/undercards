# DeepSeek辅助结果人工审阅

2026-10-18。两批各10/12张卡，重叠49/530/649/984。共享11条完整消息，包括Skill、rules、共同方法边界及4组few shots。完整payload/前缀在statistical-auxiliary；本机外部helper只负责认证与传输，密钥未写入产物。正式数值由本仓库程序独立生成。

原始两次调用均WinError10013，无HTTP结果，usage/cache未知。网络权限下在network-permitted-01目录原样payload重试，每批一次、无自动重试；均成功。第一批9442输入/1708输出，缓存0；第二批9674输入/2804输出，服务报告缓存6528。缓存数字按API原样记录，不推断消息边界上的全部命中。

以下按card_id覆盖全部候选。接受某个机制观察也不表示接受整行，其绝不自动成为价格或新裁定。

| 批次 | ID | 审阅结果 |
| --- | --- | --- |
| same_policy_numeric | 15 | 保留下一次自主攻击的6/2→6/3例，前提已经不是入场回合；不加入当前Haste菜单。 |
| same_policy_numeric | 20 | 保留Magic不随本体HP改变、身体残值改变；未来保护一句未对应此卡，不采用。 |
| same_policy_numeric | 21 | 保留本体增攻不改AOE/伤脸；“仅改变击杀质量”遗漏存活本体F差，不能作为完整归因。 |
| same_policy_numeric | 43 | 只保留ATK不直接改Dust文本；无Haste，所谓同一攻击顺序是未来条件，不是当前回合已兑现。 |
| same_policy_numeric | 49 | 保留手牌多1使成长多1/1；“手牌9→上限7”非法例拒绝，“离场身材更大”改为在场状态。 |
| same_policy_numeric | 649 | 保留HP变化不改Magic计数；不能把HP+1在未得Haste时判0，仍有身体差。 |
| same_policy_numeric | 984 | 保留多1伤可能丢恰好击杀产物；原fixed_action称Bullseye相同而下文称改变，自相矛盾，按物理差重写。满手反转泛谈不采用。 |
| same_policy_numeric | 530 | 保留ATK跨击杀线可开启当前连锁、Dodge消耗不得重复计。未来未知目标不当已执行。 |
| same_policy_numeric | 469 | HP可能改变死/活从而是否当前召唤O，不能只给一个身体F差；原文未充分覆盖这点，不采用为完整结论。 |
| same_policy_numeric | 175 | 拒绝“Armor受1点攻击从0变1”的示例：Armor使1伤降0，原/新HP均不受伤。正确的存活跃迁可用原始2伤，减伤后1伤时1HP死、2HP活。普通卡不能当前回合自主攻击。 |
| demand_distribution_bias | 2 | 拒绝整行定量解释：把敌方HP尾概率与自身HP价/自身支付概率混淆。自身HP降低不会因落入需求高密度区而价值增加。 |
| demand_distribution_bias | 4 | 拒绝“HP2→3几乎不改变残值”的推论；取决于敌ATK与F，不可直接用敌HP尾概率判断。 |
| demand_distribution_bias | 11 | 保留增攻是对另一对象的状态差；不能一概称只有下回合兑现，友军可能本回合尚可攻击。本轮无友军面板不采用该行补价。 |
| demand_distribution_bias | 13 | 保留须看敌ATK分布；拒绝把当前减攻一概限制为只有实际交锋才有状态价。F差本身保留后续使用预期。 |
| demand_distribution_bias | 49 | 保留按完整手牌分布而非均值估成长，已独立实现；不采用同回合普通攻击。 |
| demand_distribution_bias | 168 | 保留Dodge按一次实例与是否已消耗区分；未来未知受伤只作储备，示例未新验证价格。 |
| demand_distribution_bias | 243 | 保留Draw与Add区分；“抽牌后再攻击”须延后至可自主行动，不是入场计划；抽牌价仍是外生。 |
| demand_distribution_bias | 292 | 保留当前HP4而非印刷9；原“9/7→4/7”倒写攻血，受伤需求变换又误套候选自身，不采用其数值叙述。 |
| demand_distribution_bias | 530 | 拒绝“4ATK对4HP不击杀”：普通目标明确恰好击杀，触发连锁。该错误已被独立物理测试覆盖。 |
| demand_distribution_bias | 984 | 保留4→5伤对5HP目标开启Bullseye、Clover属性2/3；“均匀手牌均值”措辞错误，实际联合频数非均匀，不采其推论。 |
| demand_distribution_bias | 649 | 保留其他怪物计数及Haste阈值依赖场面；未指定目标HP就说2伤剩1不成立。 |
| demand_distribution_bias | 377 | 保留Dodge消耗不双算；拒绝用敌HP尾概率推自身HP价与支付率。 |

跨卡建议中，仅保留“点质量而非均值决定精确击杀”“扫描共同资源结构”“clamp(HP−2)不是AOE幸存样本”的方向提醒；这些已由主智能体独立统计，不是因LLM同意而得到验证。将任何本体身材变化、目标HP变化及手牌变化分开，不把三者合成一种泛泛的需求密度。

本轮未因辅助结果修改价格参数或主程序。它的作用是提供待审查反例，不能替代统计模型，更不能证明Gold标定或实战强度。
