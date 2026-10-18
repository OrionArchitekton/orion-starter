"""Distribution checks operate on the complete versioned profile."""
import hashlib
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
            def check(*options):
                return subprocess.run([sys.executable, *options, str(target / 'scripts/check_profile.py')],
                                      capture_output=True, text=True)
            self.assertEqual(check().returncode, 0)
            self.assertEqual(check('-O').returncode, 0)
            lock = target / 'profiles/continuity/requirements.lock'
            original_lock = lock.read_bytes()
            with (target / 'profiles/continuity/requirements.lock').open('a') as f:
                f.write('\n# tampered after review\n')
            for options in ((), ('-O',), ('-OO',)):
                with self.subTest(tampered='lock', options=options):
                    self.assertNotEqual(check(*options).returncode, 0)
            lock.write_bytes(original_lock)
            outside = target.parent / (target.name + '-outside-license')
            outside.write_text('MIT License\n')
            self.addCleanup(outside.unlink)
            (target / 'LICENSE').unlink()
            (target / 'LICENSE').symlink_to(outside)
            with self.subTest(tampered='selected symlink', options=('-O',)):
                self.assertNotEqual(check('-O').returncode, 0)
            (target / 'LICENSE').unlink()
            shutil.copyfile(ROOT / 'LICENSE', target / 'LICENSE')
            (target / 'LICENSE').write_text((ROOT / 'LICENSE').read_text() + '\nAdditional restrictive terms.\n')
            for options in ((), ('-O',), ('-OO',)):
                with self.subTest(tampered='license content', options=options):
                    self.assertNotEqual(check(*options).returncode, 0)
            shutil.copyfile(ROOT / 'LICENSE', target / 'LICENSE')
            invalid = json.loads((target / 'manifest.json').read_text())
            invalid['schema_version'] = 99
            (target / 'manifest.json').write_text(json.dumps(invalid))
            with self.subTest(tampered='contract', options=('-O',)):
                self.assertNotEqual(check('-O').returncode, 0)
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
            def build(name, source='HEAD'):
                return subprocess.run([sys.executable, str(target / 'scripts/build_candidate.py'), '--source', source, '--output',
                                       str(Path(tmp) / name)], capture_output=True, text=True)
            a, b = build('a.zip'), build('b.zip')
            self.assertEqual(a.returncode, 0, a.stdout + a.stderr)
            self.assertEqual(b.returncode, 0, b.stdout + b.stderr)
            self.assertEqual((Path(tmp) / 'a.zip').read_bytes(), (Path(tmp) / 'b.zip').read_bytes())
            with zipfile.ZipFile(Path(tmp) / 'a.zip') as archive:
                self.assertTrue(all(not p.startswith('/') and '..' not in Path(p).parts
                                    and '.private' not in Path(p).parts and '.git' not in Path(p).parts
                                    for p in archive.namelist()))
            originals = {name: (target / name).read_bytes() for name in
                         ['manifest.json', 'profiles/continuity/manifest.json', 'LICENSE']}
            cases = [('manifest.json', 'schema_version', 99),
                     ('manifest.json', 'distribution', 'unapproved-distribution'),
                     ('manifest.json', 'pm_contract', {'api_version': 99, 'store_format': 1}),
                     ('profiles/continuity/manifest.json', 'handoff_contract', {'interface_version': 99}),
                     ('profiles/continuity/manifest.json', 'components', []),
                     ('LICENSE', None, None)]
            for index, (name, field, value) in enumerate(cases):
                with self.subTest(selected_commit_tampering=name, field=field):
                    if field:
                        invalid = json.loads(originals[name])
                        invalid[field] = value
                        (target / name).write_text(json.dumps(invalid))
                    else:
                        (target / name).write_bytes(originals[name] + b'\nAdditional restrictive terms.\n')
                    if name == 'profiles/continuity/manifest.json':
                        root = json.loads(originals['manifest.json'])
                        root['optional_profiles']['continuity']['sha256'] = hashlib.sha256((target / name).read_bytes()).hexdigest()
                        (target / 'manifest.json').write_text(json.dumps(root))
                    git('add', *originals)
                    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Invalid selected profile')
                    selected = git('rev-parse', 'HEAD').stdout.decode().strip()
                    for original_name, raw in originals.items():
                        (target / original_name).write_bytes(raw)
                    output = f'invalid-{index}.zip'
                    refused = build(output, source=selected)
                    self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
                    self.assertFalse((Path(tmp) / output).exists(), 'Invalid selected commit created an archive')
            git('add', *originals)
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Restore valid profiles')
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
