"""Agent-selected promising cards and explicit, falsifiable tactical endpoints.

This is a curated mechanism derivation, not text-to-rules automation or a
complete game search. Roots, branches and unpriced terms remain in the output.
"""
from copy import deepcopy
from collections import Counter
from itertools import product
import csv, json, subprocess
from tactic_core import *

REASONS = {
    201:'Haste击杀后补血与二次小体；选择可存活击杀而非盲撞高攻',
    437:'治疗变为定向伤害；轻伤友军可将大部分7点治疗转解场',
    391:'受伤目标4伤；准备伤害必须连同额外卡金一起比较',
    868:'先交换再双向治疗，使已有场面转为续航而非空放治疗',
    852:'恰5HP与普通击杀不同；精确补伤收益不能默认兑现减费',
    609:'Haste主动换死可把身体转为Delay后的Blaster；不能保留死人身体',
    163:'Haste用身体吸收反击并治疗英雄；对大包是否过量有裁定边界',
    579:'Kill受伤怪兼按攻击治疗，单一轻伤可大幅改变重怪收益',
    632:'己方回合免反击，敌方回合4攻；出场不能凭空获得Haste',
    654:'14/15HP与9/10HP是即时干预/末尾Candy的硬门槛',
    254:'Haste击杀回收3G4/5副本；副本不能同时计为已出场',
    266:'多用途Haste/3伤/补牌/回血；满手与疲劳改变补牌收益',
    151:'4G复制当前大体；不永久移除被复制目标，也不复制未列出的效果',
    506:'4G4/6Haste交换，Dust奖励给当前玩家；活到敌回合可能资敌',
    197:'首回合可末尾4伤；后续不攻击也可能胜过交换，但随机分布未知',
    443:'大费用目标提升Magic伤害，Haste可另处理一个目标',
    523:'4伤击杀后+3ATK可立即留9/7；没有Haste不能再领当前攻击',
    410:'7G6/5加尘堆低费复活；Summon不触发复活牌Magic',
    892:'四次最低HP点伤击杀生成2/3Taunt，空格是实际资源',
    964:'击杀后Carousel依死亡链继续，初始目标决定敌清场与己损失',
}

ORDINARY = {
    'one_3_4': [B(3,4,cost=4)],
    'one_5_5': [B(5,5,cost=6)],
    'one_8_8': [B(8,8,cost=10)],
    'spread': [B(3,1,cost=2),B(2,2,cost=3),B(1,3,cost=2)],
}


def body(cid):
    c=CARDS[cid]
    return B(c['attack'],c['health'])


def fight(own, enemy, i, j):
    """Simultaneous ordinary damage identity only; no inferred death queue."""
    aa,bb=deepcopy(own),deepcopy(enemy)
    u,v=aa[i],bb[j]
    aa[i]=hit(u,v['a']);bb[j]=hit(v,u['a'])
    return live(aa),live(bb),aa[i]['h']>0,bb[j]['h']<=0


def carousel(own, enemy):
    """Each full 1-DMG wave completes; repeat iff that wave killed a unit."""
    aa,bb=deepcopy(own),deepcopy(enemy);waves=[]
    while True:
        next_a,next_b=live([hit(u,1) for u in aa]),live([hit(u,1) for u in bb])
        died=len(aa)+len(bb)-len(next_a)-len(next_b)
        waves.append(dict(own_before=aa,enemy_before=bb,own_after=next_a,enemy_after=next_b,deaths=died))
        aa,bb=next_a,next_b
        if not died:break
    return aa,bb,waves


def main_routes():
    records=[];comparisons=[];notes=[]
    def add(*args,**kw):
        r=route(*args,**kw);records.append(r);return r
    # Immediate single-card choices. All opponents ordinary, no Dust, Taunt or
    # attack-trigger abilities; hand room and a nonempty deck are conditions.
    haste_ids=(201,609,163,254,506)
    for root,enemy in ORDINARY.items():
        for cid in haste_ids:
            unknown=['Unexposed future abilities and opponent reply are not priced']
            start=body(cid)
            add(cid,root,'deploy_hold',[],enemy,[start],enemy,
                condition='hero missing >=4HP; initial hand<=6; no attack',unknown=unknown,
                path=['Play focal monster; retain its attack'])
            for j,e in enumerate(enemy):
                own_end,enemy_end,survived,killed=fight([start],enemy,0,j)
                gained=0;heal=0;u=list(unknown);stage='after_current_turn_actions'
                if cid==201:
                    if survived and killed:
                        own_end.append(B(1,1));heal=4
                    elif not survived and killed:u.append('After-attack kill reward when attacker also dies unresolved; not granted')
                if cid==254:
                    if survived and killed:gained=1
                    elif not survived and killed:u.append('Kill-copy trigger when attacker dies unresolved; not granted')
                if cid==163:
                    if survived:heal=min(4,e['a'])
                    else:u.append('Fountain death/overkill healing queue unresolved; not granted')
                if cid in (506,609) and not survived:
                    gained=1
                    if cid==609:stage='after_own_Delay'
                if cid==506 and survived:u.append('If killed on enemy turn, enemy receives Knife; not credited now')
                r=add(cid,root,f'attack_{j}',[],enemy,own_end,enemy_end,gained=gained,heal=heal,
                    stage=stage,condition='hero missing >=4HP; ordinary target; hand space for actual generated card',
                    path=[f'Play {CARDS[cid]["name"]}',f'Attack enemy index {j}', 'Resolve only declared surviving kill/Dust/Delay consequences'],unknown=u,
                    features=dict(endpoint_mechanics_complete=not any('unresolved' in x for x in u)))
                # Newly summoned Mettabot has Haste, never Charge. All legal
                # ordinary follow-up targets are retained, including no attack.
                if cid==201 and survived and killed:
                    for k in range(len(enemy_end)):
                        aa,bb,_,_=fight(own_end,enemy_end,len(own_end)-1,k)
                        add(cid,root,f'attack_{j}_bot_{k}',[],enemy,aa,bb,heal=heal,
                            condition='surviving Dancer kill; token has a monster to attack',
                            path=[f'Dancer kills enemy {j}',f'Mettabot attacks remaining enemy {k}'],unknown=unknown)
        # Echo copies ordinary current stats; no Haste is invented here.
        for j,e in enumerate(enemy):
            add(151,root,f'copy_{j}',[],enemy,[B(e['a'],e['h'])],enemy,
                condition='ordinary enemy without copied statuses; source stays alive',
                path=[f'Copy current stats of enemy {j}; leave original enemy'],
                unknown=['Copied named statuses and future reply vary with actual source'])
        # Spell damage + possible first-turn attack, paying full printed cost.
        for cid in (391,852,443,523,266):
            for j,e in enumerate(enemy):
                d={391:1,852:5,443:4+e['cost']//3,523:4,266:3}[cid]
                aa=[body(cid)];bb=deepcopy(enemy);v=hit(e,d);bb[j]=v;bb=live(bb)
                gained=0;heal=0;unknown=[]
                if cid==523 and v['h']<=0:aa[0]['a']+=3
                if cid==852 and v['h']==0:
                    gained=1;unknown=['Drawn card -2 COST unpriced until actually redeemed; a future feature, not current cash']
                if cid==266:gained=3;heal=3
                if cid==391:unknown=['Damage check uses target damaged before Magic; this row target starts full']
                r=add(cid,root,f'magic_{j}',[],enemy,aa,bb,gained=gained,heal=heal,
                    condition='initial hand<=4 and >=3 nonfatigue cards for Hydra; hero missing>=3; no target defense',
                    path=[f'Magic on enemy {j}: {d} DMG', 'No current attack unless a separate Haste branch'],unknown=unknown)
                if cid in (443,266):
                    for k in range(len(bb)):
                        a2,b2,_,_=fight(aa,bb,0,k)
                        add(cid,root,f'magic_{j}_attack_{k}',[],enemy,a2,b2,gained=gained,heal=heal,
                            condition=r['ledger']['condition'],path=[f'Magic target {j}',f'Haste attack remaining enemy {k}'],unknown=unknown)
        # First-turn Elder always did not attack. Random outcome rows are NOT
        # averaged: no probability law for random targets is silently fitted.
        for j,e in enumerate(enemy):
            bb=deepcopy(enemy);bb[j]=hit(e,4)
            add(197,root,f'random_outcome_{j}',[],enemy,[body(197)],live(bb),stage='after_own_turn_end',
                path=['Play Elder without Haste','Own Turn end 4 DMG lands on declared target'],
                condition=f'conditional random outcome index {j}',unknown=['Random target distribution and repeat-turn survival unknown'])
        add(632,root,'deployment_only',[],enemy,[body(632)],enemy,
            path=['Play Trashy; no Haste, no current attack'],
            unknown=['Enemy-turn +2ATK is a response feature, not an extra current attack'],
            features=dict(enemy_turn_attack=4,own_attack_retaliation_damage=0))

    # Exact preparation pair: extra Loox is not free; same hand and same root.
    own=[B(4,5,max_h=5)];enemy=[B(4,6,max_h=6)]
    good=add(437,'agent_setup','loox_then_agent',own,enemy,own+[B(2,2),body(437)],[],used=[7,437],
        path=['Loox hits ally4/5 for1, becomes2/2','Agent heals ally4/4 to4/5; overflow6 kills enemy4/6 in front of Agent'],
        condition='8G, two cards, own>=3 slots available including initial ally; matching front slot; no on-damage triggers')
    # Opposite order has no damaged legal target. It cannot be treated as a
    # legal failed Magic. Compare legal Loox-alone fallback and reversed
    # preparation only on an already lightly damaged root below.
    fallback=add(437,'agent_setup','loox_only',own,enemy,own+[B(1,2)], [B(4,5,max_h=6)], used=[7],
        path=['Loox hits enemy4/6 for1; keep Agent in hand'],condition='Same initial hand; do not force targetless Agent Magic')
    comparisons.append(compare(good,fallback,'8G two-card conversion vs legal1G fallback; charges extra Agent card/Gold'))
    # One HP of pre-existing injury, then effects resolve with actual healing.
    for missing in (1,3,6,8):
        own=[B(4,9-missing,max_h=9)];enemy=[B(5,6,max_h=6)]
        healed=min(7,missing);d=7-healed;bb=live([hit(enemy[0],d)])
        add(437,f'agent_missing_{missing}','heal_front',own,enemy,[B(4,9-missing+healed,max_h=9),body(437)],bb,
            path=[f'Heal {healed}; overflow {d} to Agent front enemy'],condition='Correct front slot; ally already damaged; no setup card required')

    # Generic attack-before-heal trajectory: old ally is ready at root.
    own=[B(6,8,max_h=8)];enemy=[B(5,5,max_h=5)]
    healed=add(868,'pancakes_order','trade_then_heal',own,enemy,[B(6,8,max_h=8),body(868)],[],heal=5,
        path=['Ready ally6/8 kills5/5, survives6/3','Pancakes restores5 monsterHP and5 heroHP'],condition='Hero missing>=5; old ally already ready')
    wasted=add(868,'pancakes_order','heal_then_trade',own,enemy,[B(6,3,max_h=8),body(868)],[],heal=0,
        path=['Heal full ally for0','Same ally makes same trade'],condition='Hero missing>=5; identical available actions')
    comparisons.append(compare(healed,wasted,'Order alone preserves5 monster HP and heals5 hero HP; same fee/card'))
    # Sheary changes from1 to4 only if already damaged before Magic.
    enemy=[B(5,5,max_h=5)]
    a=add(391,'sheary_order','loox_then_sheary',[],enemy,[B(1,2),body(391)],[],used=[7,391],
        path=['Loox1 DMG makes enemy5/4 damaged','Sheary4 kills'],condition='7G, both hand cards available')
    b=add(391,'sheary_order','sheary_then_loox',[],enemy,[body(391),B(1,2)],[B(5,3,max_h=5)],used=[391,7],
        path=['Sheary1 hits full5/5','Loox1 leaves5/3'],condition='Same cards, no intervening reply')
    comparisons.append(compare(a,b,'Same two cards; order changes total2 to5 damage'))
    # Standalone damage route and costly setup, not merely order.
    solo=add(391,'sheary_order','sheary_only',[],enemy,[body(391)],[B(5,4,max_h=5)],path=['Sheary1; retain Loox'],condition='Same hand')
    comparisons.append(compare(a,solo,'Clearing5HP costs an additional1G and Loox; body plus kill vs keep setup'))
    # Enemy chip enables same-root Baking Queen; count actual healing cap.
    for hp in (5,8):
        enemy=[B(8,hp,max_h=hp)]
        add(579,f'queen_setup_{hp}','loox_then_kill',[],enemy,[B(1,2),body(579)],[],used=[7,579],heal=8,
            path=['Loox damages full enemy','Queen kills damaged monster; heal8 heroHP'],condition='11G/two cards; hero missing>=8')
        add(579,f'queen_damaged_{hp}','already_damaged',[],[B(8,hp-1,max_h=hp)],[body(579)],[],heal=8,
            path=['Kill already damaged8ATK target; heal8'],condition='10G; no setup cost charged because injury predates root')
    # Bullseye draws a card, not current2G. Exact damage vs overkill matters.
    enemy=[B(4,6,max_h=6)]
    a=add(852,'searby_order','loox_then_searby',[],enemy,[B(1,2),body(852)],[],used=[7,852],gained=1,
        path=['Loox leaves5HP','Searby front5 exactly kills; draw1 at-2 COST'],condition='8G; front free; nonempty deck and draw room',unknown=['2G discount only a future redemption feature'])
    b=add(852,'searby_order','searby_then_loox',[],enemy,[body(852),B(1,2)],[],used=[852,7],
        path=['Searby5 leaves1HP','Loox1 kills; Searby did not Bullseye'],condition='Same cards/fee; no bonus attributed to Loox kill')
    comparisons.append(compare(a,b,'Both kill; only correct order draws1 (-2 future discount not current cash)'))
    # The same one-point preparation can unlock Dancer's kill trigger.
    enemy=[B(3,5,max_h=5)]
    a=add(201,'dancer_setup','loox_then_dancer',[],enemy,[B(1,2),B(4,4),B(1,1)],[],used=[7,201],heal=4,
        path=['Loox chips5HP to4','Dancer attacks and survives, heals4 heroHP and summons1/1Haste'],
        condition='8G/two cards; hero missing>=4; at least3 free slots')
    b=add(201,'dancer_setup','dancer_only',[],enemy,[B(4,7)],enemy,
        path=['Deploy Dancer; retain Loox and decline nonlethal attack'],condition='Same hand; hero missing>=4')
    comparisons.append(compare(a,b,'Charge Loox1G/onecard, include all resulting bodies and real heal; setup unlocks a kill'))
    # Same5/5 target, realistic affordability/card-economy alternatives.
    enemy=ORDINARY['one_5_5']
    cheap=add(506,'one_5_5','loox_then_soul_cage',[],enemy,[B(1,2),B(4,1)],[],used=[7,506],
        path=['Loox1 damage changes5/5 to5/4','SoulCage Haste kills, takes5 and remains4/1'],
        condition='5G and Loox/SoulCage held; no relevant other effects; retain Knife reward untriggered',
        unknown=['If Soul Cage dies during enemy turn, enemy gets Knife, not us'])
    searby=next(r for r in records if r['id']=='tactics/852/one_5_5/magic_0')
    comparisons.append(compare(searby,cheap,'Both clear ordinary5/5:7G onecard+draw versus5G two-card Haste/chip; future discount/Knife not priced'))
    dancer=add(201,'one_5_5','loox_then_dancer',[],enemy,[B(1,2),B(4,2),B(1,1)],[],used=[7,201],heal=4,
        path=['Loox chips5HP to4','Dancer survives5 retaliation with2HP; heal4 and summon1/1Haste'],
        condition='8G/two cards; hero missing>=4; three empty slots; no further targets for token')
    comparisons.append(compare(dancer,searby,'Both clear same5/5; compare paid8G/two cards+heal+bot with7G/onecard+draw'))
    dancer_small=next(r for r in records if r['id']=='tactics/201/one_3_4/attack_0')
    soul_small=next(r for r in records if r['id']=='tactics/506/one_3_4/attack_0')
    comparisons.append(compare(dancer_small,soul_small,'Both single-card clear3/4: Dancer pays3G more for extra bodyHP, token and4 hero healing; Soul enemy-turn Dust liability outside current endpoint'))
    # Haste and Candy gate near hero thresholds. At15 no Haste; at10 no Candy.
    for hp in (9,10,14,15):
        enemy=[B(3,6)];s=body(654);s['a']+=int(hp<15)
        add(654,f'hero_{hp}','deploy_hold',[],enemy,[s],enemy,condition=f'Hero currentHP={hp}',
            features=dict(haste=hp<15,candy=hp<10,taunt=hp<10),unknown=['Future Taunt protection not priced'])
        if hp<15:
            aa,bb,alive,_=fight([s],enemy,0,0)
            if alive and hp<10:aa[0]['h']=min(7,aa[0]['h']+3)
            add(654,f'hero_{hp}','haste_trade',[],enemy,aa,bb,stage='after_own_turn_end',
                condition=f'HeroHP={hp}; ordinary3/6; Candy only ifHP<10 at Magic',path=['Play and check HP','Haste attack3/6','If granted Candy heal3 at own end'])
    # Summon is not Play: choose a known dustpile outcome, never count Magic.
    for revived in (602,7,115):
        u=body(revived);enemy=[B(2,1)]
        add(410,'bloxer_offer',f'summon_{revived}',[],enemy,[body(410),u],enemy,
            path=[f'Bloxer offered and chose {CARDS[revived]["name"]}; summon printedbody'],
            condition='Given dustpile offering; two available slots; summon does not trigger Magic',
            unknown=['Offer distribution, dustpile setup and future reply not priced'])
        if revived==115:
            aa,bb,_,_=fight([body(410),u],enemy,1,0)
            add(410,'bloxer_offer','spider_trades',[],enemy,aa,bb,
                path=['Summon Spider from offered dustpile','Spider Haste attacks2/1; both die'],condition='Spider actually offered; no Dust')
    # Knightdyne: non-equivalent lowestHP ties not guessed. This witness has
    # unique minima until last remaining enemy and never runs out of slots.
    enemy=[B(3,1),B(2,2),B(4,5)]
    bb=deepcopy(enemy);kills=0;steps=[]
    for n in range(4):
        if not bb:break
        m=min(u['h'] for u in bb);j=next(i for i,u in enumerate(bb) if u['h']==m)
        bb[j]=hit(bb[j],1);dead=bb[j]['h']<=0;kills+=int(dead);bb=live(bb)
        steps.append(f'Packet{n+1}: lowestHP={m}; killed={dead}')
    add(892,'knightdyne_chain','four_packets',[],enemy,[body(892)]+[B(2,3) for _ in range(kills)],bb,
        path=steps,condition='At most3 Spears; no target abilities/armor; unique or equivalent minimum',
        features=dict(spear_taunt_count=kills),unknown=['Taunt protection beyond endpoint not priced'])
    # Defensive counterfactual, kept as different roots rather than falsely
    # labelled a same-state replacement. Armor absorbs every1DMG packet.
    enemy=[B(1,1,armor=True),B(2,2),B(3,3)]
    add(892,'knightdyne_armor','four_packets_blocked',[],enemy,[body(892)],enemy,
        path=['All4 packets repeatedly target lowestHP Armor1/1; actual0DMG each'],
        condition='Lowest1HP enemy has Armor; no other triggers',features=dict(spear_taunt_count=0))
    # Hand-cap counterfactual for Hydra: play from6 ->5 then only2 draws fit.
    enemy=[B(2,6)]
    add(266,'hydra_hand6','magic_then_haste',[],enemy,[B(3,1)],[],gained=2,heal=3,
        path=['Initial hand6; playHydra ->5','Magic3 leaves enemy2/3; draw3, retain2 and burn1; heal3',
              'Haste attacks remaining2/3; Hydra survives3/1'],
        condition='Hero missing>=3; no fatigue or Turbo; explicit initialhand6',features=dict(burned_draws=1))
    # Mantis target counterfactual: all waves include own monsters and source.
    own=[B(2,2)];enemy=[B(3,3),B(2,1),B(1,2),B(4,3)]
    mantis=[]
    for j in range(4):
        bb=deepcopy(enemy);bb[j]=hit(bb[j],3);killed=bb[j]['h']<=0;bb=live(bb)
        aa=own+[body(964)];waves=[]
        if killed:aa,bb,waves=carousel(aa,bb)
        mantis.append(add(964,'carousel_target',f'kill_{j}',own,enemy,aa,bb,
            path=[f'Magic3 kills target index{j}',f'Carousel completes{len(waves)} full waves'],
            condition='All targets ordinary; each wave completes simultaneously; no triggered effects',
            features=dict(carousel_waves=waves)))
    comparisons.append(compare(mantis[0],mantis[1],'Kill3HP to keep a1HP death seed; killing1HP stops Carousel after one wave'))
    a=add(964,'carousel_target','ready_ally_attacks_first',own,enemy,
        mantis[0]['ledger']['own_after'],mantis[0]['ledger']['enemy_after'],damage=2,
        path=['If old2/2 is ready, attack enemy hero for2 before sacrificing it to Carousel',
              'Mantis3DMG kills index0; complete4 Carousel waves'],
        condition='Old2/2 ready; no enemy Taunt; heroHP>2 and no on-attack reactions; identical later endpoint')
    comparisons.append(compare(a,mantis[0],'An ally that will die to known friendly AoE may first use its legal attack; no extra card/Gold'))
    # A fresh Trashy cannot attack. This separate existing-unit root prices the
    # actual retaliation prevention without granting a fictitious free turn.
    own=[body(632)];enemy=[B(5,2)]
    add(632,'trashy_ready','safe_attack',own,enemy,own,[],used=[],paid=0,
        path=['Already ready Trashy2/5 attacks5/2; takes no retaliation'],condition='Not a deployment score; own-turn attack only')
    # Elder once ready: current attack vs guaranteed4DMG at end with one foe.
    own=[body(197)];enemy=[B(5,4)]
    aa,bb,_,_=fight(own,enemy,0,0)
    a=add(197,'elder_ready','attack',own,enemy,aa,bb,used=[],paid=0,stage='after_own_turn_end',
        path=['Attack5/4; take5; no end trigger'],condition='Elder ready; one ordinary enemy')
    b=add(197,'elder_ready','wait_for_end',own,enemy,own,[],used=[],paid=0,stage='after_own_turn_end',
        path=['Do not attack; end4 kills only enemy without retaliation'],condition='Same root; no need for earlier kill or another attack through Taunt')
    comparisons.append(compare(b,a,'With one4HP ordinary foe and no immediate urgency, not attacking avoids5HP loss'))
    return records,comparisons,notes


def build(out=None):
    out=HERE/'results' if out is None else out
    out.mkdir(parents=True,exist_ok=True)
    records,comparisons,notes=main_routes()
    from resource_routes import build_routes
    rr,cc,nn=build_routes();records+=rr;comparisons+=cc;notes+=nn
    ids=sorted({r['card_id'] for r in records})
    dossiers=[]
    for cid in ids:
        c=CARDS[cid]
        dossiers.append(dict(card_id=cid,name=c['name'],cost=c['cost'],source_text=c['effect_readable'],
            profile_kind='Agent promising tactics',reason=REASONS.get(cid,'Independent resource/sequence candidate review'),
            assessment_status='Conditional tactics only; no empirical whole-card calibration',global_score=None,
            inventory_convention='All played and erased cards charged; different from base dossier common-one-card N',
            records=[r for r in records if r['card_id']==cid]))
    # Rank only a matched stage and before-state. These are declared local
    # action families, not an assertion that all legal actions were searched.
    families=[]
    for root in ORDINARY:
        rs=[r for r in records if r['root']==root and r['ledger']['valuation_stage']=='after_current_turn_actions'
            and r['features'].get('endpoint_mechanics_complete',True)]
        bycard={}
        for r in rs:
            cid=r['card_id']
            if cid not in bycard or r['inventory_adjusted_action_margin']>bycard[cid]['inventory_adjusted_action_margin']:bycard[cid]=r
        order=sorted(bycard.values(),key=lambda r:r['inventory_adjusted_action_margin'],reverse=True)
        families.append(dict(root=root,ranked_actions=[dict(record=r['id'],name=CARDS[r['card_id']]['name'],J=r['inventory_adjusted_action_margin'],paid=r['ledger']['paid_gold'],cards_played=r['inventory']['cards_played'],unpriced=r['ledger']['unpriced']) for r in order],
            interpretation='Only if alternatives available/affordable; no response or SOUL benefit; cannot rank across stages or infer strongest whole card'))
    def dump(n,x):(out/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
    sources=[HERE/'build_tactics.py',HERE/'resource_routes.py',HERE/'tactic_core.py',HERE/'derive_recommendations.py',
        HERE.parent/'value_ledger.py',HERE.parent/'build_assessments.py',
        HERE.parents[3]/'skills/undercards/references/snapshot.json',
        HERE.parents[2]/'method-lab/2026-10-18/value_model.py',
        HERE.parents[2]/'method-lab/2026-10-18/statistical_inputs.json']
    commit=subprocess.check_output(['git','log','-1','--format=%H','--']+[str(p) for p in sources],text=True).strip()
    dirty=subprocess.check_output(['git','status','--porcelain','--']+[str(p) for p in sources],text=True).strip()
    dump('dossiers.json',dict(version='promising-tactics-1.0',source_commit=commit,source_dirty=bool(dirty),prices=CENTRAL,
        default_context=dict(soul='BRAVERY; current start already resolved',hero_hp=20,enemy_hero_hp=30,
            hand_size_at_most=4,no_relevant_artifacts=True,no_other_triggers=True,
            overrides='Specific record conditions override defaults; enough cash/slots for stated path, positioning explicitly feasible. No match continuation inferred.'),
        cards=dossiers))
    dump('comparisons.json',dict(comparisons=comparisons,notes=notes))
    dump('conditional-families.json',families)
    with (out/'actions.csv').open('w') as f:
        fields=['id','card_id','name','scenario','action','stage','paid','cards_net','G_before_played_cards','N_before_played_cards','J','unpriced']
        w=csv.DictWriter(f,fields,lineterminator='\n');w.writeheader()
        for r in records:
            w.writerow(dict(id=r['id'],card_id=r['card_id'],name=CARDS[r['card_id']]['name'],scenario=r['root'],action=r['action'],stage=r['ledger']['valuation_stage'],paid=r['ledger']['paid_gold'],cards_net=r['inventory']['net_relative_cards'],G_before_played_cards=r['conditional_gross_before_played_cards'],N_before_played_cards=r['payment_margin_before_played_cards'],J=r['inventory_adjusted_action_margin'],unpriced='; '.join(r['ledger']['unpriced'])))
    base=json.loads((HERE.parent/'results/dossiers.json').read_text())['cards']
    old={c['card_id'] for c in base};new=set(ids)
    dump('receipt.json',dict(new_focal_cards=len(new-old),total_curated_cards=len(old|new),new_records=len(records),new_comparisons=len(comparisons),
        source_commit=commit,source_dirty=bool(dirty),new_http_requests=0,credential_state='skipped; normal client credential_error',
        empirical_calibration=False,all_cards_globally_scored=False,
        note='Records are explicitly chosen counterfactuals, not independent match experiments or coverage accuracy'))
    return records,comparisons


if __name__=='__main__':
    build();print((HERE/'results/receipt.json').read_text())
