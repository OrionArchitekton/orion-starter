"""Verify both versioned profiles without acquiring resources or changing state."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def selected_file(name):
    path = Path(name)
    assert not path.is_absolute() and not ({'..', '.git', '.private'} & set(path.parts)), name
    target = ROOT / path
    assert target.is_file() and not target.is_symlink() and ROOT in target.resolve().parents, name
    return target


def digest(name):
    return hashlib.sha256(selected_file(name).read_bytes()).hexdigest()


def check(manifest):
    assert manifest['schema_version'] == 1
    assert manifest['distribution'] == 'orion-starter' and manifest['version'] == '0.2.0-rc.1'
    assert digest(manifest.get('python_lock_path', 'requirements.lock')) == manifest['python_lock_sha256']
    assert digest('driver/package-lock.json') == manifest['navigation_client']['npm_lock_sha256']
    assert manifest['navigation_client']['version'] == '0.25.4'
    assert digest(manifest['bootstrap']['path']) == manifest['bootstrap']['sha256']
    for example in manifest['examples']:
        assert digest(example['path']) == example['sha256']
    assert manifest['pm_contract'] == {'api_version': 1, 'store_format': 1}
    assert all(c['license'] == 'MIT' for c in manifest['components'])


def main():
    manifest = json.loads(selected_file('manifest.json').read_text())
    check(manifest)
    descriptor = manifest['optional_profiles']['continuity']
    assert digest(descriptor['path']) == descriptor['sha256']
    continuity = json.loads(selected_file(descriptor['path']).read_text())
    check(continuity)
    assert continuity['handoff_contract'] == {'interface_version': 1, 'store_version': 1, 'record_version': 1}
    assert [(c['name'], c['version']) for c in continuity['components']] == [
        ('orion-pm', '0.1.1'), ('orion-browser', '0.1.0'), ('orion-handoff', '0.1.0')]
    assert continuity['components'][:2] == manifest['components']
    assert 'MIT License' in selected_file('LICENSE').read_text()
    print('Both profile locks, examples, contracts and MIT license verified')


if __name__ == '__main__':
    main()
