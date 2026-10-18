"""Small-scope auxiliary adversarial reviews of complete, root-owned drafts."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import time
from concurrent.futures import ThreadPoolExecutor
HERE=Path(__file__).resolve().parent
OUT=HERE/'bounded-review'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def prepare():
    OUT.mkdir(exist_ok=True)
    if (OUT/'manifest.json').exists():raise RuntimeError('Manifest is immutable')
    source=read(HERE/'selected-source.json')
    cards={str(c['id']):c for c in source['cards']+source['referenced_cards']}
    prefix=read(HERE/'pool-screen/shared-prefix.json');tasks=[]
    for task_id,deck_file,question in [
        ('A_audit','A_quality_bookshelf.json','检查A的早期稳定性、即时交换与后债，至少挑战三点；不要重新编25张表。重点The Flame真实负效、Virgil Wanted给敌1G、Normal NPC攻击频率、Archer低手牌。提出至多2组精确替换，每组一进一出且不增加费用拥塞。'),
        ('B_audit','B_library_singletons.json','检查B的Librarian当下牌库Need、抽3手限、后续随机卡抽取质量，比较单例代用品是否太差；特别Napstablook/Rock Pet/Piranhas和A重复卡。提出至多2组精确替换，不能造成非Lib重复。'),
        ('artifact_audit','A_quality_bookshelf.json','仅审查Justice+Health/Power与提供的其他SOUL/神器取舍。没有给其他SOUL法术则不能猜。Health+7HP和Power给后续怪+1/1的已知价值如何适应快攻、普通质量、控制、挂机combo？不要给胜率、不要把Power counter预先加进所有身体。')]:
        deck=read(HERE/deck_file);ids=set(deck['counts'])
        refs={str(r) for i in ids for r in cards[i].get('card_references',[]) if str(r) in cards}
        context={'deck':deck,'cards':[cards[i] for i in sorted(ids|refs,key=int)],'artifacts':source['artifacts'],
            'statuses':source['mechanics']['status'],'enchants':source['mechanics']['enchant'],
            'souls':source['mechanics']['soul']}
        prompt='''你是独立反例审查者，不批准牌表。以给定原文为准；这是已完成25张的具体草稿，不是让你重新输出全池或完整牌表。输出一个严格JSON对象，字段仅issues(最多6项，每项card_id,claim,source_quote,consequence,severity)、swaps(最多2项，每项out_id,in_id,why,tradeoff)、verdict(最多150字)。严禁在JSON外输出文字。可以没有问题；不能为了凑问题发明效果。不能估胜率或Gold价值。'''+question+'\n资料：'+json.dumps(context,ensure_ascii=False)
        payload={'model':'deepseek/deepseek-flash','messages':prefix+[{'role':'user','content':prompt}],
            'stream':False,'max_tokens':2500,'thinking':{'type':'disabled'},'response_format':{'type':'json_object'}}
        path=OUT/(task_id+'.payload.json');dump(path,payload)
        tasks.append({'id':task_id,'payload_sha256':sha(path),'deck_sha256':sha(HERE/deck_file)})
    dump(OUT/'manifest.json',{'tasks':tasks,'runner_sha256':sha(Path(__file__)),'prefix_sha256':sha(HERE/'pool-screen/shared-prefix.json')})

def run():
    spec=importlib.util.spec_from_file_location('authorized_helper','E:/NoScan/Codex/test_llm_api.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    client=helper.TencentClient(timeout=120,retries=0)
    def one(task):
        tid=task['id'];path=OUT/(tid+'.payload.json');attempt=OUT/(tid+'.attempt.json')
        if attempt.exists():return {'id':tid,'status':'skipped_existing_attempt'}
        if sha(path)!=task['payload_sha256']:raise RuntimeError('Payload changed')
        dump(attempt,{'payload_sha256':sha(path),'time':time.time()});start=time.monotonic();raw=None
        try:
            raw=client.complete(read(path));dump(OUT/(tid+'.raw.json'),raw)
            candidate=json.loads(raw['choices'][0]['message']['content']);dump(OUT/(tid+'.candidate.json'),candidate)
            result={'id':tid,'status':'returned_unreviewed'}
        except Exception as e:result={'id':tid,'status':'failed_no_retry','error':client.redact(str(e))}
        if raw:result.update(usage=raw.get('usage'),finish_reason=raw['choices'][0]['finish_reason'])
        result['elapsed_seconds']=time.monotonic()-start;dump(OUT/(tid+'.result.json'),result)
        print(json.dumps(result,ensure_ascii=False),flush=True);return result
    with ThreadPoolExecutor(max_workers=3) as ex:results=list(ex.map(one,read(OUT/'manifest.json')['tasks']))
    dump(OUT/'run-summary.json',results)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--run',action='store_true');a=p.parse_args()
    if a.prepare:prepare()
    if a.run:run()
