"""Public profile process seam over installed components and disposable Git data."""
import base64
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
ENTRY = ROOT / 'profiles/development-evidence/run.py'
TITLE = 'Demonstrate exact worktree evidence continuation'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='evidence-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = Path(sys.executable).parent
        self.pm = self.bin / 'orion-pm'
        self.handoff = self.bin / 'orion-handoff'
        self.reporter = self.bin / 'orion-worktree-report'
        for p in (self.pm, self.handoff, self.reporter):
            self.assertTrue(p.is_file(), 'Install the selected public component wheels first')
        self.run_id = str(uuid.uuid4())
        self.task_id = 'evidence-' + self.run_id.replace('-', '')
        self.write(self.root / 'projects.json', {'schema_version': 1, 'projects': [{'id': 'sample'}]})
        self.pmc('init', '--projects', self.root / 'projects.json')
        task = self.pmc('add', '--id', self.task_id, '--title', TITLE, '--project', 'sample', '--status', 'todo')['data']
        self.hc('init')
        (self.root / 'results').mkdir(mode=0o700)
        self.repo = self.root / 'repo'
        self.git('init', '-b', 'main', self.repo, cwd=self.root)
        self.git('config', 'user.name', 'Synthetic Worker')
        self.git('config', 'user.email', 'worker@example.invalid')
        (self.repo / 'shared.txt').write_text('baseline\n')
        self.git('add', 'shared.txt')
        self.git('commit', '-m', 'synthetic baseline')
        self.workers = [self.root / 'worker-a', self.root / 'worker-b']
        for index, tree in enumerate(self.workers):
            self.git('worktree', 'add', '-b', 'worker-' + str(index), tree)
            (tree / 'shared.txt').write_text('worker ' + str(index) + '\n')
        definition = {k: task['task'].get(k) for k in ('id', 'project', 'title', 'description', 'next_action')}
        self.value = {
            'selection_version': 1, 'profile': 'development-evidence',
            'goal': 'capture-and-reobserve-overlap', 'run_id': self.run_id, 'workspace': str(self.root),
            'pm': {'executable': str(self.pm), 'home': str(self.root / 'pm'), 'store_id': task['store_id'],
                   'task_id': self.task_id, 'task_definition_sha256': sha(canonical(definition))},
            'handoff': {'executable': str(self.handoff), 'store': str(self.root / 'handoff')},
            'results': {'root': str(self.root / 'results'), 'limits': {
                'max_input_bytes': 1048576, 'max_results': 1, 'max_payload_bytes': 1048576, 'inline_bytes': 4000}},
            'reporter': {'executable': str(self.reporter), 'repositories': [str(self.repo)]}}
        self.selection = self.root / 'selection.json'
        self.write(self.selection, self.value)
        self.write(self.root / 'sentinel.json', {'unrelated': 'preserve'})

    def write(self, path, value):
        path.write_bytes(canonical(value) + b'\n')
        path.chmod(0o600)

    def git(self, *args, cwd=None):
        return subprocess.check_output(['git', '-C', str(cwd or self.repo), *map(str, args)], stderr=subprocess.PIPE)

    def pmc(self, *args):
        p = subprocess.run([str(self.pm), '--json', '--home', str(self.root / 'pm'), *map(str, args)],
                           capture_output=True, check=True)
        return json.loads(p.stdout)

    def hc(self, *args, input=None):
        p = subprocess.run([str(self.handoff), '--json', '--store', str(self.root / 'handoff'), *map(str, args)],
                           input=input, capture_output=True, check=True)
        return json.loads(p.stdout)

    def invoke(self, mode, *args):
        return subprocess.run([sys.executable, '-I', '-B', str(ENTRY), mode, '--selection', str(self.selection),
                               *map(str, args)], capture_output=True, timeout=100)

    def snapshot(self, root=None):
        return {str(p.relative_to(root or self.root)): (p.stat().st_mode & 0o777, sha(p.read_bytes()))
                for p in (root or self.root).rglob('*') if p.is_file()}

    def proxy(self, component, at, fault):
        script = self.root / (component + '-proxy')
        script.write_text('#!' + sys.executable + '\n' + (ROOT / 'tests/fixtures/evidence_component.py').read_text())
        script.chmod(0o700)
        config = {'component': component, 'executable': self.value[component]['executable'],
                  'at': at, 'fault': fault, 'log': str(self.root / 'calls.jsonl')}
        self.write(Path(str(script) + '.json'), config)
        self.value[component]['executable'] = str(script)
        self.write(self.selection, self.value)
        return script

    def test_select_and_inspect(self):
        self.assertTrue(ENTRY.is_file(), 'development-evidence entry is not implemented')
        before = self.snapshot()
        p = self.invoke('inspect')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(result['state'], 'inspected')
        self.assertEqual(result['run_id'], self.run_id)
        self.assertEqual(result['outcomes']['task']['store_id'], self.value['pm']['store_id'])
        self.assertEqual(result['versions'], {'orion-pm': '0.1.1', 'orion-handoff': '0.1.0',
                                           'orion-results': '0.1.0', 'orion-worktree-report': '0.1.0'})
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list((self.root / 'results').iterdir()), [])
        self.assertFalse((self.root / 'receipts').exists())

    def test_invalid_selection_and_wrong_store_are_read_only(self):
        original = canonical(self.value)
        for case in ('extra', 'missing_executable', 'wrong_store', 'boolean_version', 'state_overlap'):
            self.value = json.loads(original)
            if case == 'extra':
                self.value['ambient_fallback'] = True
            elif case == 'missing_executable':
                self.value['reporter']['executable'] = str(self.root / 'missing')
            elif case == 'wrong_store':
                self.value['pm']['store_id'] = '0' * 32
            elif case == 'boolean_version':
                self.value['selection_version'] = True
            else:
                self.value['results']['root'] = self.value['pm']['home']
            self.write(self.selection, self.value)
            before = self.snapshot()
            p = self.invoke('inspect')
            self.assertEqual(p.returncode, 3 if case == 'wrong_store' else 2, p.stdout + p.stderr)
            self.assertEqual(self.snapshot(), before)

    def test_producer_retains_and_yields(self):
        before = self.snapshot(self.repo)
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(result['state'], 'yielded')
        receipt = json.loads((self.root / 'yield.json').read_bytes())
        self.assertEqual(receipt['pm_yield'], {'task_status': 'todo', 'claim_state': 'absent'})
        current = self.pmc('show', self.task_id)['data']
        self.assertEqual((current['task']['status'], current['claim']['state']), ('todo', 'absent'))
        from orion_results import Reference, read, inspect_session
        ref = Reference.parse(receipt['result']['reference'])
        slot = self.root / 'results' / receipt['result']['slot']
        raw = (self.root / 'receipts' / receipt['producer_attempt_id'] / 'report.raw').read_bytes()
        self.assertEqual(read(slot, ref).encode('utf-8'), raw)
        self.assertEqual((ref.sha256, ref.utf8_bytes), (sha(raw), len(raw)))
        self.assertEqual(inspect_session(slot, ref.session_id).status, 'complete')
        self.assertEqual(receipt['observation']['exit'], 1)
        self.assertEqual(receipt['observation']['coverage'], 'complete')
        context = self.hc('show', receipt['context']['record_id'])['data']
        self.assertTrue(context['current'])
        self.assertEqual(context['sha256'], receipt['context']['sha256'])
        self.assertLessEqual(len(context['record']['body'].encode()), 4096)
        self.assertEqual(self.snapshot(self.repo), before)
        self.assertNotIn(str(self.root).encode(), p.stdout)

    def test_large_report_is_referenced_not_embedded(self):
        for tree in self.workers:
            for i in range(100):
                (tree / ('synthetic-observation-path-' + str(i).zfill(3) + '.txt')).write_text('owned fixture\n')
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        receipt = json.loads((self.root / 'yield.json').read_bytes())
        self.assertGreater(receipt['observation']['stdout_bytes'], 16384)
        from orion_results import read
        raw = read(self.root / 'results' / receipt['result']['slot'], receipt['result']['reference']).encode()
        self.assertEqual((len(raw), sha(raw)), (receipt['observation']['stdout_bytes'], receipt['observation']['stdout_sha256']))
        context = self.hc('show', receipt['context']['record_id'])['data']['record']
        self.assertLessEqual(len(context['body'].encode()), 4096)
        self.assertNotIn(b'synthetic-observation-path-', p.stdout)

    def test_separate_consumer_recovers_reobserves_and_completes(self):
        first = self.invoke('produce')
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        old = json.loads((self.root / 'yield.json').read_bytes())
        second = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        result = json.loads(second.stdout)
        self.assertEqual(result['state'], 'completed')
        self.assertNotEqual(result['outcomes']['task']['generation'], old['pm']['producer_generation'])
        self.assertNotEqual(result['outcomes']['capture']['reference'], old['result']['reference'])
        self.assertNotEqual(result['outcomes']['observation']['scan_id'], old['observation']['scan_id'])
        state = self.pmc('show', self.task_id)['data']
        self.assertEqual((state['task']['status'], state['claim']['state']), ('done', 'absent'))
        self.assertEqual(state['task']['evidence'][-1]['ref'], result['outcomes']['capture']['reference'])

    def test_historical_capture_survives_fixture_change(self):
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        receipt = json.loads((self.root / 'yield.json').read_bytes())
        from orion_results import read
        slot = self.root / 'results' / receipt['result']['slot']
        old = read(slot, receipt['result']['reference'])
        self.git('restore', 'shared.txt', cwd=self.workers[1])
        p = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        reply = json.loads(p.stdout)
        self.assertEqual(reply['reason'], 'fresh_observation_does_not_meet_goal')
        self.assertEqual(reply['outcomes']['observation']['conclusion'], 'no_overlap_observed')
        self.assertEqual(read(slot, receipt['result']['reference']), old)
        state = self.pmc('show', self.task_id)['data']
        self.assertEqual((state['task']['status'], state['claim']['state']), ('todo', 'absent'))

    def test_native_partial_positive_can_yield_but_not_complete(self):
        self.value['reporter']['repositories'].append(str(self.root / 'missing-repository'))
        self.write(self.selection, self.value)
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(result['outcomes']['observation']['coverage'], 'partial')
        self.assertEqual(result['outcomes']['observation']['conclusion'], 'overlap_observed')
        p = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(self.pmc('show', self.task_id)['data']['task']['status'], 'todo')

    def test_native_negative_partial_indeterminate_and_unavailable(self):
        # Each fresh fixture is a separate run, never a replay of a mutation.
        for index, case in enumerate(('negative', 'partial', 'unavailable')):
            with self.subTest(case=case):
                if index:
                    self.setUp()
                for tree in self.workers:
                    self.git('restore', 'shared.txt', cwd=tree)
                if case == 'partial':
                    self.value['reporter']['repositories'].append(str(self.root / 'missing'))
                elif case == 'unavailable':
                    self.value['reporter']['repositories'] = [str(self.root / 'missing')]
                self.write(self.selection, self.value)
                p = self.invoke('produce')
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                obs = json.loads(p.stdout)['outcomes']['observation']
                self.assertEqual((obs['coverage'], obs['exit']), {'negative': ('complete', 0),
                    'partial': ('partial', 3), 'unavailable': ('unavailable', 4)}[case])
                p = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
                self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
                self.assertEqual(self.pmc('show', self.task_id)['data']['task']['status'], 'todo')

    def test_odd_byte_paths_keep_exact_identity(self):
        names = [b'tab\tfile', b'new\nline', b'non-utf8-\xff']
        for tree in self.workers:
            for name in names:
                fd = os.open(os.fsencode(tree) + b'/' + name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.write(fd, b'synthetic fixture\n')
                os.close(fd)
        before = self.snapshot(self.repo)
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        receipt = json.loads((self.root / 'yield.json').read_bytes())
        raw = (self.root / 'receipts' / receipt['producer_attempt_id'] / 'report.raw').read_bytes()
        identities = {base64.b64decode(x['path']['path_b64']): x['path']['path_utf8'] for x in json.loads(raw)['overlaps']}
        for name in names:
            self.assertIn(name, identities)
        self.assertIsNone(identities[names[-1]])
        self.assertEqual(self.snapshot(self.repo), before)

    def test_invalid_report_processes_never_yield(self):
        for index, fault in enumerate(('malformed', 'oversize', 'signal', 'exit74', 'exit70', 'wrong_count', 'wrong_path_label', 'stderr_overflow')):
            with self.subTest(fault=fault):
                if index:
                    self.setUp()
                self.proxy('reporter', 'scan', fault)
                p = self.invoke('produce')
                self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
                self.assertFalse((self.root / 'yield.json').exists())
                self.assertIsNone(json.loads(p.stdout)['outcomes']['capture'])
                self.assertLessEqual(len(p.stdout), 65536)
                self.assertEqual(p.stderr, b'')

    def test_internal_error_retains_bounded_private_diagnostics(self):
        self.proxy('reporter', 'scan', 'exit70')
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        attempt = json.loads(p.stdout)['attempt_id']
        diagnostic = self.root / 'receipts' / attempt / 'diagnostic-report.raw'
        self.assertTrue(diagnostic.exists(), 'failed report evidence must be retained privately')
        self.assertLessEqual(diagnostic.stat().st_size, 1048576)
