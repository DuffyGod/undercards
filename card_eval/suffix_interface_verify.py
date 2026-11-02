"""Verify an experimental checkpoint with standalone source outside checkout.

This is an application contract, not a new release or policy-quality trial.
The rejected prototype remains experimental and has no own-policy value fit.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile
from .api import default_request
from .network import Network
from .training import dump,commit


def verify(folder,output,checkpoint_name='regret_mean-selected.npz',seed_start=3491000):
    folder=Path(folder).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Preserve interface verification')
    output.mkdir(parents=True);checkpoint=folder/checkpoint_name;net,meta=Network.load(checkpoint)
    if meta.get('value_unfitted') is not True:raise ValueError('This contract tests an explicitly unfitted value checkpoint')
    with tempfile.TemporaryDirectory(prefix='undercards-prototype-source-') as temporary:
        root=Path(temporary);app=root/'app';app.mkdir();outside=root/'outside';outside.mkdir()
        shutil.copytree(Path(__file__).resolve().parent,app/'card_eval',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        model=root/'prototype.npz';shutil.copy2(checkpoint,model);shutil.copy2(folder/'validation.json',root/'validation.json')
        env=os.environ.copy();env['PYTHONPATH']=str(app);env['OPENBLAS_NUM_THREADS']='1'
        def command(args,expected=0):
            r=subprocess.run([sys.executable,'-m','card_eval',*args],cwd=outside,env=env,text=True,capture_output=True)
            if r.returncode!=expected:raise RuntimeError(f'Unexpected exit{r.returncode}: {r.stdout}\n{r.stderr}')
            return r
        origin=subprocess.run([sys.executable,'-c','import card_eval;print(card_eval.__file__)'],cwd=outside,env=env,text=True,capture_output=True,check=True).stdout.strip()
        if not Path(origin).is_relative_to(app):raise ValueError('Imported checkout instead of standalone source')
        request=default_request(['Bench'],samples=2);request.update(seed_start=seed_start,opponents=request['opponents'][:1],policies=['learned'],decision_seconds=.25)
        input_path=output/'request.json';dump(input_path,request)
        common=['evaluate','--input',str(input_path),'--checkpoint',str(model)]
        command(common+['--output',str(output/'blocked')],expected=2)
        blocked=json.loads((output/'blocked/result.json').read_text())
        if blocked['status']!='unqualified_policy' or blocked['scores'] is not None:raise ValueError('Rejected prototype escaped quality gate')
        r=command(common+['--experimental-model','--output',str(output/'actor')]);(output/'actor.log').write_text(r.stdout+r.stderr)
        actor=json.loads((output/'actor/result.json').read_text())
        if actor['status']!='complete' or actor['games']!=8 or actor['unresolved'] or actor['frozen_policy']!=net.fingerprint:raise ValueError('Standalone actor contract failed')
        if actor['comparisons'][0]['recommendation']!='experimental_only':raise ValueError('Rejected actor produced a reliable recommendation')
        unfitted=output/'unfitted-request.json';dump(unfitted,dict(request,planner=dict(mode='value')))
        command(['evaluate','--input',str(unfitted),'--checkpoint',str(model),'--experimental-model','--output',str(output/'unfitted-value')],expected=2)
        value=json.loads((output/'unfitted-value/result.json').read_text())
        if value['status']!='unsupported_policy_configuration' or value['scores'] is not None or value['issues'][0]['code']!='unfitted_value':raise ValueError('Unfitted critic was used for value planning')
        unknown=json.loads(command(['inspect','Glyde'],expected=2).stdout)
        if unknown['status']!='unsupported' or unknown['score'] is not None:raise ValueError('Unknown mechanism scored as zero')
        dump(output/'unknown.json',unknown)
        result=dict(status='passed',source_commit=commit(),source_mode='Standalone copy of current branch source, not a new wheel/release',
            module_origin=origin,checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),frozen_policy=net.fingerprint,
            slots=actor['games'],unresolved=actor['unresolved'],decision_seconds=.25,quality_gate=True,unfitted_value_rejected=True,
            unknown_not_zero=True,default_model_replaced=False,scope='Source/interface contract only; eight engineering slots are not independent policy-quality evidence')
        dump(output/'verification.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--checkpoint-name',default='regret_mean-selected.npz');p.add_argument('--seed-start',type=int,default=3491000);a=p.parse_args()
    print(json.dumps(verify(a.folder,a.output,a.checkpoint_name,a.seed_start),indent=2))
