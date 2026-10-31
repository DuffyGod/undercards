"""Load verified primitives without taking over generic Python module names."""
from pathlib import Path
import importlib.util, sys

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'analysis/strategic-model'
BUNDLED = Path(__file__).resolve().parent / '_engine'


def load(label, path, aliases=None):
    if (BUNDLED / path.name).exists(): path = BUNDLED / path.name
    name = '_undercards_card_eval_' + label
    if name in sys.modules: return sys.modules[name]
    aliases = aliases or {}
    previous = {key: sys.modules.get(key) for key in aliases}
    search = list(sys.path)
    try:
        sys.modules.update(aliases)
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec); sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    except Exception:
        sys.modules.pop(name, None); raise
    finally:
        sys.path[:] = search
        for key, value in previous.items():
            if value is None: sys.modules.pop(key, None)
            else: sys.modules[key] = value


model = load('roles', OLD / '2026-10-20/model.py')
tactics = load('tactics', OLD / '2026-10-30/tactics.py')
bridge = load('bridge', OLD / '2026-10-30/engine.py', {'model': model, 'tactics': tactics})
rules = load('rules', OLD / '2026-10-31/mechanisms.py')
features = load('features', OLD / '2026-10-31/features.py', {'mechanisms': rules})
environment = load('environment', OLD / '2026-10-31/environment.py', {'engine': bridge, 'mechanisms': rules})
learner = load('learner', OLD / '2026-10-31/learner.py', {'features': features})
agents = load('agents', OLD / '2026-10-31/agents.py', {'environment': environment, 'features': features, 'mechanisms': rules})
records = load('records', OLD / '2026-10-31/records.py', {'features': features})
