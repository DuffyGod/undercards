"""Lossless local transcript bundle, excluding any credential/helper files."""
from pathlib import Path
import gzip
import hashlib
import json
HERE=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def produce():
    documents=[]
    for subdir in ['pool-screen','deck-review','bounded-review']:
        for path in sorted((HERE/subdir).glob('*.json')):
            raw=path.read_bytes()
            documents.append({'path':path.relative_to(HERE).as_posix(),'bytes':len(raw),
                'sha256':sha(raw),'utf8_text':raw.decode('utf8')})
    prefix=json.loads((HERE/'pool-screen/shared-prefix.json').read_text(encoding='utf8'))
    payloads=[json.loads(d['utf8_text']) for d in documents if d['path'].endswith('.payload.json')]
    assert len(payloads)==20 and all(p['messages'][:len(prefix)]==prefix for p in payloads)
    raw_responses=[json.loads(d['utf8_text']) for d in documents if d['path'].endswith('.raw.json')]
    usage={'calls':len(raw_responses),'prompt_tokens':sum(r.get('usage',{}).get('prompt_tokens',0) for r in raw_responses),
        'completion_tokens':sum(r.get('usage',{}).get('completion_tokens',0) for r in raw_responses),
        'cached_prompt_tokens':sum(r.get('usage',{}).get('prompt_tokens_details',{}).get('cached_tokens',0) for r in raw_responses)}
    payload=json.dumps({'format':'lossless-utf8-document-bundle-v1','usage':usage,'documents':documents},ensure_ascii=False,separators=(',',':')).encode('utf8')
    compressed=gzip.compress(payload,mtime=0);(HERE/'api-evidence.json.gz').write_bytes(compressed)
    index={'bundle_sha256':sha(compressed),'uncompressed_sha256':sha(payload),'usage':usage,
        'shared_prefix_count':len(prefix),'all_20_prefixes_identical':True,
        'documents':[{k:v for k,v in d.items() if k!='utf8_text'} for d in documents]}
    (HERE/'api-evidence-index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'usage':usage,'documents':len(documents),'compressed_bytes':len(compressed)}))
if __name__=='__main__':produce()
