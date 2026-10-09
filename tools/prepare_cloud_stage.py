"""Freeze current-stage files for a GitHub import; excludes credentials/caches.

Active source/Skill is uploaded directly. Heavy current evidence and older
Markdown findings are losslessly archived. Superseded massive simulation
trajectories are not included in this phase import.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/'cloud-stage'
BLOCKED={'__pycache__','.git','cloud-stage','.codex','.agents','tencent-api-key'}


def sha(raw): return hashlib.sha256(raw).hexdigest()


def blocked(path):
    return (any(part in BLOCKED for part in path.parts) or path.name.startswith('.env')
            or path.suffix in ('.pem','.key','.tmp') or path.name=='run.lock')


def prepare():
    root_files=['README.md','CLOUD_SETUP.md','CONTINUATION.md','stage-verification.json']
    live=[ROOT/name for name in root_files]
    live += list((ROOT/'tools').glob('*.py'))
    live += [p for p in (ROOT/'skills').rglob('*') if p.is_file() and not blocked(p.relative_to(ROOT))]
    heuristic=ROOT/'analysis/monster-value-heuristic'
    live += [p for p in heuristic.glob('*') if p.is_file() and p.suffix in ('.py','.md')]
    for p in live:
        if not p.is_file(): raise ValueError('Missing phase file: '+str(p))
    live=sorted(set(live))
    archived={p for p in heuristic.rglob('*') if p.is_file() and not blocked(p.relative_to(ROOT))}-set(live)
    # Keep older research conclusions and the original structured inputs.
    archived.update(p for p in (ROOT/'analysis').rglob('*.md') if not blocked(p.relative_to(ROOT)))
    archived -= set(live)
    archived.update(ROOT/name for name in ('data.json','collection.json','deck_sample.json','survey.md') if (ROOT/name).is_file())
    archived.add(ROOT/'analysis/mechanics.json')
    checkout=STAGE/'checkout'
    checkout.mkdir(parents=True,exist_ok=True)
    archive_path=checkout/'research-archive/stage-evidence.zip'
    archive_path.parent.mkdir(parents=True,exist_ok=True)
    entries=[]
    with zipfile.ZipFile(archive_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for p in sorted(archived):
            relative=p.relative_to(ROOT).as_posix()
            raw=p.read_bytes()
            archive.writestr(relative,raw)
            entries.append({'path':relative,'bytes':len(raw),'sha256':sha(raw)})
    evidence={'entries':entries,'archive_sha256':sha(archive_path.read_bytes()),
              'archive_bytes':archive_path.stat().st_size,
              'scope':'Current heuristic evidence, API records, and older Markdown conclusions; excludes superseded massive simulation traces and credentials.'}
    (archive_path.parent/'manifest.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for p in live:
        destination=checkout/p.relative_to(ROOT)
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(p,destination)
    ignored=['__pycache__/','*.py[cod]','.env','.env.*','tencent-api-key','*.pem','*.key','cloud-stage/']
    ignored += ['/'+item['path'] for item in entries]
    (checkout/'.gitignore').write_text('\n'.join(ignored)+'\n',encoding='utf-8')
    # A restore/verification inside checkout may have materialized ignored
    # evidence. Only declared live files and the archive are upload entries.
    files=[checkout/p.relative_to(ROOT) for p in live]
    files += [archive_path,archive_path.parent/'manifest.json',checkout/'.gitignore']
    manifest={'files':[{'path':p.relative_to(checkout).as_posix(),'bytes':p.stat().st_size,
                        'sha256':sha(p.read_bytes()),'git_blob_sha':hashlib.sha1(b'blob '+str(p.stat().st_size).encode()+b'\0'+p.read_bytes()).hexdigest()}
                       for p in sorted(files)],'archive_entries':len(entries),'archive_bytes':evidence['archive_bytes']}
    (STAGE/'upload-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'upload_files':len(files),'archive_entries':len(entries),
                      'upload_bytes':sum(p.stat().st_size for p in files),'archive_bytes':evidence['archive_bytes']}))
    return manifest


if __name__=='__main__': prepare()
