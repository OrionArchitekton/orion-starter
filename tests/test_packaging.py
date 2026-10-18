"""Distribution checks operate on the complete versioned profile."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_continuity_lock_is_checked_and_tampering_is_refused(self):
        self.assertTrue((ROOT / 'profiles/continuity/manifest.json').is_file(), 'continuity profile not packaged')
        with tempfile.TemporaryDirectory(prefix='starter-package-test-') as tmp:
            target = Path(tmp)
            for path in ['manifest.json', 'LICENSE', 'bootstrap-requirements.txt', 'requirements.lock',
                         'driver/package-lock.json', 'examples', 'profiles', 'scripts/check_profile.py']:
                source = ROOT / path
                (target / path).parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, target / path, ignore=shutil.ignore_patterns('__pycache__'))
                else:
                    shutil.copyfile(source, target / path)
            def check():
                return subprocess.run([sys.executable, str(target / 'scripts/check_profile.py')],
                                      capture_output=True, text=True)
            self.assertEqual(check().returncode, 0)
            with (target / 'profiles/continuity/requirements.lock').open('a') as f:
                f.write('\n# tampered after review\n')
            self.assertNotEqual(check().returncode, 0)
            manifest = json.loads((ROOT / 'profiles/continuity/manifest.json').read_text())
            self.assertEqual(manifest['handoff_contract'], {'interface_version': 1, 'store_version': 1, 'record_version': 1})

    def test_builder_is_deterministic_and_refuses_unreviewed_files(self):
        builder = ROOT / 'scripts/build_candidate.py'
        self.assertTrue(builder.is_file(), 'deterministic archive builder not implemented')
        with tempfile.TemporaryDirectory(prefix='starter-build-test-') as tmp:
            target = Path(tmp) / 'source'
            target.mkdir()
            for name in ['.gitignore', '.github', 'LICENSE', 'README.md', 'RUNBOOK.md', 'bootstrap-requirements.txt',
                         'manifest.json', 'requirements.in', 'requirements.lock', 'validation.json', 'validation',
                         'driver/package.json', 'driver/package-lock.json', 'examples', 'profiles', 'scripts',
                         'tests', 'specs', 'docs']:
                source = ROOT / name
                (target / name).parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, target / name, ignore=shutil.ignore_patterns('__pycache__'))
                else:
                    shutil.copyfile(source, target / name)
            def git(*args):
                return subprocess.run(['git', *args], cwd=target, capture_output=True, check=True)
            git('init', '-q')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Fixture')
            def build(name):
                return subprocess.run([sys.executable, str(target / 'scripts/build_candidate.py'), '--output',
                                       str(Path(tmp) / name)], capture_output=True, text=True)
            a, b = build('a.zip'), build('b.zip')
            self.assertEqual(a.returncode, 0, a.stdout + a.stderr)
            self.assertEqual(b.returncode, 0, b.stdout + b.stderr)
            self.assertEqual((Path(tmp) / 'a.zip').read_bytes(), (Path(tmp) / 'b.zip').read_bytes())
            with zipfile.ZipFile(Path(tmp) / 'a.zip') as archive:
                self.assertTrue(all(not p.startswith('/') and '..' not in Path(p).parts
                                    and '.private' not in Path(p).parts and '.git' not in Path(p).parts
                                    for p in archive.namelist()))
            (target / 'unreviewed.txt').write_text('synthetic unreviewed member')
            git('add', 'unreviewed.txt')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Unexpected member')
            self.assertNotEqual(build('c.zip').returncode, 0)
            git('rm', 'unreviewed.txt')
            (target / 'README.md').unlink()
            (target / 'README.md').symlink_to('LICENSE')
            git('add', 'README.md')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Symlink member')
            self.assertNotEqual(build('d.zip').returncode, 0)


if __name__ == '__main__':
    unittest.main()
