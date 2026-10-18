"""Reproducible sparse-value experiment; all writes stay beside this file."""
from pathlib import Path
import csv
import hashlib
import json
import math
import re

from value_model import (Asset, BodyScale, VERSION, finite, response_curve, crossing,
                         fixed_deadline_option, common_plan, hand_budget_value)

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SNAPSHOT=ROOT/'skills/undercards/references/snapshot.json'


def write_json(name,value):
    (HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def freeze_inputs():
    """Freeze small exact source excerpts; no dependency on cloud scorer code."""
    cards=json.loads(SNAPSHOT.read_text(encoding='utf-8'))['cards']
    groups={k:[c for c in cards if c.get('card_type')=='monster' and
        c.get('pool_category')=='ordinary_non_token' and c.get('cost')==k] for k in range(4,8)}
    ref=[dict(card_id=c['id'],attack=c['attack'],health=c['health'],
              weight=1/(4*len(group))) for group in groups.values() for c in group]
    # A deliberately tiny source bridge, not a new mechanism compiler.
    patterns=[('plain',r''),('hand_growth',r'Magic: Gain ATK \+(\d+)/HP \+(\d+) for each card in your hand\.'),
              ('ally_attack',r'Magic: Give an ally monster \+(\d+) ATK\.'),
              ('enemy_attack',r'Magic: Give all enemy monsters -(\d+) ATK\.'),
              ('damage_any',r'Magic: Deal DMG (\d+)\.'),
              ('draw',r'Magic: Draw a card\.'),
              ('self_damage',r'Magic: Deal (\d+) DMG to this\.')]
    profiles=[]
    for c in cards:
        if c.get('card_type')!='monster' or c.get('pool_category')!='ordinary_non_token':continue
        for kind,pattern in patterns:
            m=re.fullmatch(pattern,c['effect_readable'])
            if m:
                profiles.append(dict(card={k:c[k] for k in ('id','name','cost','attack','health','effect_readable','target')},
                                     feature_kind=kind,amounts=list(map(int,m.groups()))))
                break
    # Penetration is a conditional cross-SOUL test; no silent native-access assumption.
    responses=[c for c in cards if c['id'] in (79,96,100)]
    fields=('id','name','cost','effect_readable','soul')
    return dict(snapshot_sha256=hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest(),
        reference=ref,profiles=profiles,response_sources=[{k:c[k] for k in fields} for c in responses],
        design=dict(face_share=.2,threshold_weight=.4,draw_net_option_model_gold=.65,
                    face_damage_model_gold=.25,
                    enemy=(4,5),ally=(3,4),hand_after_play=4,enemy_count=1),
        origin='Exact 2026-10-05 snapshot excerpts; no empirical frequencies')


def card_endpoint(profile,scale,*,hand=4,enemy=(4,5),ally=(3,4),enemy_count=1,draw_value=.65,
                  face_damage_value=.25):
    if type(hand) is not int or not 0<=hand<=6:
        raise ValueError('Hand after playing, before Magic, must be an integer 0..6')
    if type(enemy_count) is not int or not 0<=enemy_count<=4:
        raise ValueError('Declared enemy count must be an integer 0..4')
    finite(draw_value,'Draw net option prior',0)
    finite(face_damage_value,'Face damage prior',0)
    for body in (enemy,ally):
        if body is None:continue
        if not isinstance(body,(tuple,list)) or len(body)!=2:
            raise ValueError('Numeric target body requires attack and health')
        finite(body[0],'Target attack',0);finite(body[1],'Target health',0)
        if body[1]==0:raise ValueError('Target bodies must be living')
    if enemy_count and enemy is None:raise ValueError('Enemy count requires an enemy body')
    c=profile['card'];a,h=c['attack'],c['health'];kind=profile['feature_kind'];n=profile['amounts']
    realized=0.;damage=0.;notes=[]
    if kind=='hand_growth': a+=n[0]*hand;h+=n[1]*hand
    elif kind=='ally_attack':
        realized=scale.value(ally[0]+n[0],ally[1])-scale.value(*ally) if ally else 0.
        notes.append('Other ally is a declared ordinary numeric body; later silence on it is not modeled.')
    elif kind=='enemy_attack':
        realized=enemy_count*(scale.value(*enemy)-scale.value(max(0,enemy[0]-n[0]),enemy[1]))
        notes.append('Enemy state change uses one shared body potential; no extra control/kill bonus.')
    elif kind=='damage_any':
        target=scale.value(*enemy)-scale.value(enemy[0],max(0,enemy[1]-n[0])) if enemy_count else 0.
        # An explicit alternative direct-face conversion, not an extra reward.
        realized=max(target,n[0]*face_damage_value)
        notes.append('Restricted ordinary enemy/face target menu; hero marginal price is a design prior.')
    elif kind=='draw':
        realized=min(1,7-hand)*draw_value
        notes.append('Draw net option prior .65; identity, Turbo, fatigue and long-run use are not solved.')
    elif kind=='self_damage':h-=n[0];damage=n[0]
    elif kind!='plain':raise ValueError('Unknown sparse feature kind')
    return Asset(a,h,c['attack'],c['health'],damage),realized,notes


def csv_write(name,rows):
    with (HERE/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    inputs_path=HERE/'inputs.json'
    if not inputs_path.exists():write_json('inputs.json',freeze_inputs())
    inputs=json.loads(inputs_path.read_text(encoding='utf-8'))
    design=inputs['design']
    scale=BodyScale(inputs['reference'],face_share=design['face_share'],threshold_weight=design['threshold_weight'])
    context=dict(hand=design['hand_after_play'],enemy=design['enemy'],ally=design['ally'],
        enemy_count=design['enemy_count'],draw_value=design['draw_net_option_model_gold'],
        face_damage_value=design['face_damage_model_gold'])
    rows=[];details=[]
    for p in inputs['profiles']:
        c=p['card'];asset,realized,notes=card_endpoint(p,scale,**context)
        silence=response_curve(scale,asset,realized=realized,kind='silence',response_cost=1,enemy_cash=6)
        damage=response_curve(scale,asset,realized=realized,kind='damage',packets=(4,),response_cost=3,enemy_cash=6)
        kill=response_curve(scale,asset,realized=realized,kind='silence_kill',response_cost=6,enemy_cash=6)
        rows.append(dict(id=c['id'],name=c['name'],cost=c['cost'],kind=p['feature_kind'],
            no_reply_value=silence['no_reply'],no_reply_margin=silence['no_reply']-c['cost'],
            actor_silence_loss=silence['loss'],p025_actor_silence_margin=silence['value_at_p']['0.25']-c['cost'],
            four_damage_value=damage['answered'],headshot_value=kill['answered'],
            full_card_strength_claimed=False))
        details.append(dict(profile=p,context=inputs['design'],silence=silence,damage4=damage,
                            headshot=kill,assumptions=notes))
    csv_write('card-probes.csv',rows)
    write_json('card-probes.json',dict(version=VERSION,scope='Sparse conditional value probes, not card strength ranking',rows=details))
    grid=[]
    for share in (.1,.2,.35):
        s=BodyScale(inputs['reference'],face_share=share)
        for health in range(1,16):
            for attack in range(0,16):
                grid.append(dict(face_share=share,attack=attack,health=health,value=s.value(attack,health),
                    plus_attack=s.value(attack+1,health)-s.value(attack,health),
                    plus_health=s.value(attack,health+1)-s.value(attack,health),
                    capped_attack_increment=s.effective_attack(attack+1)-s.effective_attack(attack)))
    csv_write('body-marginals.csv',grid)
    # Actual cards retain same cost. The comparison illustrates source-derived
    # growth-vs-immediate profiles, never fits their expected rank.
    by={p['card']['id']:p for p in inputs['profiles']};comparisons=[]
    for hand in range(0,7):
        curves=[]
        for cid in (49,292):
            asset,realized,_=card_endpoint(by[cid],scale,**dict(context,hand=hand))
            curves.append(response_curve(scale,asset,realized=realized,enemy_cash=6,response_cost=1))
        comparisons.append(dict(hand_after_play=hand,crossing_p=crossing(*curves),glyde=curves[0],warrior=curves[1]))
    damage_pair=[]
    for cid in (20,13):
        asset,realized,_=card_endpoint(by[cid],scale,**context)
        damage_pair.append(response_curve(scale,asset,realized=realized,kind='damage',packets=(4,),response_cost=3,enemy_cash=6))
    write_json('risk-crossings.json',dict(hand_growth=comparisons,
        same_cost_damage=dict(card_ids=[20,13],crossing_p=crossing(*damage_pair),curves=damage_pair)))
    # Completely synthetic equal-cost profiles isolate the two design variables.
    synthetic=[]
    for growth in range(0,7):
        for immediate in (0.,1.,2.,3.):
            asset=Asset(2+growth,2+growth,2,2)
            r=response_curve(scale,asset,realized=immediate,enemy_cash=6,response_cost=1)
            synthetic.append(dict(growth=growth,realized=immediate,**r))
    write_json('synthetic-risk-grid.json',synthetic)
    options=[]
    for chance in (0.,.1,.25,.5,.75,1.):
        for wait_cost in (0.,.25,.5,1.,2.):
            r=fixed_deadline_option(1.,(-1.,4.),(1-chance,chance),wait_cost)
            options.append(dict(favorable_window_weight=chance,foregone_value=wait_cost,**r))
    write_json('waiting-grid.json',options)
    diagnostics=dict(
        attack_6_to_7_at_hp7=scale.value(7,7)-scale.value(6,7),
        attack_9_to_10_at_hp7=scale.value(10,7)-scale.value(9,7),
        common_action=common_plan([[10.,0.],[0.,10.]],[.5,.5]),
        fixed_deadline=fixed_deadline_option(2.5,[1.,5.],[.5,.5],1.),
        replacement=dict(candidate=hand_budget_value([(6,7),(4,6)],6),
                         reference=hand_budget_value([(2,2),(4,6)],6)),
        source_profiles=len(rows),body_grid_rows=len(grid),empirically_calibrated=False)
    write_json('diagnostics.json',diagnostics)
    write_json('provenance.json',dict(version=VERSION,base_remote_commit='27854807a7e9e2867f8ef43bd2614478ac301a43',
        inputs_sha256=hashlib.sha256(inputs_path.read_bytes()).hexdigest(),
        sources={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in HERE.glob('*.py')},
        snapshot_sha256=inputs['snapshot_sha256'],old_model_modified=False,
        no_battle_search=True,no_lost_experiments_replayed=True))
    print(json.dumps(diagnostics,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
