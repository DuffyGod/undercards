"""Fixed, auditable follow-up proposals; shared prefix is byte-identical.

No credentials in payloads. Outputs remain unapproved research candidates.
"""
from pathlib import Path
import argparse
import json
import hashlib
import importlib.util
import time
from concurrent.futures import ThreadPoolExecutor

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=HERE/'deck-review'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def prepare():
    OUT.mkdir(exist_ok=True)
    if (OUT/'manifest.json').exists():raise RuntimeError('Frozen manifest exists')
    spec=importlib.util.spec_from_file_location('pool_screen',HERE/'pool_screen.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    s=read(ROOT/'skills/undercards/references/snapshot.json');cards={str(c['id']):c for c in s['cards']}
    audit=read(HERE/'pool-screen/screen-audit.json')
    additions=[7,8,10,13,20,22,53,54,56,59,101,111,144,148,166,175,185,201,225,236,243,281,291,310,314,373,391,436,466,468,469,509,530,602,638,641,649,869,932,951,984]
    ids=sorted(set(map(str,audit['nominee_ids']))|set(map(str,additions)),key=int)
    refs=sorted({str(r) for i in ids for r in cards[i].get('card_references',[]) if str(r) in cards}-set(ids),key=int)
    souls={'JUSTICE','INTEGRITY','KINDNESS','PERSEVERANCE'}
    context={'candidate_cards':[module.compact(cards[i]) for i in ids],
        'references':[module.compact(cards[i]) for i in refs],
        'soul_spells':[module.compact(c) for c in s['cards'] if c.get('soul') in souls and c.get('card_type')=='spell' and c.get('pool_category')=='ordinary_non_token'],
        'artifacts':[a for a in s['artifacts'] if a.get('id') in [1,2,4,10,17,31,53,61,12]],
        'verified_rules':'Wanted临死前给对手1G；Mold Spore己方回合末加1、死亡给对手召唤对应攻防Moldsmal；Paralyze下个己方回合不能攻击。Magic不能选刚打出的自身。生成牌不进入Librarian的非Generated重复检查。'}
    prefix=read(HERE/'pool-screen/shared-prefix.json')
    common='''构筑候选不等于批准结果。禁止估计胜率或发明Gold价格。根据实际给定的整池候选比较即时交换、目标依赖、身材、抗惩罚、手牌与四格效率。不要把3G弱牌因为缺早期牌就定核心；特别比较Fire Fountain、Normal NPC、Flowey、Faun、Pixel Vase、Rock Pet等与旧六锚，不能机械拼旧研究牌。不得把同费攻击血量和当统一强度。卡的最高发挥不等于常态。SOUL先固定Justice，神器Health+Power作为受控基线，可建议一个有文本依据的替代。输出JSON，提供完整25张counts字典(ID:数量)、完整copies/name/cost卡表、每个数量的理由、低费空转/高费卡手/过抽/格子拥塞等弱点、可替换方案、未知裁定。自行验总数25和稀有度上限。'''
    tasks=[]
    for task_id,objective in [
        ('draft_bookshelf','主方案：无初始法术、2 Bookshelf、0 Librarian，其余以通用交互质量构成；可以合理重复但不强迫3满编。不要为了流派硬放差牌。给出快攻/普通质量/控制/挂机组合技四种对手下的取舍，用反例挑战自身。'),
        ('draft_librarian','替代方案：2 Librarian是全副唯一重复，1 Bookshelf、其余全单例、无初始法术。需要比较去重迫使接受多少质量损失，而不能认为多样性本身是收益。给出快攻/普通质量/控制/挂机组合技四种对手下的取舍，用反例挑战自身。')]:
        payload={'model':'deepseek/deepseek-flash','messages':prefix+[{'role':'user','content':common+'\n任务：'+objective+'\n全部候选与引用：'+json.dumps(context,ensure_ascii=False)}],
            'stream':False,'max_tokens':9000,'thinking':{'type':'disabled'},'response_format':{'type':'json_object'}}
        path=OUT/(task_id+'.payload.json');dump(path,payload)
        tasks.append({'id':task_id,'payload_sha256':sha(path)})
    # Repair only schema/coverage gaps; no semantic retry until an answer agrees.
    manifest=read(HERE/'pool-screen/manifest.json')
    missing=sorted({str(i) for issue in audit['coverage_issues'] for i in issue[4]},key=int)
    repair_refs=sorted({str(r) for i in missing for r in cards[i].get('card_references',[]) if str(r) in cards}-set(missing),key=int)
    payload={'model':'deepseek/deepseek-flash','messages':prefix+[{'role':'user','content':'先前输出漏行。仅补充这49张真实卡，不能输出其他id。输出screen每个id恰一次(id,gate,role,one_risk)，nominations最多12(id,why,condition_cost)。不估价格。注意Fish Rod、Memorial Statue等需公平检查。'+json.dumps({'cards':[module.compact(cards[i]) for i in missing],'references':[module.compact(cards[i]) for i in repair_refs]},ensure_ascii=False)}],
        'stream':False,'max_tokens':6500,'thinking':{'type':'disabled'},'response_format':{'type':'json_object'}}
    path=OUT/'coverage_repair.payload.json';dump(path,payload);tasks.append({'id':'coverage_repair','payload_sha256':sha(path)})
    dump(OUT/'manifest.json',{'tasks':tasks,'candidate_count':len(ids),'repair_ids':missing,'shared_prefix_sha256':sha(HERE/'pool-screen/shared-prefix.json'),'source_sha256':sha(ROOT/'skills/undercards/references/snapshot.json'),'runner_sha256':sha(Path(__file__))})

def run():
    spec=importlib.util.spec_from_file_location('authorized_helper','E:/NoScan/Codex/test_llm_api.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    client=helper.TencentClient(timeout=180,retries=0)
    def one(t):
        task_id=t['id'];attempt=OUT/(task_id+'.attempt.json')
        if attempt.exists():return {'id':task_id,'status':'skipped_existing_attempt'}
        payload_path=OUT/(task_id+'.payload.json')
        if sha(payload_path)!=t['payload_sha256']:raise RuntimeError('Payload changed')
        dump(attempt,{'status':'started','payload_sha256':sha(payload_path),'time':time.time()});start=time.monotonic()
        try:
            raw=client.complete(read(payload_path));dump(OUT/(task_id+'.raw.json'),raw)
            choice=raw['choices'][0];content=choice['message']['content'];candidate=json.loads(content)
            dump(OUT/(task_id+'.candidate.json'),candidate)
            result={'id':task_id,'status':'returned_unreviewed','finish_reason':choice['finish_reason'],'usage':raw.get('usage'),'elapsed':time.monotonic()-start}
        except Exception as e:
            result={'id':task_id,'status':'failed_no_retry','error':client.redact(str(e)),'elapsed':time.monotonic()-start}
        dump(OUT/(task_id+'.result.json'),result);print(json.dumps(result,ensure_ascii=False),flush=True);return result
    with ThreadPoolExecutor(max_workers=3) as executor:results=list(executor.map(one,read(OUT/'manifest.json')['tasks']))
    dump(OUT/'run-summary.json',results)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--run',action='store_true');a=p.parse_args()
    if a.prepare:prepare()
    if a.run:run()
