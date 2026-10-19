"""Small new response window, not a restoration of the historical game engine.

Own finite physical payment menu, then one ordinary ready enemy's optional
attack. Enemy hand is declared empty; there is no new draw, income or play.
All attack targets and declining are allowed. Survival is a hard common goal.
"""
from dataclasses import asdict, replace

from run_study import METHOD  # makes the frozen analytical operators importable
from statistical_value import unit, hurt, deaths, FEATURES
from frontier import envelope, value, paired_range, number

SUPPORTED = (2, 4, 9, 13, 15, 20, 21, 43, 49, 168, 175, 187, 377, 602)


def reconstruct(solver, cid, backgrounds, enemy, quote, slots):
    """Read ONE quoted menu's physical endpoint without re-optimizing a part."""
    def bg(i):
        return unit(solver.cards[str(backgrounds[i])], root=False)
    plan = quote.plan
    if not plan.candidate_used:
        return tuple(bg(i) for i in plan.suffix), tuple(enemy), 0.
    hand = len(backgrounds)-len(plan.prefix)
    focal = dict(solver._focal_plans(cid, tuple(enemy), hand, 0))
    lottery = focal[plan.focal_action]
    if len(lottery) != 1 or abs(lottery[0][0]-1)>1e-12:
        raise ValueError('Random outcomes require a common chance policy, outside this small response probe')
    _, team, remaining, face, draw, discount = lottery[0]
    if draw or len(team)+len(plan.prefix)+len(plan.suffix)>slots:
        raise ValueError('Draw or capacity failure is outside the selected response subset')
    if any(u.trigger or u.dust=='child' for u in team):
        raise ValueError('On-kill/callback or death-child reply is outside this response subset')
    return tuple(bg(i) for i in plan.prefix)+tuple(team)+tuple(bg(i) for i in plan.suffix), remaining, face


def replies(own, enemy, own_hp):
    """Complete optional combat action of at most ONE ready ordinary enemy."""
    if len(enemy)>1:
        raise ValueError('Declare at most one ready enemy; this is not a multi-attacker turn')
    out=[dict(action='decline', own=own, enemy=enemy, own_hp=own_hp)]
    if not enemy or enemy[0][0]<=0:
        return out
    a,h=enemy[0]
    taunts=[i for i,u in enumerate(own) if u.taunt and u.h>0]
    targets=taunts if taunts else list(range(len(own)))
    if not taunts:
        out.append(dict(action='face',own=own,enemy=enemy,own_hp=own_hp-a))
    for i in targets:
        actor=own[i]
        if actor.trigger or actor.dust=='child':
            raise ValueError('Unsupported responsive trigger must not silently disappear')
        team=list(own);team[i]=hurt(actor,a)
        team,_=deaths(tuple(team),{})  # only dust=discount allowed; no post-reply casts
        remaining=() if h-actor.a<=0 else ((a,h-actor.a),)
        out.append(dict(action='attack_body_'+str(i),own=team,enemy=remaining,own_hp=own_hp))
    return out


def frontier_after_reply(solver,cid,backgrounds,enemy,cash,slots,own_hp=15,minimum_own_hp=1,
                         remove_focal_defense=False,minimum_own_bodies=0):
    if cid not in SUPPORTED:
        raise ValueError('Unsupported response mechanism; no zero substitute')
    number(cash,'cash',0)
    if slots!=4:
        raise ValueError('This response window requires an initially empty friendly board with four slots; occupied inert bodies cannot cancel when attacked')
    for v,name in ((own_hp,'own HP'),(minimum_own_hp,'survival floor')):
        if type(v) is not int or v<1:
            raise ValueError(name+' must be a positive integer')
    if minimum_own_hp>own_hp:
        raise ValueError('No healing operators in this declared response subset')
    if type(minimum_own_bodies) is not int or not 0<=minimum_own_bodies<=4:
        raise ValueError('Body-retention floor must be an integer from zero to four')
    if len(enemy)>1 or any(type(x) is not int or x<0 for pair in enemy for x in pair):
        raise ValueError('One ordinary nonnegative-integer body required')
    if any(h<=0 for _,h in enemy):
        raise ValueError('Enemy body must initially be alive')
    if remove_focal_defense and FEATURES[cid][0] not in ('armor','dodge'):
        raise ValueError('Defense counterfactual applies only to a standalone Armor/Dodge focal')
    quotes=solver.quotes(cid,tuple(backgrounds),tuple(enemy),slots)
    original_enemy=sum(solver.scale.value(a,h) for a,h in enemy)
    all_lines=[];background_lines=[];records=[]
    for q in quotes:
        if q.paid>cash:continue
        own,remaining,face=reconstruct(solver,cid,backgrounds,enemy,q,slots)
        if face>=30:
            raise ValueError('Enemy lethal is outside this nonterminal response probe')
        raw=(sum(solver.scale.value(u.a,u.h) for u in own)+original_enemy-
             sum(solver.scale.value(a,h) for a,h in remaining)+face*solver.face_price)
        if abs(raw-q.asset_value)>1e-8:
            raise AssertionError('Physical reconstruction disagrees with the declared complete menu')
        if remove_focal_defense:
            own=tuple(replace(u,dodge=0,armor=False) if u.root else u for u in own)
        outcomes=replies(own,remaining,own_hp)
        own_endpoint=[dict(attack=u.a,health=u.h,dodge=u.dodge,armor=u.armor,taunt=u.taunt) for u in own]
        guaranteed_hp=min(r['own_hp'] for r in outcomes)
        hp_witness=min(outcomes,key=lambda r:r['own_hp'])['action']
        guaranteed_bodies=min(len(r['own']) for r in outcomes)
        body_witness=min(outcomes,key=lambda r:len(r['own']))['action']
        if guaranteed_hp<minimum_own_hp or guaranteed_bodies<minimum_own_bodies:
            records.append(dict(plan=asdict(q.plan),paid=q.paid,feasible=False,
                                guaranteed_own_hp=guaranteed_hp,minimum_hp_reply=hp_witness,
                                guaranteed_body_count=guaranteed_bodies,minimum_body_reply=body_witness,
                                own_after_own=own_endpoint,
                                enemy_after_own=remaining))
            continue  # hard goal: never buy back lethal with a large body quote
        for r in outcomes:
            r['asset']=(sum(solver.scale.value(u.a,u.h) for u in r['own'])+original_enemy-
                        sum(solver.scale.value(a,h) for a,h in r['enemy'])+
                        (face-(own_hp-r['own_hp']))*solver.face_price)
        worst=min(outcomes,key=lambda r:r['asset'])
        line=dict(intercept=worst['asset'],slope=-q.paid,action=asdict(q.plan),
                  guaranteed_own_hp=guaranteed_hp,worst_reply=worst['action'],
                  guaranteed_body_count=guaranteed_bodies,minimum_body_reply=body_witness,
                  asset_worst_reply_own_hp=worst['own_hp'],minimum_hp_reply=hp_witness,
                  own_after=[[u.a,u.h,u.dodge,int(u.armor)] for u in worst['own']],
                  enemy_after=worst['enemy'])
        all_lines.append(line)
        if not q.plan.candidate_used:background_lines.append(line)
        records.append(dict(plan=asdict(q.plan),paid=q.paid,feasible=True,
                            guaranteed_own_hp=guaranteed_hp,worst_reply=worst['action'],
                            guaranteed_body_count=guaranteed_bodies,minimum_body_reply=body_witness,
                            own_after_own=own_endpoint,
                            minimum_hp_reply=hp_witness,enemy_after_own=remaining,
                            asset_worst_reply_own_hp=worst['own_hp'],
                            worst_asset=worst['asset']))
    return dict(curve=envelope(all_lines) if all_lines else None,
                background_curve=envelope(background_lines) if background_lines else None,
                own_hp=own_hp,minimum_own_hp=minimum_own_hp,
                minimum_own_bodies=minimum_own_bodies,
                enemy_hero_hp=30,
                condition=dict(background_ids=list(backgrounds),enemy_before=[list(e) for e in enemy],
                               cash=cash,initial_own_board='empty',slots=4,own_hp=own_hp,
                               minimum_own_hp=minimum_own_hp,enemy_hero_hp=30,
                               minimum_own_bodies=minimum_own_bodies,
                               face_price=solver.face_price,
                               body_face_share=getattr(solver.scale,'face_share',None),
                               body_threshold=getattr(solver.scale,'threshold_weight',None)),
                guarantee_feasible=bool(all_lines),
                enabled_goal_when_background_cannot=bool(all_lines) and not background_lines,
                enabled_survival_when_background_cannot=minimum_own_bodies==0 and bool(all_lines) and not background_lines,
                source_focal_defense_removed=remove_focal_defense,menus=records)


def compare_reply(left,right):
    return compare_reply_set({'same_prices':{'a':left,'b':right}},'a','b')


def compare_reply_set(settings_map,left,right,cash_price=None):
    if cash_price is not None:number(cash_price,'cash price',0,1)
    states=[];physical=[]
    price_fields={'face_price','body_face_share','body_threshold'}
    for results in settings_map.values():
        a,b=results[str(left)],results[str(right)]
        if a['condition']!=b['condition']:
            raise ValueError('Both candidates must share the physical window, goal and prices')
        states.append((a['guarantee_feasible'],b['guarantee_feasible']))
        physical.append({k:v for k,v in a['condition'].items() if k not in price_fields})
    if not states or any(p!=physical[0] for p in physical):
        raise ValueError('Price settings must preserve the SAME physical window and goal')
    if len(set(states))!=1:
        raise ValueError('Hard survival feasibility cannot change with normative prices')
    a,b=states[0]
    if not a or not b:
        board_goal=physical[0].get('minimum_own_bodies',0)>0
        return dict(left_feasible=a,right_feasible=b,numeric_difference=None,
                    status=('shared_goal_feasibility_differs' if a!=b else 'neither_guarantees_shared_goal') if board_goal
                           else ('survival_feasibility_differs' if a!=b else 'neither_guarantees_survival'))
    curves={s:{str(left):r[str(left)]['curve'],str(right):r[str(right)]['curve']}
            for s,r in settings_map.items()}
    delta=paired_range(curves,left,right,cash_price)
    return dict(left_feasible=True,right_feasible=True,numeric_difference=delta,status=delta['status'])
