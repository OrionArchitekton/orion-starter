"""Verify both versioned profiles without acquiring resources or changing state."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def selected_file(name):
    path = Path(name)
    require(not path.is_absolute() and not ({'..', '.git', '.private'} & set(path.parts)), 'invalid_selected_path')
    target = ROOT / path
    require(target.is_file() and not target.is_symlink() and ROOT in target.resolve().parents, 'invalid_selected_file')
    return target


def digest(name):
    return hashlib.sha256(selected_file(name).read_bytes()).hexdigest()


def check(manifest):
    require(manifest['schema_version'] == 1, 'unsupported_schema')
    require(manifest['distribution'] == 'orion-starter' and manifest['version'] == '0.2.0-rc.1', 'unsupported_distribution')
    require(digest(manifest.get('python_lock_path', 'requirements.lock')) == manifest['python_lock_sha256'], 'python_lock_changed')
    require(digest('driver/package-lock.json') == manifest['navigation_client']['npm_lock_sha256'], 'npm_lock_changed')
    require(manifest['navigation_client']['version'] == '0.25.4', 'unsupported_client')
    require(digest(manifest['bootstrap']['path']) == manifest['bootstrap']['sha256'], 'bootstrap_changed')
    for example in manifest['examples']:
        require(digest(example['path']) == example['sha256'], 'example_changed')
    require(manifest['pm_contract'] == {'api_version': 1, 'store_format': 1}, 'unsupported_pm_contract')
    require(all(c['license'] == 'MIT' for c in manifest['components']), 'unsupported_component_license')


def main():
    manifest = json.loads(selected_file('manifest.json').read_text())
    check(manifest)
    descriptor = manifest['optional_profiles']['continuity']
    require(digest(descriptor['path']) == descriptor['sha256'], 'profile_changed')
    continuity = json.loads(selected_file(descriptor['path']).read_text())
    check(continuity)
    require(continuity['handoff_contract'] == {'interface_version': 1, 'store_version': 1, 'record_version': 1},
            'unsupported_handoff_contract')
    require([(c['name'], c['version']) for c in continuity['components']] == [
        ('orion-pm', '0.1.1'), ('orion-browser', '0.1.0'), ('orion-handoff', '0.1.0')], 'unsupported_components')
    require(continuity['components'][:2] == manifest['components'], 'base_components_changed')
    require(digest('LICENSE') == '684b097118cc67a5d1e356b77daa65c2b829a81325d73ddfc0140eeb6e10a56f',
            'license_changed')
    print('Both profile locks, examples, contracts and MIT license verified')


if __name__ == '__main__':
    main()
