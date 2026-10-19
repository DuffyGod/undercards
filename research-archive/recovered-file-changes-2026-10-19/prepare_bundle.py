"""Archive recorded file changes, never import recovered game/research code.

The 2.7MB response is parsed locally; conversations and local trajectory folders
are not inputs to the archive. The original restoration algorithm is used only
as a text transformation and its outputs are compared with saved snapshots.
"""
from pathlib import Path, PurePosixPath
import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import io
import json
import re
import sys
import tarfile

HERE=Path(__file__).resolve().parent
SELECTED=('board_tactics.py','paid_board_tactics.py','combat_event_extensions.py',
          'test_board_tactics.py','test_paid_board_tactics.py','test_combat_event_extensions.py')

def sha(data):return hashlib.sha256(data).hexdigest()
def serialized(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8')
def dump(path,value):path.write_bytes(serialized(value))
def safe(name):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name:raise ValueError('Unsafe member path')
    return path.as_posix()

def build(source,restored,restorer):
    response_bytes=source.read_bytes();data=json.loads(response_bytes.decode('utf-8-sig'))
    # Preserve turn/item coordinates, replacing every non-file-change item.
    projected={k:data[k] for k in ('title','version') if k in data}
    projected['turns']=[];changes=[]
    for turn in data['turns']:
        items=[]
        for item in turn.get('items',[]):
            if 'changes' in item:
                items.append({k:item[k] for k in ('type','status','changes') if k in item})
                changes.extend(item['changes'])
            else:items.append({'type':'omitted_non_file_item'})
        projected['turns'].append({'items':items})
    if len(changes)!=930:raise ValueError('Unexpected response version; freeze a new batch')
    for change in changes:
        name=change['path']
        if not name.endswith(('.py','.md','.json','.js','.html','.css')):raise ValueError('Unreviewed source extension')
        if re.search(r'(?i)(^|[/\\])(?:\.env(?:\.|$)|tencent-api-key|credentials|id_rsa|.*\.pem$)',name):raise ValueError('Credential filename')
        if re.search(r'Bearer\s+[A-Za-z0-9_-]{24,}',change['diff']):raise ValueError('Unreviewed credential-like literal')
    helper_name='recorded_file_text_restorer'
    spec=importlib.util.spec_from_file_location(helper_name,restorer)
    helper=importlib.util.module_from_spec(spec);sys.modules[helper_name]=helper;spec.loader.exec_module(helper)
    tracks,events,summary=helper.recover(projected)
    original=json.loads((restored/'manifest.json').read_text(encoding='utf8'))
    if summary!=original['summary']:raise AssertionError('Restoration summary differs')
    if [{k:v for k,v in event.items() if k!='raw_diff'} for event in events]!=original['events']:
        raise AssertionError('Recorded event coordinates/status differ')
    expected={};members={};snapshot_rows=[]
    for track in tracks:
        initial='initial/'+track.filename;latest='latest/'+track.filename
        expected[initial]=track.initial.text.encode('utf8')
        expected[latest]=track.current_text().encode('utf8')
    for event in events:
        if 'patch_file' in event:expected[event['patch_file']]=event['raw_diff'].encode('utf8')
    # This checks the full byte content, not just historical hash statements.
    for name,raw in expected.items():
        if (restored/name).read_bytes()!=raw:raise AssertionError('Saved reconstruction differs: '+name)
        members['restored-added-files/'+safe(name)]=raw
    if len(expected)!=593:raise AssertionError('Expected234 initial+234 replayed+125 pending files')
    for name in ['manifest.json','README.md']:
        members['restored-added-files/'+name]=(restored/name).read_bytes()
    members['file-change-records.json']=serialized(projected)
    members['restore_added_files.py']=restorer.read_bytes()
    for row in original['files']:
        latest=expected[row['latest_file']]
        snapshot_rows.append({**row,'initial_sha256':sha(expected[row['initial_file']]),'latest_sha256':sha(latest),
            'latest_bytes':len(latest),'status':'partial_replay' if row['unresolved_patch_candidates'] else 'no_flagged_pending_patch_not_final_version_proof'})
    selected=[];view=HERE/'selected';view.mkdir(exist_ok=True)
    for basename in SELECTED:
        rows=[r for r in snapshot_rows if r['source_path']==basename]
        if len(rows)!=1:raise ValueError('Selected snapshot ambiguous')
        row=rows[0];raw=expected[row['latest_file']]
        try:
            tree=ast.parse(raw.decode('utf8'));syntax='parseable';version=None
            for statement in tree.body:
                if isinstance(statement,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in statement.targets) and isinstance(statement.value,ast.Constant):version=statement.value.value
        except SyntaxError as error:syntax='syntax_error:'+str(error);version=None
        target=view/(basename+'.txt');target.write_bytes(raw)
        selected.append({**row,'view_path':'selected/'+target.name,'syntax_only':syntax,'version_literal':version,
            'applied_patch_count':len(row['applied_patch_entries']),'pending_patch_count':len(row['unresolved_patch_candidates'])})
    report=next(r for r in snapshot_rows if r['latest_file']=='latest/README__e000902.md')
    (HERE/'historical-combat-report.md').write_bytes(expected[report['latest_file']])
    file_index=[{'path':name,'bytes':len(raw),'sha256':sha(raw)} for name,raw in sorted(members.items())]
    members['file-index.json']=serialized({'scope':'Recorded source snapshots and change text, no trajectories or API credentials.',
        'files':file_index,'snapshots':snapshot_rows})
    archive_path=HERE/'restored-source.tar.xz'
    with tarfile.open(archive_path,'w:xz',preset=9) as archive:
        for name,raw in sorted(members.items()):
            info=tarfile.TarInfo(safe(name));info.size=len(raw);info.mode=0o644;info.mtime=0
            info.uid=info.gid=0;info.uname=info.gname=''
            archive.addfile(info,io.BytesIO(raw))
    member_index=[{'path':name,'bytes':len(raw),'sha256':sha(raw)} for name,raw in sorted(members.items())]
    manifest={'format':'recorded-file-changes-recovery-v1','date':'2026-10-19','source_response':{'bytes':len(response_bytes),'sha256':sha(response_bytes)},
        'projected_records':{'path':'file-change-records.json','bytes':len(members['file-change-records.json']),'sha256':sha(members['file-change-records.json']),
            'all_file_changes_retained':True,'non_file_items_omitted':True,'original_turn_item_change_coordinates_preserved':True},
        'summary':summary,'archive':{'path':archive_path.name,'bytes':archive_path.stat().st_size,'sha256':sha(archive_path.read_bytes()),'members':len(members)},
        'byte_replay_verification':{'matched_snapshot_and_pending_files':len(expected),'game_code_imported':False,'experiments_rerun':False},
        'selected':selected,'historical_report':{'path':'historical-combat-report.md','source':report['latest_file'],'sha256':report['latest_sha256']},
        'members':member_index,'boundaries':['Basenames are recorded, original directories are absent.',
            'Replay does not establish the final paid0.32/API0.34/board0.6.1 source version.',
            'No original generated inventory/regression/comparison/trajectory results are invented.',
            'No local dynamic simulator directory or its large trajectories was read into this archive.'],
        'producer_sha256':sha(Path(__file__).read_bytes())}
    dump(HERE/'manifest.json',manifest)
    print(json.dumps({'archive_bytes':manifest['archive']['bytes'],'archive_members':len(members),'verified_files':len(expected),
        'changes':len(changes),'selected':[{k:r[k] for k in ['source_path','version_literal','pending_patch_count']} for r in selected]},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('E:/NoScan/Codex/tmp/response.json'))
    parser.add_argument('--restored',type=Path,default=Path('E:/NoScan/Codex/tmp/restored-added-files'))
    parser.add_argument('--restorer',type=Path,default=Path('E:/NoScan/Codex/tmp/restore_added_files.py'))
    args=parser.parse_args();build(args.source,args.restored,args.restorer)
