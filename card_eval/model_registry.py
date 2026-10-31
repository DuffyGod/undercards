"""Versioned models shipped with the application, with explicit quality state."""
from pathlib import Path
import hashlib,json

MODELS=Path(__file__).resolve().parent/'models'


def catalog():
    path=MODELS/'registry.json'
    if not path.exists():raise ValueError('This installation is missing its model registry')
    return json.loads(path.read_text(encoding='utf-8'))['models']


def checkpoint(name):
    entry=next((m for m in catalog() if m['name']==name),None)
    if entry is None:raise ValueError('Unknown bundled model: '+str(name))
    path=MODELS/entry['file']
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
        raise ValueError('Bundled model is missing or does not match its release manifest')
    return path


def example(learned=False):
    name='learned-request.json' if learned else 'reference-request.json'
    return json.loads((Path(__file__).resolve().parent/'examples'/name).read_text(encoding='utf-8'))
