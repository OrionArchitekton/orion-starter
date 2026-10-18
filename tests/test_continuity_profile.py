"""Exercise the example as a process over installed PM/Handoff commands."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/continuity_starter.py'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='starter-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = Path(sys.executable).parent
        self.pm = self.bin / 'orion-pm'
        self.handoff = self.bin / 'orion-handoff'
        self.assertTrue(self.pm.is_file(), 'Run tests with installed profile dependencies')
        self.project = self.root / 'projects.json'
        self.write(self.project, {'schema_version': 1, 'projects': [{'id': 'sample'}]})
        self.pmc('init', '--projects', self.project)
        task = self.pmc('add', '--id', 'continuity-demo', '--title', 'Read the synthetic page twice',
                        '--project', 'sample', '--status', 'todo')['data']
        subprocess.run([str(self.handoff), '--json', '--store', str(self.root / 'handoff'), 'init'],
                       check=True, capture_output=True)
        self.fake = self.root / 'browser'
        self.fake.write_text('#!' + sys.executable + '\n' + (ROOT / 'tests/fixtures/native_cli.py').read_text())
        self.fake.chmod(0o700)
        self.client = self.root / 'client'
        self.client.write_text('#!' + sys.executable + '\n' + (ROOT / 'tests/fixtures/native_cli.py').read_text())
        self.client.chmod(0o700)
        self.config = self.root / 'browser.toml'
        self.config.write_text('[paths]\nstate = "' + str(self.root / 'browser-state') +
                               '"\nprofiles = "' + str(self.root / 'browser-profiles') +
                               '"\n[[browser]]\nname = "contdemo"\nscreen = 87\nrestore_session = false\n')
        self.config.chmod(0o600)
        self.agent = self.root / 'agent.json'
        self.write(self.agent, {})
        self.selection = self.root / 'selection.json'
        definition = {k: task['task'].get(k) for k in ('id', 'project', 'title', 'description', 'next_action')}
        self.value = {'selection_version': 1, 'run_id': str(uuid.uuid4()), 'workspace': str(self.root),
                      'pm': {'executable': str(self.pm), 'home': str(self.root / 'pm'),
                             'store_id': task['store_id'], 'task_id': 'continuity-demo',
                             'task_definition_sha256': hashlib.sha256(canonical(definition)).hexdigest()},
                      'handoff': {'executable': str(self.handoff), 'store': str(self.root / 'handoff')},
                      'browser': {'executable': str(self.fake), 'config': str(self.config),
                                  'config_sha256': digest(self.config), 'name': 'contdemo'},
                      'client': {'executable': str(self.client), 'config': str(self.agent),
                                 'config_sha256': digest(self.agent)}}
        self.write(self.selection, self.value)

    def write(self, path, value):
        path.write_text(json.dumps(value) + '\n')
        path.chmod(0o600)

    def pmc(self, *args):
        p = subprocess.run([str(self.pm), '--json', '--home', str(self.root / 'pm'), *map(str, args)],
                           capture_output=True, text=True, check=True)
        return json.loads(p.stdout)

    def invoke(self, mode, *args, env=None):
        return subprocess.run([sys.executable, str(EXAMPLE), '--selection', str(self.selection),
                               mode, *map(str, args)], capture_output=True, text=True,
                              env=env or os.environ.copy(), timeout=30)

    def snapshot(self):
        return {str(p.relative_to(self.root)): digest(p) for p in self.root.rglob('*') if p.is_file()}

    def test_inspect_selected_installed_stores_without_mutations(self):
        self.assertTrue(EXAMPLE.is_file(), 'continuity example not implemented')
        before = self.snapshot()
        p = self.invoke('inspect')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(result['state'], 'inspected')
        self.assertEqual(result['run_id'], self.value['run_id'])
        self.assertEqual(self.snapshot(), before)

    def test_malformed_component_envelope_returns_unknown_without_traceback(self):
        broken = self.root / 'broken-pm'
        broken.write_text('#!' + sys.executable + '\nprint("[]")\n')
        broken.chmod(0o700)
        self.value['pm']['executable'] = str(broken)
        self.write(self.selection, self.value)
        p = self.invoke('inspect')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        self.assertEqual(p.stderr, '')
        self.assertEqual(json.loads(p.stdout)['state'], 'reconciliation_required')

    def test_producer_yields_verified_context_without_completing_task(self):
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(result['state'], 'yielded')
        receipt = json.loads((self.root / 'yield.json').read_text())
        self.assertEqual(receipt['run_id'], self.value['run_id'])
        self.assertEqual(receipt['resource_stop'], 'clean')
        self.assertEqual(receipt['pm_yield'], {'task_status': 'todo', 'claim_state': 'absent'})
        current = self.pmc('show', 'continuity-demo')['data']
        self.assertEqual(current['task']['status'], 'todo')
        self.assertEqual(current['claim']['state'], 'absent')
        p = subprocess.run([str(self.handoff), '--json', '--store', str(self.root / 'handoff'),
                            'pickup', '--task', receipt['handoff_task_key']], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertEqual(json.loads(p.stdout)['data']['selected_record_id'], receipt['record_id'])

    def test_malformed_lease_after_claim_remains_unknown(self):
        self.write(self.root / 'faults.json', {'browser:lease': 'bad_time'})
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)['state'], 'reconciliation_required')
        self.assertEqual(self.pmc('show', 'continuity-demo')['data']['task']['status'], 'in_progress')
        self.assertFalse((self.root / 'yield.json').exists())


if __name__ == '__main__':
    unittest.main()
