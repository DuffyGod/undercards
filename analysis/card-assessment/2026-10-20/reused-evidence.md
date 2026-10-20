# 已恢复DeepSeek证据：可复用清单

2026-10-20。直接在内存读取 `research-archive/stage-evidence.zip` 的指定成员；没有联网、重跑、计算哈希或整包恢复。逐卡JSON来源见 `reused-evidence.json`。本清单复用机制候选，不恢复旧评分为Gold。

## 实际覆盖与原始状态

- 九份 `annotations.json` 合计239条、134个独立card ID；另有6条旧人工reviewed-subset，不增加独立ID。
- round01八份inventory raw均能解析，合计80行、66个独立ID；其中共同probe重复。与上述集合重合3个ID：15, 20, 49。总并集197个ID、325个记录出现次数；不是325张牌。
- complete404的manifest确实请求404张、列51项任务，但其 `annotations.json` 实际仅119条/119个ID；归档仅有16份该run的正式batch记录。404是请求规模，不能当已完成覆盖。
- 404项请求中，综合本清单其他来源现有196张有候选注释，208张仍无本清单内返回注释；另有一张Froggit #2不属于该404请求。缺少注释不表示该卡没有作用。
- 原始条目状态：221次未提供annotation_status，101次自报parsed，3次自报partial。parsed不是人工语义验证。
- 逐卡当前复核状态全部为未复核：**0个新verified**。325次printed_effect均与当前快照逐字一致，所存module evidence均能找到字面子串；这仅是表面文本检查，不保证目标、数量、触发和规则正确。

| 来源码 | 行数 / 独立ID | 原一致性 | 原语义状态 | 精确archive member |
| --- | --- | --- | --- | --- |
| A01 | 6 / 6 | False | 未获本轮语义复核 | `analysis/monster-value-heuristic/annotation-runs/pilot-v1-online/annotations.json` |
| A02 | 0 / 0 | False | 未获本轮语义复核 | `analysis/monster-value-heuristic/annotation-runs/pilot-v1/annotations.json` |
| A03 | 11 / 11 | False | 未获本轮语义复核 | `analysis/monster-value-heuristic/annotation-runs/pilot-v2/annotations.json` |
| A04 | 15 / 15 | False | 未获本轮语义复核 | `analysis/monster-value-heuristic/annotation-runs/pilot-v3-central/annotations.json` |
| A05 | 32 / 32 | True | 未获本轮语义复核 | `analysis/monster-value-heuristic/annotation-runs/pool-v4-dialogue-32/annotations.json` |
| A06 | 119 / 119 | False | 未获本轮语义复核 | `analysis/monster-value-heuristic/annotation-runs/pool-v5-complete404/annotations.json` |
| A07 | 32 / 32 | True | 未获本轮语义复核 | `analysis/monster-value-heuristic/annotation-runs/pool-v5-knowledge-32/annotations.json` |
| A08 | 16 / 16 | False | 未获本轮语义复核 | `analysis/monster-value-heuristic/annotation-runs/semantic-v6-holdout16/annotations.json` |
| A09 | 8 / 8 | True | 未获本轮语义复核 | `analysis/monster-value-heuristic/annotation-runs/semantic-v6-regression8/annotations.json` |
| A10 | 6 / 6 | True | 旧semantic_audit_passed=true；本轮未复核 | `analysis/monster-value-heuristic/annotation-runs/pilot-v3-central/reviewed-subset.json` |

旧6条reviewed-subset是历史上“六个简单模板”的审查通过记录，必须保留其原始语义审查状态；也不能据此把其它复杂牌或本轮新数值标为已验证。run整体consistency=false与某个保留条目的结构失败不是同一个概念；JSON分别保存run旗标和round逐卡错误。

| round01任务 | 原状态 | 注释行 / finding数 | 原始结构问题 |
| --- | --- | --- | --- |
| `counterexample_000` | completed | 0 / 3 | 无原记录错误；仍需语义复核 |
| `counterexample_001` | structural_validation_failed | 0 / 3 | Finding evidence is not a literal supplied-source substring |
| `inventory_000` | failed | 10 / 0 | JSON 缺少字段：['kind', 'task_id'] |
| `inventory_001` | structural_validation_failed | 10 / 0 | 759: a: binding must refer to an earlier module_id, never a future/self reference |
| `inventory_002` | structural_validation_failed | 10 / 0 | 790: unknown mechanism/formula requires partial status |
| `inventory_003` | structural_validation_failed | 10 / 0 | 781: a: unknown module enum；171: b: binding source does not produce an event output；171: unknown mechanism/formula requires partial status；925: a: unknown module enum；921: unknown mechanism/formula requires partial status；245: a: unknown module enum |
| `inventory_004` | completed | 10 / 0 | 无原记录错误；仍需语义复核 |
| `inventory_005` | structural_validation_failed | 10 / 0 | 301: a: known numeric effect requires fixed amount or an explicit unknown/source basis；301: b: known numeric effect requires fixed amount or an explicit unknown/source basis；248: b: known numeric effect requires fixed amount or an explicit unknown/source basis；248: c: binding source does not produce an event output；542: a: binding must refer to an earlier module_id, never a future/self reference；975: a: binding must refer to an earlier module_id, never a future/self reference |
| `inventory_006` | completed | 10 / 0 | 无原记录错误；仍需语义复核 |
| `inventory_007` | structural_validation_failed | 10 / 0 | 993: b: unknown expression source/stat；993: b: binding source does not produce an event output；495: unknown mechanism/formula requires partial status；500: b: state_change needs named key and 0/1 enabled value |
| `model_review_000` | structural_validation_failed | 0 / 4 | Finding evidence is not a literal supplied-source substring；Finding evidence is not a literal supplied-source substring |
| `model_review_001` | structural_validation_failed | 0 / 4 | Finding evidence is not a literal supplied-source substring |

round01的精确成员前缀是 `analysis/monster-value-heuristic/research-runs/round01/`，每项任务对应 `<task_id>.json`；共同manifest为该前缀下的 `manifest.json`。原始注释位于 `JSON.parse(raw_response.choices[0].message.content).annotations[i]`。原记录中completed/ok只代表当时结构合同通过，不代表规则正确；failed raw也没有被丢弃或改写成通过。

## 三个会改变新逐卡报价的疑点

### 434 Dark Ponman：数量与分支

`analysis/monster-value-heuristic/annotation-runs/pool-v5-complete404/annotations.json` → `annotations[39]`。该行左分支同时是 `amount=3,count=3`，右分支另有全体Ponman加身材；若新通用解释器相乘或把两支相加，会把3张变9张并叠加增益。原notes明确互斥，不能丢弃。V6 holdout对同一卡改用amount=null,count=3及左右branch_guard，说明旧结构不能直接当统一执行格式。以3张为数量、按容量计算留存；选择buff分支时不同时加牌。 这是需针对性复核的语义/迁移风险，不声称旧程序已经按错误方式执行。

### 506 Soul Cage：收益归属和出手时机

`analysis/monster-value-heuristic/annotation-runs/pool-v5-complete404/annotations.json` → `annotations[47]`。旧模块只有 `target=hand`，没有结构化recipient，且没有把1-COST绑定为产物改写。卡面是current turn player：己回合主动换死可给己方Knife，敌回合被处理可给对手Knife。若无条件给携带者一张牌，会把Haste主动兑现与留场被处理的差异抹掉，甚至把负收益算成正收益。 这是需针对性复核的语义/迁移风险，不声称旧程序已经按错误方式执行。

### 151 Echo Fish：复制源与受益对象

`analysis/monster-value-heuristic/annotation-runs/pool-v5-complete404/annotations.json` → `annotations[16]`。旧结构为 `kind=transform,target=enemy_monster`，其notes说复制目标当前数值，却未结构化区分“读敌体”与“改变自身”。不能把它解释为移除/变形敌怪。复制敌8/8时，己方Echo Fish成为相应身体、敌8/8仍在；不能再加一份清除敌体的F收益。当前/最大HP与base stats边界仍保留为unresolved，未在本轮做服务器裁定。 这是需针对性复核的语义/迁移风险，不声称旧程序已经按错误方式执行。

## 逐卡可复用来源

下表来源码对应上方精确ZIP成员；`[i]`为该成员annotations数组索引，R码对应round01 inventory raw。所有条目均为候选材料、本轮未verified；多个来源全部保留，不按多数票合并成Gold。

| card ID | 当前名称 | 可用来源码及数组索引 |
| --- | --- | --- |
| 2 | Froggit | A03[0], A04[0], A10[0] |
| 11 | Snowdrake | A03[1], A04[1], A10[1] |
| 13 | Woshua | A03[2], A04[2], A10[2] |
| 15 | Aaron | A03[3], A04[3], A10[3], R002[6] |
| 20 | Vulkin | A01[0], A03[4], A04[4], A06[0], A10[4], R000[8], R001[8], R002[8], R003[8], R004[8], R005[8], R006[8], R007[8] |
| 21 | Tsunderplane | A03[5], A04[5], A06[1] |
| 25 | Astigmatism | R004[0] |
| 35 | Lemon Bread | A06[2] |
| 36 | Snowdrake's Mom | A06[3] |
| 37 | Moldessa | R005[7] |
| 42 | So Sorry | A06[4] |
| 43 | Lesser Dog | A03[6], A04[6], A05[7], A06[5], A07[7] |
| 44 | Gyftrot | R004[2] |
| 49 | Glyde | A01[1], A04[7], A06[6], R000[9], R001[9], R002[9], R003[9], R004[9], R005[9], R006[9], R007[9] |
| 52 | Alphys | A06[7] |
| 54 | Flowey | R000[0] |
| 59 | Sans | R007[5] |
| 101 | Nacarat Jester | R003[7] |
| 102 | Sad Customer | A06[8] |
| 103 | Muffet's Pet | R006[5] |
| 108 | Rock | R006[1] |
| 112 | Ice Wolf | A06[9], A08[0] |
| 119 | G Follower 2 | A06[10] |
| 125 | Heats Flamesman | R002[3] |
| 126 | Papyrus Statue | A05[10], A06[11], A07[10] |
| 135 | Big Mouth | R002[4] |
| 138 | Ferry | A06[12] |
| 141 | Gift Bear | A06[13] |
| 142 | Blue Laser | A06[14] |
| 143 | Orange Laser | A05[25], A06[15], A07[25] |
| 151 | Echo Fish | A06[16] |
| 152 | Bratty | R006[6] |
| 153 | Catty | A06[17], A08[1] |
| 163 | MTT Fountain | A06[18] |
| 165 | Oni | A06[19] |
| 169 | Bunbun | R001[0] |
| 171 | Dimensional Box | R003[2] |
| 185 | Librarian | A06[20] |
| 193 | Disco Ball | A05[28], A06[21], A07[28] |
| 194 | Shambling Mass | R006[0] |
| 197 | Elder Puzzler | A06[22] |
| 198 | Red Bird | A06[23] |
| 201 | Dancer Mettaton | A09[0] |
| 221 | Skateboard Girl | R003[4] |
| 227 | Coffee Man | A05[18], A06[24], A07[18] |
| 235 | Dad Slime | A06[25] |
| 236 | Hot Dog Vulkin | A04[8] |
| 239 | Snowdin Sign | R001[5] |
| 240 | TV | R002[7] |
| 243 | Bench | A04[9], A10[5] |
| 245 | Scarf Lady | R003[6] |
| 248 | Business Dude | R005[2] |
| 265 | Lancer | R004[1] |
| 271 | Chaos Duck | A06[26] |
| 273 | Noelle | A06[27] |
| 274 | Starwalker | R007[1] |
| 276 | Catty's Dad | R005[4] |
| 277 | Snailmobile | R006[4] |
| 278 | Dark Candy Tree | A06[28] |
| 290 | Snowy | A06[29] |
| 291 | Normal NPC | A06[30] |
| 296 | Jar of Worms | A06[31] |
| 297 | Starwalker Bird | A06[32] |
| 298 | Rabbick | A06[33] |
| 301 | Toy Block | R005[1] |
| 302 | Big Hat Charles | R005[5] |
| 308 | Donation Stump | A06[34] |
| 394 | Mister Elegance | A06[35], A09[1] |
| 396 | Hathy | A06[36] |
| 408 | Space Cooler | A06[37] |
| 418 | Malius | A04[10] |
| 426 | Rabbick Hole | R000[2] |
| 432 | Popumeter | A05[26], A06[38], A07[26] |
| 434 | Dark Ponman | A05[15], A06[39], A07[15], A08[2] |
| 438 | Battleflies | R004[3] |
| 441 | Sword Emblem | R003[0] |
| 466 | Bookshelf | R007[3] |
| 468 | Rudolph | A05[20], A06[40], A07[20] |
| 469 | Blockler B | A04[11], A06[41] |
| 471 | Chaos Blaster | A06[42], A09[2] |
| 472 | Seam | A06[43] |
| 474 | Spider Sign | A06[44] |
| 495 | Cross Bomb | R007[4] |
| 500 | Ice-E Mascot | R007[6] |
| 501 | Cool Bone | A06[45] |
| 503 | Library Loox | A05[21], A06[46], A07[21], A09[3] |
| 504 | Biker Lancer | R007[7] |
| 506 | Soul Cage | A05[5], A06[47], A07[5] |
| 507 | Fireplace | R002[2] |
| 509 | Long Sink | A05[29], A06[48], A07[29] |
| 514 | Date Alphys | A06[49] |
| 524 | Legendary Artifact | R001[1] |
| 528 | Rope Dog | R006[3] |
| 530 | Piranhas | A01[2], A03[7] |
| 533 | Gerson Tombstone | A05[23], A06[50], A07[23] |
| 534 | Carbed | R000[5] |
| 542 | Trash Ball | R005[3] |
| 545 | Totem | A06[51] |
| 549 | Cop Undyne | A06[52] |
| 556 | Baron | A06[53] |
| 560 | Mom Slime | R002[5] |
| 561 | Royal Loox | A05[17], A06[54], A07[17] |
| 566 | Fox Bodyguard | A05[9], A06[55], A07[9] |
| 570 | The Original | A05[22], A06[56], A07[22] |
| 581 | Golden Mascot | A05[8], A06[57], A07[8] |
| 582 | Tiny Bookshelf | A06[58] |
| 583 | Cracked Geode | A06[59] |
| 588 | Spaghetti | R004[6] |
| 589 | Shrine Mascot | R002[1] |
| 591 | Memorykeeper | R005[0] |
| 594 | Toy Bricks | R007[2] |
| 609 | G Machine | A06[60] |
| 612 | Angel Doll | A06[61] |
| 624 | Tasque | A06[62] |
| 630 | Shovels x999 | A05[30], A06[63], A07[30] |
| 635 | Susie Statue | A05[31], A06[64], A07[31] |
| 645 | Arcade Machine | A05[24], A06[65], A07[24] |
| 646 | Glitch | R000[4] |
| 649 | Broken Car | A01[3], A03[8], A04[12] |
| 651 | Traffic Car | A06[66] |
| 653 | Virovirokun | A06[67] |
| 658 | Cyber Balloon | A06[68], A08[3] |
| 664 | Spamton | A09[4] |
| 667 | Tiny Tornado | R006[2] |
| 671 | Berdlycoaster | A06[69] |
| 673 | Berdly Plush | R004[4] |
| 674 | Halberd | R004[5] |
| 676 | Milk Looker | A06[70] |
| 678 | Cauldron | R004[7] |
| 683 | Hatplug | A08[4] |
| 684 | Werewire | A06[71] |
| 751 | Ruins Tree | A06[72] |
| 757 | Pipis Cannon | A06[73], A08[5] |
| 759 | Tasque Singer | R001[3] |
| 762 | Watching Man | A05[16], A06[74], A07[16] |
| 763 | Control Panel | R000[3] |
| 773 | Shyra Tombstone | R001[6] |
| 775 | Crimeter | A06[75], A09[5] |
| 781 | Gift Bomb | R003[1] |
| 782 | Teacher Alphys | R001[7] |
| 790 | Mettabot Factory | R002[0] |
| 794 | GIGA Queen | R001[4] |
| 802 | Mew Mew Wand | A06[76] |
| 805 | Yandereplane | R000[7] |
| 806 | Torch | A06[77] |
| 807 | Spamequin | A06[78] |
| 812 | Flameguy | A06[79], A08[6] |
| 814 | Rorrim | A06[80] |
| 815 | Dalv's Wardrobe | R000[1] |
| 830 | Well | A06[81] |
| 832 | Tall Miner | A06[82] |
| 833 | Gamer | A05[2], A06[83], A07[2], A08[7] |
| 834 | Drinki | A05[1], A06[84], A07[1] |
| 835 | Rockman | A05[0], A06[85], A07[0] |
| 841 | Frost Igloo | A06[86] |
| 846 | Giftshopper | A06[87], A08[8] |
| 847 | Fortune Teller | A01[4], A03[9], A04[13] |
| 850 | Mines Sign | A06[88] |
| 851 | Minecart | A06[89] |
| 852 | Searby | A05[3], A06[90], A07[3] |
| 864 | Axis | A06[91] |
| 865 | Gilbert | A06[92] |
| 880 | Martlet | A06[93], A09[6] |
| 883 | Pixel Lancer | R000[6] |
| 888 | White Cloak | A06[94] |
| 893 | Treat Catcher | A06[95] |
| 894 | Winglade | A05[14], A06[96], A07[14] |
| 898 | Titan Serpent | A06[97] |
| 899 | Friendogeny | A06[98], A08[9] |
| 903 | Zoot Susie | A05[4], A06[99], A07[4] |
| 904 | Zoot Ralsei | A06[100] |
| 906 | Pixel Lanino | A05[12], A06[101], A07[12] |
| 907 | Pixel Elnina | R001[2] |
| 908 | Rockstar Ralsei | A06[102], A08[10] |
| 909 | Rockstar Kris | A05[27], A06[103], A07[27], A08[11] |
| 910 | Golden Piano | A08[12] |
| 911 | Crossganikk | A06[104] |
| 921 | Wicabel | R003[5] |
| 923 | Pixel Kris | A06[105] |
| 925 | Guei | R003[3] |
| 927 | Gachapon Machine | A06[106] |
| 929 | Chef Rouxls | R006[7] |
| 940 | Strange Machine | A06[107] |
| 948 | Blackjack | A06[108] |
| 951 | Fire Fountain | A05[6], A06[109], A07[6] |
| 952 | Miss Mizzle | A06[110] |
| 956 | Tuning Fork | A05[11], A06[111], A07[11] |
| 958 | Rockstar Susie | A06[112], A09[7] |
| 960 | Shinobeetle | A06[113] |
| 965 | Blue | A06[114] |
| 967 | Floradinn | A06[115] |
| 973 | Trial Susie | A05[13], A06[116], A07[13] |
| 975 | Trial Ralsei | R005[6] |
| 984 | Terakota Archer | A01[5], A03[10], A04[14], A06[117], A08[13] |
| 985 | Giant Shrubbery | A08[14] |
| 989 | Vampire Alvin | A05[19], A06[118], A07[19], A08[15] |
| 993 | Lost Noelle | R007[0] |

R000–R007分别对应 `analysis/monster-value-heuristic/research-runs/round01/inventory_000.json` 至 `inventory_007.json`。每项source的manifest、原始结构状态、逐卡错误、未决事项和字面检查结果都在JSON中，不因聚合来源码丢失。

## 如何继续复用

先让主模型利用197张的已有候选机制选择有价值的卡与反例；只对影响价格的目标/数量/产物绑定/时序进行简化用途复核。原批次失败可逐行审查，不能把整批10张全都当无资料重发；也不能仅修JSON字段就宣称语义正确。

404请求中未出现的208个ID只是这份清单的缺口，不应自动变成无差别补跑任务。先由Agent按独立站场、即时干预、补牌、机会条件与现有数值盲点选价值候选；DeepSeek后续只补机制与用途判断，不定最终价格。当前凭据缺失不影响这些本地候选证据继续研究。
