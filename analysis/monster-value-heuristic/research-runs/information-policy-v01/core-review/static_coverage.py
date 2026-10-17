"""Inventory only: successful compilation is not a whole-match reliability claim."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from finite_game.rules import compile_card, UnknownMechanic

SNAPSHOT=ROOT.parents[1]/'skills/undercards/references/snapshot.json'
cards=json.loads(SNAPSHOT.read_text())['cards']
pool=[c for c in cards if c['card_type']=='monster' and c['pool_category']=='ordinary_non_token' and 1<=c['cost']<=10]
supported=[];unknown=[]
for c in cards:
    try:
        compile_card(c)
        supported.append(c)
    except UnknownMechanic as e:
        unknown.append({'id':c['id'],'name':c['name'],'reason':str(e)})
sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
         for p in (ROOT/'finite_game').glob('*.py')}
supported_pool=[c for c in supported if c in pool]
out={'schema':'finite_core_static_coverage0.1.0',
     'snapshot_sha256':hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest(),
     'sources_sha256':sources,'all_snapshot_entries':len(cards),
     'card_typed_entries':sum(c['card_type'] in ('monster','spell') for c in cards),
     'supported_entries':len(supported),'unknown_entries':len(unknown),
     'standard_monster_denominator':len(pool),'standard_monster_compiled':len(supported_pool),
     'supported_by_card_type':dict(Counter(c['card_type'] for c in supported)),
     'standard_monsters':[{'id':c['id'],'name':c['name'],'cost':c['cost'],'effect':c['effect_readable']} for c in supported_pool],
     'unknown':unknown,
     'interpretation':'Strict text coverage only; semantic guards can still reject transitions. New implementation, not recovered historical paid engine.'}
(HERE/'static-coverage.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:out[k] for k in ('all_snapshot_entries','supported_entries','unknown_entries','standard_monster_denominator','standard_monster_compiled')},ensure_ascii=False))
