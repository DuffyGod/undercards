"""Agent-authored conditional dossiers, not a card-text/game simulator.

Mechanism derivations here create explicit endpoint ledgers. The generic ledger
can price arbitrary externally reasoned endpoints without implementing a card.
Probe roots are local counterexamples, never a weighted environment sample.
"""
from pathlib import Path
from copy import deepcopy
from collections import Counter
from itertools import product
import json,csv
from value_ledger import *
SNAPSHOT=json.loads((ROOT/'skills/undercards/references/snapshot.json').read_text())
CARDS={c['id']:c for c in SNAPSHOT['cards']}


def B(a,h,**kw):return dict(a=a,h=h,**kw)
def payment_windows(cost):
    rows=[]
    for seat in (0,1):
        cash=1
        for turn in range(1,16):
            cash+=min(turn,10)+int(seat==1 and turn in (1,3,5,7,9))
            if cash>=cost:
                rows.append(dict(seat=seat,earliest_own_turn=turn,natural_total=cash,prior_spend_slack=cash-cost));break
    return dict(printed_cost_only=cost,windows=rows,scope='No discounts/Program/artifacts/SOUL/previous spending; funding fact, NOT actual playability or recommendation')

ROOTS={'empty':([],[]),'small':([],[B(3,5)]),'tall':([],[B(8,8)]),
       'wide':([],[B(3,1),B(2,1),B(1,1)]),'ally':([B(2,3)],[B(6,6)]),
       'asymmetric':([B(6,2)],[B(2,8)])}

# Every entry is an analyst mechanism judgement, with exact source text attached
# by the exporter. No prose parser quietly upgrades an unsupported ability.
PROFILES={
 2:('plain','独立早场；和同费攻击/存活阈值比较'),4:('plain','低费交换；高攻击换取易受清理'),15:('plain','普通站场参照；不是普遍最佳5G'),187:('plain','高血低攻；有拖延用途但收尾慢'),196:('plain','免费动作仍消耗手牌/格子'),602:('plain','2G独立站场桥接'),
 8:('toriel','高攻目标使减攻和自身增血同时兑现；低攻目标不强求出牌'),
 13:('debuff','多单位攻击总量与目标原ATK共同决定减攻收益'),
 16:('swap','在己残血高攻或敌低攻高血时改变交换；魔法不能选自己'),
 20:('damage2','击杀或跨过交换阈值优先；可打英雄补刀'),
 23:('hp3','给另一友军补HP改变存活阈值；不能给自身加血'),
 184:('set32','3/2覆盖可削弱大体或抬升友军；不能只按敌方原费用定价'),
 95:('self_attack_aoe','敌高攻低血密集时可清场；己方也受伤'),
 236:('hotdog','单体3伤与友方+3ATK二选一；同费与Plane比较'),
 669:('stickman','-3ATK提供及时交换保护，Delay赠卡需目标确实死亡'),
 727:('ruckus','3/3覆盖与3伤二选一；嘲讽保护另设维度'),
 115:('haste','1G2/1 Haste；能先换谁决定效率，不能只看免费杀敌'),
 312:('ponman','左侧1/3 Haste与右侧英雄治疗分支有不同交换阈值'),
 111:('statue','满足怪物数条件才有Haste，攻击前沉默可穿过防御；残留能力价值不乱定'),
 221:('skate','存活攻击会回手，不能同时记作留场4/5和返还一张牌'),
 291:('npc','Haste后Paralyze损失后续攻击窗口，不能按普通4/6长期攻击估价'),
 413:('rabbit','主动交换死亡能补牌并回库；活着未触发不提前领抽牌'),
 21:('plane','群伤1清尾血＋3点直伤＋Haste，可打破障碍再攻击'),
 277:('snail','即时Haste兼低费定向补牌；必须有可抽对象和可用卡位'),
 243:('bench','同费Aaron相比，抽牌需覆盖0.315037体价差'),
 225:('rod','每次己末活着才抽；初次出场末可抽，后续需生存'),
 44:('gyftrot','嘲讽大体兼可选补牌；承担等待和费用，抽牌不可用可选0'),
 311:('chest','死亡补2；先被打穿与活着占格是两种路径'),
 12:('chill','4/5兼单张定向检索；位置与牌库成分决定可用性'),
 605:('boat','临时借3张，没花掉会回库；不能当永久抽3'),
 628:('yarn','右侧2张先回库再抽3；净卡量和换掉的质量要分开'),
 43:('lesser','Dust后折扣只算实际未来用掉的余额，不能按当前手牌数全算现金'),
 49:('glyde','入场后剩余手牌带来身材；上手难度与高密度需求相连'),
 307:('tree','每个活着的己方开始增长1攻，晚到缺少兑现窗口'),
 385:('eye','Magic和每己开始产Spying；信息与对手实际多支付费用分开'),
 299:('bear','需要友军攻击/对位；可由对手规避，不能默认碰到高收益位置'),
 649:('car','其它怪数决定单体伤害，<=3伤才有Haste；空场差但可以等待'),
 984:('archer','出牌后手牌数决定伤害；恰杀才有Clover，不是击杀都有'),
 17:('knight','主动攻击且存活才回血，敌先攻和互死不回血'),
 60:('papyrus','Charge首击可打脸，击杀后追加只能打怪；Program有额外支付'),
 62:('undyne','逐次1伤最低HP十次；没有目标的次数才转Spear，护甲挡伤不转'),
 444:('jevil','多种Chaos Weapon选择改善适应性；随机施法与完整武器集合暂不硬凑总分'),
 61:('asgore','杀所有受伤怪物包含己方，适合准备残血后兑现'),
 176:('bounce','回手暂时移除敌身材却保留其再出资源；不是免费永久杀'),
 1:('defense','Taunt保护依赖敌可攻击量及目标，裸体价不是全部价值'),
 9:('charge','Charge额外当前攻击；回击死亡要扣除自身身体'),
 168:('defense','Dodge一次大包与连续小包不同'),175:('defense','Armor抗多次1伤，不能当一次盾'),377:('defense','一次Dodge与2HP脆弱性共同定价'),
}


def hit(u,d):
    v=deepcopy(u)
    if d>0 and v.get('dodge',0):v['dodge']-=1;return v
    v['h']-=max(0,d-int(v.get('armor',False)));return v

def live(xs):return [u for u in xs if u['h']>0]

def choose(records):
    # Exact declared central-price choice for this endpoint only, not a global
    # policy/Gold target. All legal alternatives remain saved for price queries.
    return max(records,key=lambda r:quote(r)['net_payment_margin'])


def base(cid,root,**events):
    own,enemy=deepcopy(ROOTS[root]);c=CARDS[cid]
    focal=[] if c['card_type']=='spell' else [B(c['attack'],c['health'],source='focal')]
    l=dict(own_before=own,enemy_before=enemy,own_after=deepcopy(own)+focal,enemy_after=deepcopy(enemy),
           paid_gold=c['cost'],events=events,unpriced=[],valuation_stage='deployment',scope='Conditional local endpoint with ordinary targets; one ordinary card commitment is common baseline')
    return l


def combat_options(l,cid,*,charge=False,silence=False,knight=False,chain=False,armor=False):
    """One-card hand-derived combat endpoint alternatives, at most four foes.

    Generic combat identity, not a multi-turn opponent simulator. No target
    abilities/Dust in these ordinary probes. All branches remain explicit.
    """
    start=deepcopy(l);f=start['own_after'][-1];f['armor']=armor
    options=[start];stack=[(start,True)]
    while stack:
        cur,first=stack.pop();f=cur['own_after'][-1]
        if first and charge:
            end=deepcopy(cur);end['events']['hero_damage']=end['events'].get('hero_damage',0)+f['a'];end['action']='attack hero';options.append(end)
        for i,e in enumerate(cur['enemy_after']):
            end=deepcopy(cur);x=deepcopy(e)
            if silence:x.pop('armor',None);x.pop('dodge',None)
            aa=hit(f,x['a']);bb=hit(x,f['a']);killed=bb['h']<=0
            if knight and aa['h']>0:aa['h']=min(f['h'],aa['h']+min(x['h'],max(0,f['a']-int(x.get('armor',False)))))
            end['own_after']=cur['own_after'][:-1]+([aa] if aa['h']>0 else [])
            end['enemy_after']=live([bb if j==i else u for j,u in enumerate(cur['enemy_after'])])
            end['action']='attack ordinary monster'
            if cid==221 and aa['h']>0:
                end['own_after']=cur['own_after'][:-1];end['events']['usable_cards']=end['events'].get('usable_cards',0)+1
                end['scope']+='; through own Delay return, not a standing body'
                end['valuation_stage']='after_Delay_return'
            if cid==413 and aa['h']<=0:
                end['events']['usable_cards']=end['events'].get('usable_cards',0)+1
                end['future_feature']='one Rabbit added to deck; no immediate extra hand value'
            options.append(end)
            if chain and killed and aa['h']>0 and end['enemy_after']:stack.append((end,False))
    return options


def derive(cid,kind,root):
    l=base(cid,root);own=l['own_before'];enemy=l['enemy_before'];c=CARDS[cid];out=[]
    if kind=='plain':return [l]
    if kind in ('defense',):
        l['unpriced']=['Unexposed Taunt/Armor/Dodge continuation; see fixed-packet resistance dimension'];return [l]
    if kind=='toriel':
        for i,e in enumerate(enemy):
            if e['a']<1:continue
            q=deepcopy(l);gain=e['a']-1;q['enemy_after'][i]['a']=1;q['own_after'][-1]['h']+=gain;q['condition']=f"enemy ATK={e['a']}, HP={e['h']}";out.append(q)
    elif kind=='debuff':
        l['enemy_after']=[dict(e,a=max(0,e['a']-1)) for e in enemy];out=[l]
    elif kind=='swap':
        for side in ('own','enemy'):
            xs=l[side+'_before']
            for i,u in enumerate(xs):
                q=deepcopy(l);q[side+'_after'][i]=dict(u,a=u['h'],h=u['a'])
                q[side+'_after']=live(q[side+'_after']);out.append(q)
    elif kind=='hp3':
        for i,u in enumerate(own):
            q=deepcopy(l);q['own_after'][i]['h']+=3;out.append(q)
    elif kind=='set32':
        for side in ('own','enemy'):
            for i,u in enumerate(l[side+'_before']):
                q=deepcopy(l);q[side+'_after'][i]=B(3,2);out.append(q)
    elif kind=='self_attack_aoe':
        l['own_after']=live([hit(u,u['a']) for u in own]);l['enemy_after']=live([hit(u,u['a']) for u in enemy]);out=[l]
    elif kind in ('damage2','hotdog','ruckus','car','archer'):
        d={'damage2':2,'hotdog':3,'ruckus':3,'car':len(own)+len(enemy),'archer':3}[kind]
        # Archer hand-after-play=3 is one explicit witness, not random hand prior.
        for i,e in enumerate(enemy):
            q=deepcopy(l);x=hit(e,d);q['enemy_after']=live([x if j==i else u for j,u in enumerate(enemy)])
            if kind=='archer' and x['h']==0 and len(q['own_after'])<4:q['own_after'].append(B(2,3,source='Clover'))
            choices=combat_options(q,cid) if kind=='car' and d<=3 else [q]
            out.extend(choices)
            if kind=='ruckus':
                q=deepcopy(l);q['enemy_after'][i]=B(3,3);out.append(q)
        if kind in ('damage2','hotdog'):
            q=deepcopy(l);q['events']['hero_damage']=d;out.append(q)
        if kind=='hotdog':
            for i,u in enumerate(own):
                q=deepcopy(l);q['own_after'][i]['a']+=3;out.append(q)
        if kind=='ruckus':
            for i,u in enumerate(own):
                q=deepcopy(l);q['own_after'][i]=B(3,3);out.append(q)
        if kind=='ruckus':l['unpriced']=['Taunt future protection'];[q['unpriced'].extend(l['unpriced']) for q in out]
    elif kind=='stickman':
        for i,e in enumerate(enemy):
            q=deepcopy(l);q['enemy_after'][i]['a']=max(0,e['a']-3);q['unpriced']=['Delay gift only if target dies: separate conditional event'];out.append(q)
    elif kind in ('haste','ponman','statue','skate','npc','rabbit','plane','snail','charge','papyrus','knight'):
        if kind=='plane':
            l['enemy_after']=live([hit(e,1) for e in enemy]);l['events']['hero_damage']=3
        if kind=='ponman':
            l['condition']='left placement: +2HP before the Haste attack'
            l['own_after'][-1]['h']+=2  # explicit left placement
        if kind=='snail':l['events']['usable_cards']=2;l['condition']='two <=1G targets exist and both retained/usable'
        if kind=='statue' and len(own)+1>len(enemy):
            l['unpriced']=['No current Haste under count condition; future attack Silence'];return [l]
        if kind=='papyrus':l['condition']='11 <= available G < 13, Program cannot pay; ordinary targets only'
        out=combat_options(l,cid,charge=kind in ('charge','papyrus'),silence=kind=='statue',knight=kind=='knight',chain=kind=='papyrus')
        if kind=='papyrus':
            # Both balance conditions retained; Program payment is not free Armor.
            l2=deepcopy(l);l2['paid_gold']+=2;l2['condition']='13G available, Program(2) pays';out+=combat_options(l2,cid,charge=True,chain=True,armor=True)
        if kind=='npc':
            for q in out:q['unpriced'].append('Paralyze opportunity loss on following own turn')
        if kind=='knight':
            for q in out:
                q['scope']='One active attack from full 9HP, hp-loss heal ruling; future repeat conditional'
                q['valuation_stage']='later_active_attack_after_survival'
    elif kind in ('bench','rod','gyftrot','chest','chill','boat','yarn'):
        counts={'bench':(0,1),'rod':(0,1,2,3),'gyftrot':(0,1,2),'chest':(0,2),'chill':(0,1),'boat':(0,),'yarn':(0,1)}[kind]
        for n in counts:
            q=deepcopy(l);q['events']['usable_cards']=n;q['condition']=f'{n} actually retained usable extra cards; ordinary card use excluded'
            if kind=='chest' and n:
                q['valuation_stage']='post_Dust_projection'
                q['unpriced']=['Past body services and cause of death absent in this projection']
                q['own_after']=deepcopy(own);q['condition']='Chest has died, both Dust draws retained; no simultaneous 2/2 stock';q['scope']='Post-Dust continuation, ordinary probes; death cause not scored as a free enemy kill'
            if kind=='rod':q['valuation_stage']='own_end' if n<=1 else 'future_successful_end_windows'
            if kind=='boat':
                q['valuation_stage']='after_Delay_return'
                q['condition']='No borrowed cards used; all returned at Delay, no permanent extra hand quantity'
                q['unpriced']=['Temporary access may enable actions, not priced as permanent cards']
            if kind=='yarn':q['condition']=f'net card quantity {n}; two rightmost returns and three retained draws must support this';q['unpriced']=['Quality and access change of rightmost cards sent to deck']
            if kind=='chill':q['unpriced']=['Monster/spell targeting premium beyond usable card count']
            if kind=='gyftrot':q['unpriced']=['Taunt future protection']
            out.append(q)
        if kind=='boat' and len(own)<=2:
            q=deepcopy(l);q['own_after'].append(B(2,1,source='borrowed Spider'))
            q['paid_gold']+=1;q['events']['usable_cards']=0
            q['condition']='Borrow Spider then pay 1G to play it; no attack; other borrowed cards return'
            q['valuation_stage']='after_Delay_return'
            q['scope']='Complete declared 4G Boat+Spider endpoint; Spider body replaces any card-access credit'
            out.append(q)
    elif kind=='lesser':
        # Deployment and Dust endpoint kept separate; cannot collect both body
        # stock and dead-card reward at the same checkpoint.
        out=[l]
        for n in (0,1,3,5):
            q=deepcopy(l);q['own_after']=deepcopy(own);q['events']['usable_gold']=n;q['condition']=f'after Dust, actual redeemed discount {n}G';q['scope']='Post-Dust continuation; lost body not retained, no death-cause kill credited';q['valuation_stage']='post_Dust_projection';q['unpriced']=['Prior ordinary body services not valued in this projection'];out.append(q)
    elif kind=='glyde':
        for h in (0,1,3,6):
            q=deepcopy(l);q['own_after'][-1]=B(2+h,2+h,source='focal');q['condition']=f'hand AFTER paying card has {h} cards';out.append(q)
    elif kind=='tree':
        for k in (0,1,2,3):
            q=deepcopy(l);q['own_after'][-1]['a']+=k;q['valuation_stage']='deployment' if not k else 'later_own_start_after_survival';q['condition']=f'survived {k} own turn starts, no HP loss in this conditional path';out.append(q)
    elif kind=='eye':
        for n in (0,1,3):
            q=deepcopy(l);q['events']['usable_gold']=n;q['condition']=f'Spying actually causes {n} additional enemy G expenditure';q['unpriced']=['Enemy-hand information and unspent cost disruption; not automatic 1G per Spying'];out.append(q)
    elif kind=='bear':
        for i,u in enumerate(own):
            for j,e in enumerate(enemy):
                q=deepcopy(l);q['enemy_after']=live([hit(x,u['a']) if k==j else x for k,x in enumerate(enemy)]);q['condition']='ally and target occupy matching opposite positions';out.append(q)
        if not own or not enemy:
            l['unpriced']=['No assumed Magic payout without ally/opposite target'];out=[l]
    elif kind=='undyne':
        # Only ordinary no-status targets, deterministic tie convention is safe
        # for these roots only when all tied targets will die; arbitrary
        # non-equivalent surviving ties are rejected, not optimistically chosen.
        q=deepcopy(l);xs=deepcopy(enemy);unused=0
        for packet_index in range(10):
            if not xs:unused+=1;continue
            lowest=min(x['h'] for x in xs)
            tied=[x for x in xs if x['h']==lowest]
            if len({(x['a'],x['h']) for x in tied})>1 and sum(x['h'] for x in xs)>10-packet_index:
                raise ValueError('Undyne non-equivalent surviving tie is unresolved')
            i=min(range(len(xs)),key=lambda j:(xs[j]['h'],j));xs[i]=hit(xs[i],1);xs=live(xs)
        q['enemy_after']=xs
        if unused and len(q['own_after'])<4:q['own_after'].append(B(unused,unused,source='Spear'))
        q['condition']='ordinary targets, no defensive status; no-target packets alone become Spear';out=[q]
    elif kind=='asgore':
        # Ordinary probe bodies are marked explicitly as damaged, not inferred
        # from low printed health. Different from arbitrary HP<=ATK.
        l['condition']='all pre-existing probe monsters are full HP, none killed by Magic';out=[l]
        q=deepcopy(l)
        q['enemy_before']=[dict(u,max_h=u['h']+1) for u in enemy]
        q['enemy_after']=[]
        q['condition']='all ordinary enemies have max HP=current HP+1, allies full; all damaged enemies killed'
        out.append(q)
        if own:
            z=deepcopy(q);z['own_before']=[dict(u,max_h=u['h']+1) for u in own]
            z['own_after']=[u for u in z['own_after'] if u.get('source')=='focal']
            z['condition']='both all old allies and enemies damaged, Asgore new full HP; symmetric collateral paid'
            out.append(z)
    elif kind=='bounce':
        for i,e in enumerate(enemy):
            q=deepcopy(l);q['enemy_after']=[x for j,x in enumerate(enemy) if j!=i];q['condition']='enemy hand full, return kills ordinary target';out.append(q)
            z=deepcopy(q);z['events']['usable_cards']=-1;z['condition']='enemy has hand space, retains target as replayable card';z['unpriced']=['Replay quality differs from one generic usable card'];out.append(z)
    elif kind=='jevil':
        l['unpriced']=['Complete Chaos Weapon choice and random spell branch; known alternatives have separate attainable ledgers'];out=[l]
        for i,e in enumerate(enemy):
            q=deepcopy(l);q['enemy_after']=[x for j,x in enumerate(enemy) if j!=i];q['condition']='if Devilsknife offered/chosen, exactly one ordinary enemy so random kill certain';q['scope']='Known attainable Jevil choice, not upper bound or full option-set valuation'
            if len(enemy)==1:q['unpriced']=['Chaos-menu binding is conditional, not a complete option-set score'];out.append(q)
    if kind=='jevil':
        # These are conditional attainable choices if offered by the Chaos menu;
        # the source snapshot does not enumerate that menu as a typed relation.
        d=3-len(own)
        q=deepcopy(l);q['enemy_after']=live([hit(e,d) for e in enemy]);q['events']['hero_damage']=d
        q['condition']=f'if Spade Chaos offered/chosen, {d} empty slots after Jevil deployment'
        q['unpriced']=['Full menu membership/other choices not independently bound; conditional attainable option only']
        out.append(q)
        for n,discount in ((0,0),(1,0),(3,0),(3,6)):
            q=deepcopy(l);q['events']=dict(usable_cards=n,usable_gold=discount)
            q['condition']=f'if Diamond Chaos offered: {n} draws retained/usable, {discount}G discount actually redeemed later'
            q['valuation_stage']='conditional_draw_and_discount_redemption'
            q['unpriced']=['Menu binding and future card quality; not free 6G now'];out.append(q)
        q=deepcopy(l);q['events']['hero_heal']=7
        q['condition']='if Heart Chaos offered, hero missing at least7HP, probe monsters full HP'
        q['unpriced']=['Menu binding and alternative choices'];out.append(q)
        q=deepcopy(l);q['own_after']=[dict(u,a=u['a']+1,h=u['h']+2) for u in l['own_after']]
        q['condition']='if Jevilstail offered, all current allies including Jevil gain1ATK2HP'
        q['unpriced']=['Menu binding; hand monsters +1/+1 and random Club Chaos branch not priced'];out.append(q)
    if not out:
        # No assumption that mandatory Magic can be skipped or must be wasted.
        l['unpriced']=['No legal target witness here; playability not inferred, no forced deployment recommendation'];l['no_target_witness']=True;out=[l]
    return out


def packet_dimension(c):
    if c['card_type']!='monster':return None
    u=B(c['attack'],c['health'])
    if c['id'] in (168,377):u['dodge']=1
    if c['id']==175:u['armor']=True
    result=[]
    for packets in ([1],[1,1,1],[3],[5],[3,3]):
        x=deepcopy(u)
        for p in packets:
            if x['h']>0:x=hit(x,p)
        result.append(dict(packets=packets,remaining_hp=max(0,x['h']),survives=x['h']>0,body_reference_after=F(x['a'],x['h']),
                           scope='Fixed external non-retaliating packets on printed body only; not whole-card response or Dust accounting'))
    return result


def build(out):
    out.mkdir(parents=True,exist_ok=True);dossiers=[];rows=[]
    for cid,(kind,reason) in PROFILES.items():
        c=CARDS[cid];records=[]
        for root in ROOTS:
            for i,l in enumerate(derive(cid,kind,root)):
                record=dict(id=f'{cid}/{root}/{i}',root=root,ledger=l,valuation=analyze(l));records.append(record)
                a=record['valuation'];q=a['central'];rows.append(dict(card_id=cid,name=c['name'],kind=kind,root=root,variant=i,
                    gross=q['absolute_gross'],net=q['net_payment_margin'],optional_surplus=q['decline_or_play_surplus'],
                    gross_low=a['price_sensitivity']['gross'][0],gross_high=a['price_sensitivity']['gross'][1],
                    condition=l.get('condition','current endpoint'),unpriced='; '.join(l['unpriced'])))
        if kind=='lesser':
            for n in (0,1,3,5):
                l=dict(own_before=[],enemy_before=[B(5,5)],own_after=[],enemy_after=[],paid_gold=6,events=dict(usable_gold=n),unpriced=[],
                    valuation_stage='after_active_mutual_trade_and_discount_redemption',condition=f'5/5 Lesser attacks ordinary5/5, both die, then {n}G discount actually redeemed',
                    scope='Complete conditional trade+Dust path; includes enemy removal, no remaining Lesser body; future same other plays cancel except redeemed Gold')
                rec=dict(id=f'{cid}/mutual_dust/{n}',root='mutual_dust',ledger=l,valuation=analyze(l));records.append(rec)
                a=rec['valuation'];q=a['central'];rows.append(dict(card_id=cid,name=c['name'],kind=kind,root='mutual_dust',variant=n,gross=q['absolute_gross'],net=q['net_payment_margin'],optional_surplus=q['decline_or_play_surplus'],gross_low=a['price_sensitivity']['gross'][0],gross_high=a['price_sensitivity']['gross'][1],condition=l['condition'],unpriced=''))
        dossier=dict(card_id=cid,name=c['name'],cost=c['cost'],source_text=c['effect_readable'],profile_kind=kind,
            assessment_status='Agent conditional mechanism dossier; no empirical calibration',reason=reason,records=records,
            fixed_packet_dimension=packet_dimension(c),global_score=None,
            unknown='No environment frequency, full match value or unconditional timing cost inferred')
        dossiers.append(dossier)
    catalog=[]
    for c in SNAPSHOT['cards']:
        if c['pool_category']!='ordinary_non_token':continue
        cid=c['id'];catalog.append(dict(card_id=cid,name=c['name'],cost=c['cost'],type=c['card_type'],soul=c['soul'],
            effect=c['effect_readable'],printed_body_reference=None if c['card_type']!='monster' else F(c['attack'],c['health']),
            absolute_whole_card=None,has_agent_conditional_dossier=cid in PROFILES,
            assessment_status='conditional dossier available' if cid in PROFILES else 'awaiting Agent/DeepSeek opportunity review; body reference is NOT card rating',
            numeric_features=dict(cost=c['cost'],attack=c['attack'],health=c['health']),
            printed_payment_windows=payment_windows(c['cost']),
            holding_model=dict(joint_executable_window_q=None,inventory_cost='extra_burns times card shadow price',foregone_tempo_cost=None,replacement_surplus=None,rule='Optional use after observation; no forced bad deployment; no fixed delay penalty'),
            dossier=f'dossiers.json#card-{cid}' if cid in PROFILES else None))
    def dump(n,x):(out/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
    dump('dossiers.json',dict(version=VERSION,prices=CENTRAL,price_corners=PRICE_CORNERS,unweighted_conditional_records=True,cards=dossiers))
    dump('catalog.json',dict(version=VERSION,scope='All ordinary non-token cards; no pending card silently treated as plain',cards=catalog))
    with (out/'conditional-values.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    dump('receipt.json',dict(version=VERSION,catalog_cards=len(catalog),agent_dossiers=len(dossiers),conditional_records=len(rows),
        profile_types=Counter(p[0] for p in PROFILES.values()),new_api_calls=0,empirically_calibrated=False,
        interpretation='Agent-supplied conditional endpoints and model prices, no weighted meta expectation or global ranking; unpriced fields remain public'))
    return dossiers

if __name__=='__main__':
    build(HERE/'results');print((HERE/'results/receipt.json').read_text())
