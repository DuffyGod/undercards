"""Purposive families: same-fee Charge/healing, Taunt, vanilla and Dodge."""
import gzip
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import information_pressure as pressure
from run_comparisons import configuration,scene,BY,TASKS
P=Path(__file__).parent;OUT=P/'pressure';OUT.mkdir(exist_ok=True)
binding=pressure.sources();rows=[];start=time.time();calls=0
for cid in [6,9,22,14,15,168]:
    for context in ['single','wide']:
        for purpose,task in TASKS.items():
            config=configuration(scene([cid,15],BY[cid]['cost'],context,2),task)
            result=pressure.evaluate(config,floors=[1,9,12,15]);calls+=result['actual_information_evaluations']
            file=f'card{cid}-{context}-{purpose}.json.gz'
            with gzip.open(OUT/file,'wt') as f:json.dump(dict(config=config,result=result),f)
            rows.append(dict(card_id=cid,name=BY[cid]['name'],cost=BY[cid]['cost'],context=context,
                purpose=purpose,frontier=result['frontier'],complete_sampled_floors=result['complete_sampled_floors'],
                artifact=file,actual_information_evaluations=result['actual_information_evaluations']))
            print(cid,context,purpose,result['frontier'],result['complete_sampled_floors'],flush=True)
assert binding==pressure.sources()
(OUT/'index.json').write_text(json.dumps(dict(source_hashes=binding,rows=rows,actual_information_evaluations=calls,
    seconds=time.time()-start,scope='Same declared hidden world envelope and cash as main; each HP/E-cap point uses one common information policy. Samples do not certify a continuous frontier.'),ensure_ascii=False,indent=2)+'\n')
