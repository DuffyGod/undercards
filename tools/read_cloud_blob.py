"""Read only a manifest-listed frozen upload file, emitting bounded base64."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--path',required=True)
parser.add_argument('--start',type=int,default=0)
parser.add_argument('--length',type=int,default=30000)
args=parser.parse_args()
manifest=json.loads((ROOT/'cloud-stage/upload-manifest.json').read_text(encoding='utf-8'))
entry=next((item for item in manifest['files'] if item['path']==args.path),None)
if entry is None or args.start<0 or not 1<=args.length<=30000: raise ValueError('Invalid bounded file read')
root=(ROOT/'cloud-stage/checkout').resolve()
path=(root/entry['path']).resolve()
if not path.is_relative_to(root): raise ValueError('File escapes frozen checkout')
raw=path.read_bytes()
if hashlib.sha256(raw).hexdigest()!=entry['sha256']: raise ValueError('Frozen upload source changed')
print(json.dumps({'path':args.path,'start':args.start,'total':len(raw),
                  'base64':base64.b64encode(raw[args.start:args.start+args.length]).decode('ascii')}))
