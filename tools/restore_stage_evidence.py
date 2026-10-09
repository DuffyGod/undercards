"""Restore hash-verified phase evidence, with strict workspace path containment."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def restore(root=ROOT):
    root=Path(root).resolve()
    folder=root/'research-archive'
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    raw=(folder/'stage-evidence.zip').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=manifest['archive_sha256']:
        raise ValueError('Phase evidence archive hash mismatch')
    expected={entry['path']:entry for entry in manifest['entries']}
    if len(expected)!=len(manifest['entries']): raise ValueError('Duplicate evidence path')
    restored=unchanged=0
    with zipfile.ZipFile(folder/'stage-evidence.zip') as archive:
        if set(archive.namelist())!=set(expected) or len(archive.namelist())!=len(expected):
            raise ValueError('Archive entries do not match manifest')
        # Validate every byte/path before making any writes.
        for name,entry in expected.items():
            destination=(root/name).resolve()
            if not destination.is_relative_to(root) or Path(name).is_absolute():
                raise ValueError('Evidence path escapes checkout')
            if any(part in ('.git','.env','tencent-api-key') for part in Path(name).parts):
                raise ValueError('Forbidden evidence destination')
            data=archive.read(name)
            if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
                raise ValueError('Evidence entry hash mismatch: '+name)
            if destination.exists() and destination.read_bytes()!=data:
                raise ValueError('Existing local evidence differs; preserve it: '+name)
        for name in expected:
            destination=root/name
            if destination.exists(): unchanged+=1; continue
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(archive.read(name))
            restored+=1
    return {'restored':restored,'already_identical':unchanged,'entries':len(expected)}


if __name__=='__main__': print(json.dumps(restore()))
