"""Tiny exact information-set cases; no production model or engine imports."""
from itertools import product
from pathlib import Path
import hashlib
import json


def visible_response_case():
    # Enemy turn, old Moldsmal already attacked before the declared start.
    # New monsters are not Charge/Haste and cannot attack this enemy turn.
    branches = {
        'Snowdrake:buff_old': {'old':5,'new':4},
        'Snowdrake:buff_self': {'old':3,'new':6},
        'Aaron:play': {'old':3,'new':6},
        # Holding leaves the same public state for both hidden menus.
        # If we kill old now, a newly deployed monster next turn cannot attack.
        'Snowdrake:hold': {'old':3},
        'Aaron:hold': {'old':3},
    }
    def leaf(branch, action):
        attack = branches[branch]
        if action.startswith('kill_'):
            target=action[5:]
            if target not in attack:
                return None
            remaining = sum(v for k,v in attack.items() if k != target)
            return max(0,15-remaining)
        if action == 'self_damage':
            if branch == 'Snowdrake:hold':
                return 2
            return max(0,15-8-sum(attack.values()))
        # If first enemy held, it can play Snowdrake next turn and buff old
        # before old attacks. Fresh Snowdrake/Aaron cannot attack that turn.
        if branch == 'Snowdrake:hold':
            return 10
        return max(0,15-sum(attack.values()))
    rows = {}
    optimal = {}
    for branch in branches:
        rows[branch]={a:leaf(branch,a) for a in ('kill_old','kill_new','self_damage','hold')}
        good={a:v for a,v in rows[branch].items() if v is not None}
        optimal[branch]={'value':max(good.values()),
            'actions':[a for a,v in good.items() if v==max(good.values())]}
    # Every non-hold branch is a different public history. Hold branches share
    # one info set; both choose kill_old so that equality constraint is met.
    adaptive=min(x['value'] for x in optimal.values())
    displayed_matrix={
        'kill_old':{'Snowdrake:buff_old':rows['Snowdrake:buff_old']['kill_old'],
                    'Aaron:play':rows['Aaron:play']['kill_old']},
        'kill_new':{'Snowdrake:buff_old':rows['Snowdrake:buff_old']['kill_new'],
                    'Aaron:play':rows['Aaron:play']['kill_new']},
    }
    frozen=max(min(r.values()) for r in displayed_matrix.values())
    assert displayed_matrix == {'kill_old':{'Snowdrake:buff_old':11,'Aaron:play':9},
                                'kill_new':{'Snowdrake:buff_old':10,'Aaron:play':12}}
    assert adaptive==11 and frozen==10
    return {'branches':branches,'all_own_action_values':rows,
        'observed_history_optimal_actions':optimal,
        'correct_observation_adaptive_guarantee':adaptive,
        'incorrect_identical_future_target_guarantee':frozen,
        'displayed_matrix':displayed_matrix,
        'note':'Held-menu public histories are equal and both use kill_old. Different played cards/buffs are public and permit different target actions.'}


def same_observation_case():
    # Both worlds can attack face with the same observed 3/6 then hold their
    # hidden spell. The full prelude observation is identical, not merely board.
    public={
        'phase':'own_turn_after_enemy_end', 'own_hp':15,
        'enemy_hp':30, 'own_gold':5,'enemy_gold':2,
        'own_hand':[14,15], 'enemy_hand_count':1, 'enemy_soul':'PERSEVERANCE',
        'earlier_common_history':'Bone Box402 generated one hidden spell costing <=3 GOLD; source no longer on board',
        'own_board':[],
        'enemy_board':[{'key':'old','card_id':246,'attack':3,'health':6,
                        'current_cost':4,'base_cost':4,'printed_cost':4}],
        'public_history':[
            {'actor':'enemy','action':'attack_face','source':'old','damage':3,'own_hp_before':18,'own_hp_after':15},
            {'actor':'enemy','action':'end_turn'},
        ],
    }
    worlds=[{'private_enemy_hand':[{'card_id':79,'generated':True}],'public':public},
            {'private_enemy_hand':[{'card_id':86,'generated':True}],'public':public}]
    enc=[json.dumps(w['public'],sort_keys=True,separators=(',',':')) for w in worlds]
    assert enc[0]==enc[1]
    return {'worlds':worlds,
        'public_observations_sha256':[hashlib.sha256(x.encode()).hexdigest() for x in enc],
        'required_shared_root_action':True,
        'forbidden_policy':{'private_[79]':'play_Aaron','private_[86]':'play_Jerry'},
        'forbidden_policy_world_values':[12,15],
        'forbidden_policy_min':12,
        'valid_common_policy':'play_Aaron; next own turn attack live enemy',
        'valid_common_policy_world_values':[12,9],
        'valid_common_policy_min':9,
        'independent_bound_reference':'independent-hidden-menu.json',
        'note':'An enemy declining to reveal a card does not split own information sets without an independently justified public inference rule.'}


def main():
    here=Path(__file__).resolve().parent
    data={'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'visible_response':visible_response_case(),
          'same_public_action_hidden_menu':same_observation_case()}
    (here/'independent-information-sets.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'visible_adaptive':data['visible_response']['correct_observation_adaptive_guarantee'],
        'overrestricted_same_future_target':data['visible_response']['incorrect_identical_future_target_guarantee'],
        'same_public_observation_hashes_equal':len(set(data['same_public_action_hidden_menu']['public_observations_sha256']))==1}))

if __name__=='__main__':main()
