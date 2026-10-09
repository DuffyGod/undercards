import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SOURCE=Path(__file__).resolve().parents[2]/'tools/restore_stage_evidence.py'
spec=importlib.util.spec_from_file_location('cloud_restore_tests',SOURCE)
restore=importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


def fixture(root,files):
    folder=root/'research-archive'
    folder.mkdir()
    entries=[]
    with zipfile.ZipFile(folder/'stage-evidence.zip','w') as archive:
        for path,raw in files.items():
            archive.writestr(path,raw)
            entries.append({'path':path,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    manifest={'entries':entries,'archive_sha256':hashlib.sha256((folder/'stage-evidence.zip').read_bytes()).hexdigest()}
    (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')


class CloudRestoreTests(unittest.TestCase):
    def test_restore_preserves_exact_bytes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            fixture(root,{'evidence/a.json':b'{"value":1}\n'})
            self.assertEqual(restore.restore(root)['restored'],1)
            self.assertEqual((root/'evidence/a.json').read_bytes(),b'{"value":1}\n')
            self.assertEqual(restore.restore(root)['already_identical'],1)

    def test_existing_different_evidence_blocks_all_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            fixture(root,{'a.json':b'original','b.json':b'new'})
            (root/'a.json').write_bytes(b'local edit')
            with self.assertRaises(ValueError): restore.restore(root)
            self.assertEqual((root/'a.json').read_bytes(),b'local edit')
            self.assertFalse((root/'b.json').exists())

    def test_traversal_and_archive_tampering_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'checkout'; root.mkdir()
            fixture(root,{'safe.json':b'safe','../outside.json':b'escape'})
            with self.assertRaises(ValueError): restore.restore(root)
            self.assertFalse((root/'safe.json').exists())
            self.assertFalse((root.parent/'outside.json').exists())
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            fixture(root,{'a.json':b'bytes'})
            with (root/'research-archive/stage-evidence.zip').open('ab') as file:
                file.write(b'tampered')
            with self.assertRaises(ValueError): restore.restore(root)
            self.assertFalse((root/'a.json').exists())
