"""Create the complete application/source/evidence bundle from a clean commit."""
from pathlib import Path
import argparse,hashlib,json,subprocess,zipfile
from . import __version__

ROOT=Path(__file__).resolve().parents[1]


def build(output):
    output=Path(output)
    if output.exists():raise ValueError('Preserve release artifact; use a new output')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise ValueError('Freeze source, models and evidence in Git before creating the delivery bundle')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    selected=[]
    for name in tracked:
        if not name:continue
        include=(name.startswith(('card_eval/','tests/','examples/','artifacts/card_eval/v5/','artifacts/card_eval/v6/')) or
                 name in ('pyproject.toml','README.md','AGENTS.md','CURRENT_CHECKPOINT.md','RESEARCH_PRINCIPLES.md','RESEARCH_AUTOMATION.md',
                          'artifacts/card_eval/v4/primary-value.npz','artifacts/card_eval/v4/validation.json'))
        if include:selected.append(name)
    wheel=ROOT/'artifacts/card_eval/dist'/f'undercards_card_eval-{__version__}-py3-none-any.whl'
    if not wheel.is_file():raise ValueError('Build and verify wheel first')
    prefix=f'undercards-card-evaluator-{__version__}'
    manifest=dict(version=__version__,source_commit=revision,source_branch='research/local-method-lab-20261018',
                  completeness='Runnable application, named trained models, source and necessary V6 inputs/evidence. Supported game rules and policy quality remain limited.',files={})
    def add(archive,name,data):
        archive.writestr(prefix+'/'+name,data);manifest['files'][name]=hashlib.sha256(data).hexdigest()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        add(archive,wheel.name,wheel.read_bytes())
        add(archive,'START_HERE.md',(ROOT/'artifacts/card_eval/v6/START_HERE.md').read_bytes())
        for example in ('reference-request.json','learned-request.json'):
            add(archive,'examples/'+example,(ROOT/'card_eval/examples'/example).read_bytes())
        for name in selected:add(archive,'source/'+name,(ROOT/name).read_bytes())
        add(archive,'source/SOURCE_REVISION.json',json.dumps(dict(source_commit=revision,source_mode='frozen delivery archive',version=__version__),indent=2).encode())
        archive.writestr(prefix+'/MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    return dict(version=__version__,source_commit=revision,bundle=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                bytes=output.stat().st_size,files=len(manifest['files']))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    print(json.dumps(build(args.output)))
