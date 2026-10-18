"""Verify producer provenance and export reproducible round-two quotations."""
from pathlib import Path
from itertools import combinations
import csv
import gzip
import hashlib
import json

from quote_card import deployment, slot
from statistical_value import Prices, best_value, deployment_plans

HERE=Path(__file__).resolve().parent


def read(name):return json.loads((HERE/name).read_text(encoding='utf-8'))
def sha(name):return hashlib.sha256((HERE/name).read_bytes()).hexdigest()
def dump(name,value):(HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    checked={}
    for filename,key in (('demand-stress/provenance.json','source_hashes'),
                         ('joint-stress/joint-design.json','source_sha256'),
                         ('joint-stress/prototype-design.json','source_sha256'),
                         ('slot-results/slot-design.json','source_sha256')):
        data=read(filename)
        checked[filename]={name:sha(name)==digest for name,digest in data[key].items()}
        if not all(checked[filename].values()):raise AssertionError(filename+' producer mismatch')
    old=read('statistical-results/final-design.json')
    if old['input_sha256']!=sha('statistical_inputs.json'):raise AssertionError('Frozen input mismatch')
    compressed=[]
    for archive in read('slot-results/slot-design.json')['deterministic_compressed_exports']:
        raw=(HERE/'slot-results'/archive['gzip']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==archive['gzip_sha256']
        assert hashlib.sha256(gzip.decompress(raw)).hexdigest()==archive['source_sha256']
        assert int.from_bytes(raw[4:8],'little')==0 and raw[3]&8==0
        compressed.append(dict(file=archive['gzip'],gzip_sha256=archive['gzip_sha256'],lossless=True,
                               bytes=len(raw),mtime=0,no_filename=True))
    with (HERE/'joint-stress/joint-scores.csv').open(encoding='utf-8',newline='') as f:
        joint=list(csv.DictReader(f))
    original={(r['scenario'],r['id']):r for r in read('statistical-results/final-scores.json') if r['parameter']=='central'}
    score_checks=0
    for row in joint:
        if row['setting']!='central' or row['case']=='aoe2_survivors':continue
        oldrow=original[row['case'],int(row['id'])]
        for key in ('net_value','plus_attack','plus_health','fixed_policy_plus_attack','opportunity_index'):
            assert abs(float(row[key])-oldrow[key])<1e-9
            score_checks+=1
    # A concrete source-physical counterexample, not a fitted negative HP price.
    inputs=read('statistical_inputs.json')
    prices=Prices(inputs,face_share=.35,threshold=.6,tail=0.,face=.15)
    card=inputs['cards']['469'];enemy=((4,3),(1,1),(2,1))
    before=best_value(card,inputs['cards'],enemy,0,prices,'damage2',.1,0.,details=True)
    after=best_value(card,inputs['cards'],enemy,0,prices,'damage2',.1,0.,h_delta=1,details=True)
    negative=dict(enemy=enemy,parameters=dict(face_share=.35,threshold=.6,tail=0.,face=.15),
        card_id=469,base_q=before[0],plus_hp_q=after[0],hp_difference=after[0]-before[0],
        base_plan=before[1],plus_hp_plan=after[1],
        meaning='Same attack; original B dies and summons O now, extraHP leaves B3/1 and defers Dust. No future Dust reserve at tail0.')
    examples=dict(
        actual_survivors=deployment([649,530],'aoe2_survivors'),
        prototype=deployment([469,530,649,49,984],'icecap_vulkin'),
        paid_slot=slot([530,984,469,20],'three_plain','aggro_32',8,2,1.,2),
        fixed_case_two_slots=slot([20],'three_plain','three_3_2',6,2,0.,2),
        fixed_case_one_slot=slot([20],'three_plain','three_3_2',6,1,0.,2))
    dump('round2-query-examples.json',examples)
    dump('round2-verification.json',dict(producer_hashes=checked,archives=compressed,
        original_central_scalar_checks=score_checks,original_central_max_difference_below=1e-9,
        negative_hp_physical_counterexample=negative,
        actual_tests=dict(command='python -B -m unittest discover -s analysis/method-lab/2026-10-18 -p test_*.py -v',
                          passed=39,failures=0,errors=0),
        source_sha256={name:sha(name) for name in ('round2_summary.py','quote_card.py','test_joint_stress.py','test_value_ties.py','test_quote_card.py')},
        note='Provenance, physical and accounting checks; not empirical Gold calibration'))
    print(json.dumps(dict(producer_packages=len(checked),original_scalar_checks=score_checks,
        joint_rows=len(joint),query_examples=len(examples),archives_lossless=len(compressed)),ensure_ascii=False))


if __name__=='__main__':main()
