"""Offline phase verification; preserves machine-readable actual test results."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'stage-verification.json')
    args=p.parse_args()
    folder=ROOT/'analysis/monster-value-heuristic'
    suite=unittest.defaultTestLoader.discover(str(folder),pattern='test_*.py')
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    source={str(path.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(folder.glob('*.py'))}
    artifact={'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
              'skipped':len(result.skipped),'successful':result.wasSuccessful(),'source_sha256':source,
              'scope':'Offline local invariants; not card win-rate or complete numerical coverage validation.'}
    args.output.write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in artifact.items() if k!='source_sha256'}))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__': sys.exit(main())
