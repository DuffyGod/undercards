"""Reduce frozen experiments to comparable tables, diagnostics and boundaries.

No fit to named cards, no new match simulation, no numerical LLM adoption.
"""
from pathlib import Path
import csv
import hashlib
import json
from collections import defaultdict

from statistical_value import Prices
from discount_statistics import expected_discount

HERE = Path(__file__).resolve().parent
OUT = HERE / 'statistical-results'
ROOT = HERE.parents[2]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
        '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
        ['| ' + ' | '.join(str(v) for v in row) + ' |' for row in rows])


def main():
    inputs = read(HERE / 'statistical_inputs.json')
    rows = read(OUT / 'final-scores.json')
    central = {(r['scenario'], r['id']): r for r in rows if r['parameter'] == 'central'}
    scenarios = ['aggro_wide', 'midrange_single', 'control_silence', 'empty_development', 'wounded_wide']
    labels = ['满血低费三体', '中费单体', '高费单体/沉默', '空场发展', '受伤低费三体']
    selected = [49, 984, 530, 649, 469, 43, 13, 15, 21, 20]
    sections = ['# 自动生成的统计摘要',
        '单位均为 model-G。原始卡池及资源统计不等于实战分布；参数范围不等于置信区间。',
        '## 共同净报价 E[Q] − cost',
        table(['卡牌'] + labels, [[inputs['cards'][str(cid)]['name']] +
            [f"{central[s, cid]['net_value']:+.3f}" for s in scenarios] for cid in selected])]
    attr_cases = [('aggro_wide', 13), ('aggro_wide', 15), ('aggro_wide', 20),
                  ('aggro_wide', 649), ('aggro_wide', 469), ('control_silence', 530)]
    sections += ['## 配对属性边际（其余输入相同）', table(
        ['场景', '卡牌', '+ATK', '固定原当前计划+ATK', '+HP', '计划改变质量'],
        [[s, central[s,cid]['name'], *[f"{central[s,cid][k]:.4f}" for k in
            ('plus_attack', 'fixed_policy_plus_attack', 'plus_health', 'changed_plan_mass')]]
         for s, cid in attr_cases])]
    paired = read(OUT / 'final-paired.json')
    sections += ['## 同一组参数的配对分差', table(
        ['场景', '左 − 右', '中央差', '11组参数最小', '11组参数最大', '配对MC标准误'],
        [[p['scenario'], inputs['cards'][str(p['left'])]['name'] + ' − ' + inputs['cards'][str(p['right'])]['name'],
          f"{p['differences'][0]['net_difference']:+.3f}",
          f"{p['min_shared_parameter_difference']:+.3f}", f"{p['max_shared_parameter_difference']:+.3f}",
          '全体枚举/无抽样' if p['paired_demand_mc_se'] is None else f"{p['paired_demand_mc_se']:.4f}"]
         for p in paired if p['left'] in (49,649,469) and p['scenario'] in scenarios])]
    resource_rows = []
    for tag in ('lower', 'final', 'higher'):
        result = [r for r in read(OUT / (tag+'-scores.json')) if r['parameter']=='central']
        for r in result:
            if r['id'] in (49,984,43) and r['scenario'] in ('aggro_wide','wounded_wide','control_silence'):
                resource_rows.append(dict(resource=tag, **r))
    sections += ['## 只换共同资源结构', table(
        ['资源', '场景', '卡牌', '净报价', '可支付率', '可放弃部署的机会指数'],
        [[r['resource'],r['scenario'],r['name'],f"{r['net_value']:+.3f}",
          f"{r['payable_share']:.3f}", f"{r['opportunity_index']:.3f}"] for r in resource_rows])]
    prices = Prices(inputs)
    scale = prices.scale
    body = []
    for a in range(2,11):
        body.append(dict(attack=a,health=7,
            target_hp_above_attack=sum(r['weight'] for r in inputs['reference'] if r['health']>a),
            effective_attack_increment=scale.effective_attack(a+1)-scale.effective_attack(a),
            body_increment=scale.value(a+1,7)-scale.value(a,7)))
    sections += ['## 身体攻击边际的数据来源', table(
        ['A/7 → (A+1)/7', 'P(目标HP>A)', '有效攻击增量', 'F增量'],
        [[str(r['attack']),f"{r['target_hp_above_attack']:.4f}",
          f"{r['effective_attack_increment']:.4f}",f"{r['body_increment']:.4f}"] for r in body])]
    # Literal exchangeable future-cost menu, not future hand identity or timing.
    discounts=[]
    for resource, data in inputs['resources'].items():
        handweights=defaultdict(float)
        for row in data['records']:
            handweights[row['hand_size_before_play']-1]+=row['weight']
        for cash in (3,5,8):
            for quality in (0.,1.,2.):
                discounts.append(dict(resource=resource,cash=cash,quality=quality,
                    value=sum(w*expected_discount(tuple(sorted(data['source_costs'])),h,cash,quality)
                              for h,w in handweights.items())))
    sections += ['## Lesser Dog：死亡时折扣菜单的先验敏感度',
        '以下是已发生Dust后的支付菜单增量；牌尚在场时只按tail保留，不等于整卡得分。',
        table(['资源','未来cash','每张未来卡净质量先验','折扣菜单增量'],
              [[r['resource'],r['cash'],r['quality'],f"{r['value']:.3f}"] for r in discounts])]
    # Exact opportunity to find a matching target, not chosen-plan realization.
    bulls=[]
    for resource,data in inputs['resources'].items():
        for cohort_name,cohort in inputs['cohorts'].items():
            for n in (1,3):
                v=0.
                for record in data['records']:
                    hand=record['hand_size_before_play']-1
                    mass=sum(r['weight'] for r in cohort if r['health']==hand)
                    v+=record['weight']*(1-(1-mass)**n)
                bulls.append(dict(resource=resource,cohort=cohort_name,targets=n,exact_target_opportunity=v))
    # Probe the existing price unit, do not fit six vanilla cards and call it validation.
    snapshot_path=ROOT/'skills/undercards/references/snapshot.json'
    snapshot=read(snapshot_path)
    vanilla=[dict(id=c['id'],name=c['name'],cost=c['cost'],attack=c['attack'],health=c['health'],
                  F=scale.value(c['attack'],c['health']),residual=scale.value(c['attack'],c['health'])-c['cost'])
             for c in snapshot['cards'] if c.get('card_type')=='monster'
             and c.get('pool_category')=='ordinary_non_token'
             and not c.get('effect_readable','').strip() and not c.get('base_statuses')]
    sections += ['## Gold锚的外部信息有多稀疏',
        '文字及初始状态均为空的普通怪物只有6张；种族、稀有度与设计强弱仍混杂，未拟合。',
        table(['卡牌','印刷费','身材','F','F−费用'],
              [[r['name'],r['cost'],f"{r['attack']}/{r['health']}",f"{r['F']:.3f}",f"{r['residual']:+.3f}"] for r in vanilla])]
    order_path=OUT/'paid-order-sensitivity.json'
    if order_path.exists():
        order=read(order_path)
        sections += ['## 共同付费菜单的顺序选择权',
            '候选与2G Froggit都必须打出，同付费同背景；这是孤立顺序增量，不加入主分。',
            table(['资源','场景','卡牌','顺序毛增量','可支付顺序增量','联合可支付质量'],
                  [[r['resource'],r['scenario'],r['name'],f"{r['ordering_gross_premium']:.4f}",
                    f"{r['payable_ordering_premium']:.4f}",f"{r['joint_payable_mass']:.4f}"]
                   for r in order['rows']])]
    clock=[]
    delta=scale.value(3,3)-scale.value(3,1)
    for face in (.15,.25,.4,.6):
        clock.append(dict(face_price=face,retention_crossing=(3*face-1)/delta,
                          physically_possible_crossing=0<=(3*face-1)/delta<=1))
    hashes={}
    for tag in ('final','lower','higher','higher-pair'):
        design=read(OUT/(tag+'-design.json'))
        hashes[tag]=dict(input_matches=design['input_sha256']==sha(HERE/'statistical_inputs.json'),
            source_matches={name:digest==sha(HERE/name) for name,digest in design['sources'].items()})
    assert all(v['input_matches'] and all(v['source_matches'].values()) for v in hashes.values())
    assert all(r['fixed_policy_plus_attack']<=r['plus_attack']+1e-9 for r in central.values())
    diagnostic=dict(schema_version=1,body_marginals=body,discount_prior_grid=discounts,
        bullseye_matching_target_opportunities=bulls,vanilla_anchor_audit=vanilla,
        clock_icecap_minus_rockpet_crossings=clock,
        final_producer_source_validation=hashes,
        source_hashes={'statistical_inputs.json':sha(HERE/'statistical_inputs.json'),
                       'snapshot.json':sha(snapshot_path),'summarize_statistics.py':sha(Path(__file__))},
        assertions=dict(fixed_current_plan_marginal_bounded_by_reoptimized=True,
                        central_rows=len(central),attributions_are_empirical_match_values=False))
    (OUT/'summary-diagnostics.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'summary-tables.md').write_text('\n\n'.join(sections)+'\n',encoding='utf-8')
    print(json.dumps(dict(validated_runs=list(hashes),central_rows=len(central),
        discount_prior_points=len(discounts),vanilla_anchors=len(vanilla),clock_crossings=clock),ensure_ascii=False))


if __name__=='__main__':main()
