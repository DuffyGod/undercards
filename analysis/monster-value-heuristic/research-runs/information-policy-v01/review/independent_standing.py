"""Independent standing-purpose proof using the pre-existing independent kernel.

Imports no production engine or belief code. Reads selected production artifacts
only after deriving the independent bounds, as a schema/number consistency check.
"""
from dataclasses import replace, asdict
from pathlib import Path
import gzip
import hashlib
import json
import independent_hidden_menu as kernel

HERE=Path(__file__).resolve().parent

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def leaf_score(s):return (int(s.ally is not None),s.hp)


def hold_then_jerry(spell):
    initial=kernel.State(spell=spell,spell_generated=True)
    terminals=[]
    for first_trace,after_first in kernel.enemy_window(initial):
        late=dict(kernel.deployments(after_first))['play_14']
        # Newly played Jerry has no Haste; no attacks this own turn. Ending is
        # an actual shared policy, independent of hidden spell and public branch.
        late=replace(late,enemy_acted=False)
        for last_trace,end in kernel.enemy_window(late):
            terminals.append((first_trace,last_trace,end))
    assert terminals
    assert all(end.ally is not None and end.ally.card==14 and end.ally.health>0
               for _,_,end in terminals)
    worst=min(terminals,key=lambda x:x[2].hp)
    return {
        'enemy_terminal_action_histories':len(terminals),
        'all_terminal_histories_retain_jerry':True,
        'minimum_player_hp':worst[2].hp,
        'minimum_jerry_health':min(e.ally.health for _,_,e in terminals),
        'worst_hp_witness':{'enemy_first':worst[0],'enemy_second':worst[1],
                            'terminal':asdict(worst[2])},
    }


def only_aaron_world():
    initial=kernel.State(hand=(15,),spell=86,spell_generated=True)
    root_rows=[]
    # All own root action traces: end, or play Aaron then end. One card, 5G.
    for root_trace,root_end in kernel.own_window(initial):
        replies=[]
        for first_trace,after_first in kernel.enemy_window(root_end):
            next_own=replace(after_first,ally=replace(after_first.ally,attacked=False)
                             if after_first.ally else None)
            choices=[]
            for own_trace,after_own in kernel.own_window(next_own):
                start_last=replace(after_own,enemy_acted=False)
                last=[(leaf_score(e),trace,e) for trace,e in kernel.enemy_window(start_last)]
                worst=min(last,key=lambda x:x[0])
                choices.append((worst[0],own_trace,worst))
            best=max(choices,key=lambda x:x[0])
            every_choice_has_kill_reply=all(choice[2][0][0]==0 for choice in choices)
            replies.append((best[0],first_trace,best,every_choice_has_kill_reply))
        worst=min(replies,key=lambda x:x[0])
        root_rows.append({'root_trace':root_trace,'worldwise_purpose_upper_value':worst[0],
            'enemy_first_witness':worst[1],
            'best_own_continuation_against_witness':worst[2][1],
            'enemy_final_witness':worst[2][2][1],
            'terminal':asdict(worst[2][2][2]),
            'all_own_continuations_at_first_witness_have_enemy_kill_reply':worst[3]})
    assert all(r['worldwise_purpose_upper_value'][0]==0 for r in root_rows)
    assert all(r['all_own_continuations_at_first_witness_have_enemy_kill_reply'] for r in root_rows)
    best=max(r['worldwise_purpose_upper_value'] for r in root_rows)
    assert best==(0,12),best
    return {'world':86,'generated':True,'own_hand':[15],
            'all_root_choices_infeasible_even_with_world_revealed':True,
            'upper_value':best,'root_rows':root_rows}


def inspect_main(independent):
    batch=HERE.parent
    names=['card14-single-2G-hp.json.gz','baseline-5G-single-2G-hp.json.gz',
           'card14-single-2G-standing.json.gz','baseline-5G-single-2G-standing.json.gz']
    rows=[]
    for name in names:
        path=batch/'main'/name
        data=json.load(gzip.open(path,'rt'))
        c,r=data['config'],data['result']
        s=c['scenario']
        assert [w['opponent_hand_ids'] for w in c['worlds']]==[[79],[86]]
        assert all(w['opponent_hand_generated']==[True] for w in c['worlds'])
        assert s['gold_before_play']==5 and s['opponent_gold_before_response']==2
        assert s['own_player_hp']==15 and not s['ally_bodies_before_play']
        assert all(s[k]==0 for k in ['next_own_gold_income','next_opponent_gold_income',
                                    'next_natural_draw_count','next_opponent_natural_draw_count'])
        assert len(s['enemy_bodies'])==1
        b=s['enemy_bodies'][0]
        assert (b['card_id'],b['attack'],b['health'],b['max_health'])==(246,3,6,6)
        assert [b[k] for k in ['printed_cost','base_cost','current_cost']]==[4,4,4]
        assert r['known'] is True and r['status']=='known'
        assert r['declared_world_envelope_complete_for_server'] is False
        assert r['probabilities_inferred'] is False and r['calibrated_win_probability'] is None
        assert r['oracle_is_playable_under_hidden_information'] is False
        p=r['common_policy']
        if 'standing' in name:
            assert c['task']=={'kind':'joint','constraints':{'min_own_living_count':1}}
            if name.startswith('card14'):
                assert s['hand_ids']==[14,15] and p['value']==[1,9]
                assert p['feasible'] is True and p['guaranteed_player_hp']==9
                assert r['informed_world_upper_bound']['guaranteed_player_hp']==12
            else:
                assert s['hand_ids']==[15] and p['value']==[0,12]
                assert p['feasible'] is False and p['guaranteed_player_hp'] is None
        else:
            assert c['task']=={'kind':'hp'} and p['value']==[9]
            assert p['feasible'] is True and p['guaranteed_player_hp']==9
            if name.startswith('card14'):
                assert r['informed_world_upper_bound']['value']==[12]
                assert r['information_gap_hp']==3
        rows.append({'path':str(path.relative_to(batch)), 'gzip_sha256':digest(path),
            'version':r['version'],'reported_source_hashes':r['source_hashes'],
            'common_policy':p,'root_action':r['root_action'],
            'information_gap_hp':r['information_gap_hp']})
    return {'passed':True,'artifact_rows':rows,
        'method':'Read actual configs/results and verify scalar/tuple semantics against independent small-case proofs; did not import production model.',
        'corrections_and_limits':[
            'Root end/hold can be optimal. Aaron-at-root is an independent witness, not a forced or unique optimal action.',
            'PureHP marginal is zero in this specific background; standing-purpose feasibility improves. Do not call Jerry generally worthless.',
            'Joint [0,12] is infeasible for standing. Its physical HP12 is a diagnostic fallback, not a valid standing guarantee and not zero HP.',
            'Main Generated=true facts remove cross-SOUL main-deck illegality and suppress native Worsening Add.',
            'Enemy sourceGenerated must not itself enter public observation unless the input publicly reveals origin.',
            'BoneBox choice privacy remains an explicit unverified information-rule hypothesis.',
        ]}


def main():
    source_files={HERE/'independent_standing.py',HERE/'independent_hidden_menu.py'}
    bounds={str(w):hold_then_jerry(w) for w in (79,86)}
    assert bounds['79']['minimum_player_hp']==9
    assert bounds['86']['minimum_player_hp']==12
    baseline=only_aaron_world()
    prior=json.loads((HERE/'independent-hidden-menu.json').read_text())
    assert prior['root_locked_upper_bound']==9
    data={'method':'Independent exhaustive small-kernel action histories plus explicit common-policy witness.',
        'source_hashes':{p.name:digest(p) for p in sorted(source_files)},
        'policy':'Root end/hold. At second own window play Jerry and end; do not attack.',
        'standing_constraint':{'min_own_living_count':1},
        'world_policy_results':bounds,
        'common_policy_lower_bound':9,
        'upper_bound':9,
        'upper_reason':'Standing-feasible policies are a subset of pureHP policies; independently certified pureHP common maximum is9.',
        'only_aaron_negative_control':baseline,
        'independent_bound_source_sha256':digest(HERE/'independent-hidden-menu.json')}
    data['actual_main_artifact_review']=inspect_main(data)
    (HERE/'independent_standing.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'standing_common_bounds':[9,9],
        'late_jerry_world_hp':{k:v['minimum_player_hp'] for k,v in bounds.items()},
        'only_aaron_worldwise_standing_upper':baseline['upper_value'],
        'actual_main_schema_checks_passed':True}))

if __name__=='__main__':main()
