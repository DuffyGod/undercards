"""Exercise the installed CLI outside the checkout and audit a complete ZIP."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,tempfile,zipfile
from .training import dump


def command(args,cwd,env,expected=0):
    r=subprocess.run(args,cwd=cwd,env=env,text=True,capture_output=True)
    if r.returncode!=expected:raise RuntimeError(f'Unexpected exit{r.returncode}: {args!r}\n{r.stdout}\n{r.stderr}')
    return r


def wheel_verify(wheel,output,expected_policy):
    wheel=Path(wheel).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Preserve verification output')
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='undercards-v040-') as temporary:
        root=Path(temporary);target=root/'installed';cwd=root/'outside';cwd.mkdir()
        r=command([sys.executable,'-m','pip','install','--no-deps','--no-index','--no-cache-dir','--target',str(target),str(wheel)],cwd,os.environ.copy())
        (output/'install.log').write_text(r.stdout+r.stderr)
        env=os.environ.copy();env['PYTHONPATH']=str(target)
        origin=command([sys.executable,'-c','import card_eval;print(card_eval.__file__)'],cwd,env).stdout.strip()
        if not Path(origin).is_relative_to(target):raise ValueError('Imported checkout instead of installed wheel')
        cli=[sys.executable,'-m','card_eval']
        catalog=json.loads(command(cli+['models'],cwd,env).stdout);names={m['name'] for m in catalog['models']}
        if names!={'legacy-v3','paired-v5','memory-v6','afterstate-v7','entity-v9'}:raise ValueError('Incomplete named-model release')
        request_file=output/'request.json'
        command(cli+['example','--learned','--output',str(request_file)],cwd,env)
        request=json.loads(request_file.read_text());request.update(candidates=['Bench'],samples=2,seed_start=2491000,
            opponents=request['opponents'][:1],policies=['learned'],planner=dict(mode='value',margin=.2,nodes=48,depth=3,width=4,seconds=.12))
        dump(request_file,request)
        command(cli+['evaluate','--input',str(request_file),'--model','entity-v9','--output',str(output/'blocked')],cwd,env,expected=2)
        blocked=json.loads((output/'blocked/result.json').read_text())
        if blocked['status']!='unqualified_policy' or blocked['scores'] is not None:raise ValueError('Qualification gate failed')
        r=command(cli+['evaluate','--input',str(request_file),'--model','entity-v9','--experimental-model','--output',str(output/'evaluated')],cwd,env)
        (output/'evaluation.log').write_text(r.stdout+r.stderr)
        result=json.loads((output/'evaluated/result.json').read_text())
        if result['status']!='complete' or result['games']!=8 or result['frozen_policy']!=expected_policy:raise ValueError('Installed policy/configuration mismatch')
        if result['comparisons'][0]['recommendation']!='experimental_only':raise ValueError('Unqualified planner recommended a direction')
        unknown=json.loads(command(cli+['inspect','Glyde'],cwd,env,expected=2).stdout)
        if unknown['status']!='unsupported' or unknown['score'] is not None:raise ValueError('Unknown mechanism scored as zero')
        dump(output/'unknown-card.json',unknown)
        receipt=dict(status='passed',scope='Installed application contract, not strategy qualification',
            wheel=str(wheel),wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),module_origin=origin,
            model_names=sorted(names),frozen_policy=result['frozen_policy'],base_model=result['base_model'],
            planner=result['planner'],comparison_slots=result['games'],unresolved_slots=result['unresolved'],
            quality_gate=True,unknown_effect_not_zero=True,outside_checkout=True,policy_qualified=False)
        dump(output/'verification.json',receipt);return receipt


def bundle_verify(bundle,output):
    bundle=Path(bundle).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Preserve bundle verification')
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='undercards-complete-v040-') as temporary:
        root=Path(temporary)
        with zipfile.ZipFile(bundle) as z:
            manifest_name=next(n for n in z.namelist() if n.endswith('/MANIFEST.json'));prefix=manifest_name.rsplit('/',1)[0]
            manifest=json.loads(z.read(manifest_name))
            if len(z.namelist())!=len(set(z.namelist())):raise ValueError('Duplicate bundle entry')
            for name,digest in manifest['files'].items():
                if hashlib.sha256(z.read(prefix+'/'+name)).hexdigest()!=digest:raise ValueError('Bundle hash mismatch: '+name)
            if set(z.namelist())!={prefix+'/'+n for n in manifest['files']}|{manifest_name}:raise ValueError('Unmanifested archive file')
            z.extractall(root)
        source=root/prefix/'source';env=os.environ.copy();env['PYTHONPATH']=str(source)
        (source/'work').mkdir(exist_ok=True)
        audit=command([sys.executable,'-m','card_eval.entity_audit','--folder','artifacts/card_eval/v9'],source,env)
        data=json.loads(audit.stdout);dump(output/'source-audit.json',data)
        if data['status']!='passed' or not data['source_commit'].startswith('archive:'):raise ValueError('Source archive audit depended on Git checkout')
        wheel=next((root/prefix).glob('*.whl'))
        with tempfile.TemporaryDirectory(prefix='undercards-zip-wheel-') as install_dir:
            target=Path(install_dir)/'installed'
            command([sys.executable,'-m','pip','install','--no-deps','--no-index','--no-cache-dir','--target',str(target),str(wheel)],root,os.environ.copy())
            env=os.environ.copy();env['PYTHONPATH']=str(target)
            names=json.loads(command([sys.executable,'-m','card_eval','models'],root,env).stdout)
            if len(names['models'])!=5:raise ValueError('ZIP wheel missing models')
        receipt=dict(status='passed',bundle=str(bundle),sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
            source_commit=manifest['source_commit'],manifest_files=len(manifest['files']),zip_bytes=bundle.stat().st_size,
            source_audit='passed without Git, game replay or refitting',installed_zip_wheel=True,
            scope='Archive completeness and installed entry contract, not universal policy quality')
        dump(output/'verification.json',receipt);return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['wheel','bundle']);p.add_argument('--input',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--expected-policy');args=p.parse_args()
    if args.mode=='wheel' and not args.expected_policy:raise ValueError('Expected frozen policy required for wheel check')
    result=wheel_verify(args.input,args.output,args.expected_policy) if args.mode=='wheel' else bundle_verify(args.input,args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))
