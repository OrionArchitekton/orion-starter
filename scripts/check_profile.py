"""Verify three versioned profiles without acquiring resources or changing state."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_COMPONENTS = [
    ('orion-pm', '0.1.1', 'orion-pm-oss', 'orion_pm-0.1.1-py3-none-any.whl', '54f28272550054c32958c67fd84094b825bb387f91ad3efe3b342d463b9c16c7'),
    ('orion-handoff', '0.1.0', 'orion-handoff', 'orion_handoff-0.1.0-py3-none-any.whl', 'e1f3e1e43839cfd2896cfc553bef9366867c1cf50bce1e4d4762cdbec9977e41'),
    ('orion-results', '0.1.0', 'orion-results', 'orion_results-0.1.0-py3-none-any.whl', '67af57c4deda8967db83c2176642184bb3b7fb59f826539284086efa95e78e2e'),
    ('orion-worktree-report', '0.1.0', 'orion-worktree-report', 'orion_worktree_report-0.1.0-py3-none-any.whl', 'f06d7ca9d3fd1001b9bd16ed18a8ee7827727c09eeb4a535f41692723336550b')]


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def selected_file(name):
    path = Path(name)
    require(not path.is_absolute() and not ({'..', '.git', '.private'} & set(path.parts)), 'invalid_selected_path')
    target = ROOT / path
    require(target.is_file() and not target.is_symlink() and ROOT in target.resolve().parents, 'invalid_selected_file')
    return target


def check(manifest, digest):
    require(manifest['schema_version'] == 1, 'unsupported_schema')
    require(manifest['distribution'] == 'orion-starter' and manifest['version'] == '0.3.0-rc.1', 'unsupported_distribution')
    require(digest(manifest.get('python_lock_path', 'requirements.lock')) == manifest['python_lock_sha256'], 'python_lock_changed')
    require(digest('driver/package-lock.json') == manifest['navigation_client']['npm_lock_sha256'], 'npm_lock_changed')
    require(manifest['navigation_client']['version'] == '0.25.4', 'unsupported_client')
    require(digest(manifest['bootstrap']['path']) == manifest['bootstrap']['sha256'], 'bootstrap_changed')
    for example in manifest['examples']:
        require(digest(example['path']) == example['sha256'], 'example_changed')
    require(manifest['pm_contract'] == {'api_version': 1, 'store_format': 1}, 'unsupported_pm_contract')
    require(all(c['license'] == 'MIT' for c in manifest['components']), 'unsupported_component_license')


def verify(read_file):
    def digest(name):
        return hashlib.sha256(read_file(name)).hexdigest()
    manifest = json.loads(read_file('manifest.json'))
    check(manifest, digest)
    descriptor = manifest['optional_profiles']['continuity']
    require(digest(descriptor['path']) == descriptor['sha256'], 'profile_changed')
    continuity = json.loads(read_file(descriptor['path']))
    check(continuity, digest)
    require(continuity['handoff_contract'] == {'interface_version': 1, 'store_version': 1, 'record_version': 1},
            'unsupported_handoff_contract')
    require([(c['name'], c['version']) for c in continuity['components']] == [
        ('orion-pm', '0.1.1'), ('orion-browser', '0.1.0'), ('orion-handoff', '0.1.0')], 'unsupported_components')
    require(continuity['components'][:2] == manifest['components'], 'base_components_changed')
    descriptor = manifest['optional_profiles']['development-evidence']
    require(descriptor['path'] == 'profiles/development-evidence/manifest.json', 'evidence_profile_path')
    require(digest(descriptor['path']) == descriptor['sha256'], 'evidence_profile_changed')
    evidence = json.loads(read_file(descriptor['path']))
    require(type(evidence['schema_version']) is int and evidence['schema_version'] == 1
            and evidence['distribution'] == 'orion-starter' and evidence['version'] == '0.3.0-rc.1'
            and evidence['profile'] == 'development-evidence' and type(evidence['profile_interface_version']) is int
            and evidence['profile_interface_version'] == 1, 'unsupported_evidence_profile')
    expected = [{'name': name, 'version': version, 'url': f'https://github.com/OrionArchitekton/{repo}/releases/download/v{version}/{filename}',
                 'sha256': checksum, 'license': 'MIT'} for name, version, repo, filename, checksum in EVIDENCE_COMPONENTS]
    require(evidence['components'] == expected, 'evidence_components_changed')
    lock = ''.join(f'{name}=={version} --hash=sha256:{checksum}\n' for name, version, repo, filename, checksum in EVIDENCE_COMPONENTS).encode()
    require(evidence['python_lock_path'] == 'profiles/development-evidence/requirements.lock'
            and read_file(evidence['python_lock_path']) == lock and digest(evidence['python_lock_path']) == evidence['python_lock_sha256'], 'evidence_lock_changed')
    require(evidence['contracts'] == {'pm_api': 1, 'pm_store': 1, 'handoff_interface': 1, 'handoff_store': 1,
                                     'handoff_record': 1, 'results_reference': 1, 'worktree_report_interface': 1}
            and all(type(value) is int for value in evidence['contracts'].values()), 'evidence_contract_changed')
    installer = evidence['installer']
    require(installer['path'] == 'profiles/development-evidence/installer.lock' and installer['pip'] == '26.2.1'
            and read_file(installer['path']) == b'pip==26.2.1 --hash=sha256:71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e\n'
            and digest(installer['path']) == installer['sha256'], 'evidence_installer_changed')
    require([x['path'] for x in evidence['examples']] == ['profiles/development-evidence/run.py', 'profiles/development-evidence/results_io.py'], 'evidence_entry_changed')
    for selected in evidence['examples'] + evidence.get('notices', []):
        require(digest(selected['path']) == selected['sha256'], 'evidence_selected_file_changed')
    require(evidence.get('notices') == [{'path': 'profiles/development-evidence/THIRD_PARTY_NOTICES.md',
                                      'sha256': 'c8d4c4f38c11345fd00286b12da8e2fffb72bcf2bb8a01dd602fc173326c1a79'}], 'evidence_notice_changed')
    require(digest('LICENSE') == '684b097118cc67a5d1e356b77daa65c2b829a81325d73ddfc0140eeb6e10a56f',
            'license_changed')


def main():
    verify(lambda name: selected_file(name).read_bytes())
    print('Three profile locks, examples, contracts and MIT license verified')


if __name__ == '__main__':
    main()
