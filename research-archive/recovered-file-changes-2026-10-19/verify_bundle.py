"""Verify/retrieve source text without importing any recovered research code."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import tarfile

HERE=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def verified(archive_path,manifest):
    if sha(archive_path.read_bytes())!=manifest['archive']['sha256']:raise ValueError('Archive hash mismatch')
    expected={r['path']:r for r in manifest['members']}
    if len(expected)!=len(manifest['members']):raise ValueError('Duplicate expected members')
    payload={}
    with tarfile.open(archive_path,'r:xz') as archive:
        members=archive.getmembers()
        if len(members)!=len(expected) or {x.name for x in members}!=set(expected):raise ValueError('Archive contents mismatch')
        for member in members:
            path=PurePosixPath(member.name)
            if not member.isfile() or path.is_absolute() or '..' in path.parts or '\\' in member.name or ':' in member.name:raise ValueError('Unsafe archive entry')
            if member.size!=expected[member.name]['bytes']:raise ValueError('Size mismatch')
            raw=archive.extractfile(member).read()
            if sha(raw)!=expected[member.name]['sha256']:raise ValueError('Member hash mismatch')
            payload[member.name]=raw
    return payload

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--extract-to',type=Path)
    args=p.parse_args();manifest=json.loads((HERE/'manifest.json').read_text(encoding='utf8'))
    payload=verified(HERE/manifest['archive']['path'],manifest)
    if args.extract_to:
        destination=args.extract_to.resolve()
        if destination.exists():raise ValueError('Choose a NEW destination; existing directories are never overwritten')
        targets={name:destination.joinpath(*PurePosixPath(name).parts).resolve() for name in payload}
        if any(not t.is_relative_to(destination) for t in targets.values()):raise ValueError('Destination escape')
        destination.mkdir(parents=True,exist_ok=False)
        for name,target in targets.items():target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload[name])
    print(json.dumps({'verified_members':len(payload),'extracted':str(args.extract_to) if args.extract_to else None,
        'research_code_executed':False,'experiments_rerun':False}))
if __name__=='__main__':main()
