"""Build a deterministic profile archive from one reviewed Git commit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = frozenset('''
.gitignore
.github/dependabot.yml
.github/workflows/ci.yml
.github/workflows/dependency-review.yml
LICENSE
README.md
RUNBOOK.md
bootstrap-requirements.txt
docs/plans/2026-10-17-starter-continuity-release-plan.md
docs/runbooks/starter-continuity.md
driver/package-lock.json
driver/package.json
examples/browser_starter.py
examples/cli_consumer.py
examples/continuity_starter.py
examples/project-config.json
manifest.json
profiles/continuity/README.md
profiles/continuity/manifest.json
profiles/continuity/requirements.in
profiles/continuity/requirements.lock
requirements.in
requirements.lock
scripts/build_candidate.py
scripts/check_profile.py
specs/starter-continuity-spec.md
tests/fixtures/component_cli.py
tests/fixtures/native_cli.py
tests/test_continuity_profile.py
tests/test_packaging.py
validation.json
validation/pm-browser-rc2.json
'''.split())


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], stderr=subprocess.PIPE)


def build(source, output):
    commit = git('rev-parse', '--verify', '--end-of-options', source + '^{commit}').decode().strip()
    entries = {}
    for entry in git('ls-tree', '-r', '-z', commit).split(b'\0'):
        if not entry:
            continue
        metadata, raw_name = entry.split(b'\t', 1)
        mode, kind, oid = metadata.decode().split()
        if mode not in ('100644', '100755') or kind != 'blob':
            raise ValueError('non_regular_member')
        entries[raw_name.decode('utf-8')] = oid
    if set(entries) != FILES:
        raise ValueError('unreviewed_or_missing_members')
    blobs = {name: git('cat-file', 'blob', oid) for name, oid in entries.items()}
    def digest(name):
        return hashlib.sha256(blobs[name]).hexdigest()
    root = json.loads(blobs['manifest.json'])
    descriptor = root['optional_profiles']['continuity']
    if digest(descriptor['path']) != descriptor['sha256']:
        raise ValueError('profile_digest_mismatch')
    for manifest in (root, json.loads(blobs[descriptor['path']])):
        if manifest['version'] != '0.2.0-rc.1':
            raise ValueError('unsupported_distribution')
        checks = [(manifest.get('python_lock_path', 'requirements.lock'), manifest['python_lock_sha256']),
                  ('driver/package-lock.json', manifest['navigation_client']['npm_lock_sha256']),
                  (manifest['bootstrap']['path'], manifest['bootstrap']['sha256'])]
        checks += [(e['path'], e['sha256']) for e in manifest['examples']]
        if any(digest(name) != expected for name, expected in checks):
            raise ValueError('member_digest_mismatch')
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as target:
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in sorted(FILES):
                info = zipfile.ZipInfo('orion-starter-0.2.0-rc.1/' + name, (2026, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, blobs[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        target.flush()
        os.fsync(target.fileno())
    return {'version': '0.2.0-rc.1', 'source_commit': commit, 'members': len(FILES),
            'archive': str(output), 'sha256': hashlib.sha256(Path(output).read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='HEAD')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        result = build(args.source, args.output)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print(json.dumps({'state': 'refused', 'reason': str(exc) if isinstance(exc, ValueError) else 'build_unavailable'}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
