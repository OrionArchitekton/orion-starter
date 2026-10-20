"""Public profile process seam over installed components and disposable Git data."""
import base64
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import time
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
        self.entry = ENTRY
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
        return subprocess.run([sys.executable, '-I', '-B', str(self.entry), mode, '--selection', str(self.selection),
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

    def helper_fault(self, command):
        target = self.root / 'profile-under-test'
        target.mkdir(mode=0o700)
        shutil.copyfile(ENTRY, target / 'run.py')
        helper = ROOT / 'profiles/development-evidence/results_io.py'
        (target / 'results_io.py').write_text(
            'import runpy,sys,os,json\n' +
            'namespace=runpy.run_path(' + repr(str(helper)) + ')\n' +
            'data=namespace["main"]()\n' +
            'if sys.argv[1]==' + repr(command) + ': os._exit(74)\n' +
            'print(json.dumps({"command":sys.argv[1],"state":"ok","data":data}))\n')
        self.entry = target / 'run.py'

    def storage_fault(self, output_name):
        target = self.root / 'profile-under-test'
        target.mkdir(mode=0o700)
        source = ENTRY.read_text()
        source = source.replace('    private_dir(path.parent)\n',
            '    if path.name == ' + repr(output_name) + ':\n        raise OSError("controlled persistence failure")\n    private_dir(path.parent)\n', 1)
        (target / 'run.py').write_text(source)
        shutil.copyfile(ROOT / 'profiles/development-evidence/results_io.py', target / 'results_io.py')
        self.entry = target / 'run.py'

    def quota_fault(self):
        target = self.root / 'profile-under-test'
        target.mkdir(mode=0o700)
        shutil.copyfile(ENTRY, target / 'run.py')
        helper = ROOT / 'profiles/development-evidence/results_io.py'
        (target / 'results_io.py').write_text(
            'import runpy,orion_results\noriginal=orion_results.Session.create\n'
            'def limited(root,*,limits):\n'
            '    return original(root,limits=orion_results.Limits(max_input_bytes=1048576,max_results=1,max_payload_bytes=1,inline_bytes=4000))\n'
            'orion_results.Session.create=staticmethod(limited)\n'
            'runpy.run_path(' + repr(str(helper)) + ',run_name="__main__")\n')
        self.entry = target / 'run.py'

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
        self.assertEqual(result['outcomes']['task']['state'], 'yielded')
        p = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        refused = json.loads(p.stdout)
        self.assertEqual(refused['outcomes']['task']['state'], 'released_unfinished')
        saved = json.loads((self.root / 'receipts' / refused['attempt_id'] / 'attempt.json').read_bytes())
        self.assertEqual(saved['outcomes']['task']['state'], 'released_unfinished')
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

    def test_unselected_repository_overlap_cannot_complete(self):
        # Two explicit roots can legitimately resolve to one common repository.
        self.value['reporter']['repositories'].append(str(self.workers[0]))
        self.write(self.selection, self.value)
        proxy = self.proxy('reporter', 'scan', None)
        produced = self.invoke('produce')
        self.assertEqual(produced.returncode, 0, produced.stdout + produced.stderr)
        receipt = json.loads((self.root / 'yield.json').read_bytes())
        report = json.loads((self.root / 'receipts' / receipt['producer_attempt_id'] / 'report.raw').read_bytes())
        self.assertEqual((len(report['inputs']), len(report['repositories'])), (2, 1))
        self.assertEqual(report['coverage']['repositories_selected'], 1)
        self.git('restore', 'shared.txt', cwd=self.workers[1])
        config_path = Path(str(proxy) + '.json')
        config = json.loads(config_path.read_bytes())
        config.update(fault='foreign_repository', overlap_template=report['overlaps'][0])
        self.write(config_path, config)
        consumed = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
        self.assertEqual(consumed.returncode, 7, consumed.stdout + consumed.stderr)
        reply = json.loads(consumed.stdout)
        self.assertEqual(reply['reason'], 'report_not_established')
        self.assertIsNone(reply['outcomes']['capture'])
        task = self.pmc('show', self.task_id)['data']['task']
        self.assertNotEqual(task['status'], 'done')
        self.assertEqual(task['evidence'], [])
        self.assertEqual(len(list((self.root / 'results').iterdir())), 1)
        diagnostic = json.loads((self.root / 'receipts' / reply['attempt_id'] / 'diagnostic-report.raw').read_bytes())
        self.assertEqual((len(diagnostic['inputs']), len(diagnostic['repositories'])), (2, 2))
        self.assertEqual(diagnostic['overlaps'][0]['repository_id'], 'sha256:' + 'f' * 64)

    def test_internal_error_retains_bounded_private_diagnostics(self):
        self.proxy('reporter', 'scan', 'exit70')
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        attempt = json.loads(p.stdout)['attempt_id']
        diagnostic = self.root / 'receipts' / attempt / 'diagnostic-report.raw'
        self.assertTrue(diagnostic.exists(), 'failed report evidence must be retained privately')
        self.assertLessEqual(diagnostic.stat().st_size, 1048576)

    def test_wrong_result_slot_refuses_before_claim(self):
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        receipt = json.loads((self.root / 'yield.json').read_bytes())
        receipt['result']['slot'] = str(uuid.uuid4())
        self.write(self.root / 'wrong.json', receipt)
        before = self.snapshot(self.root / 'pm')
        p = self.invoke('continue', '--yield-receipt', self.root / 'wrong.json')
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(self.snapshot(self.root / 'pm'), before)
        self.assertEqual(len(list((self.root / 'results').iterdir())), 1)

    def test_mismatched_receipts_never_claim(self):
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        original = json.loads((self.root / 'yield.json').read_bytes())
        before = self.snapshot(self.root / 'pm')
        cases = [('run_id', str(uuid.uuid4())), ('selection_sha256', '0'*64),
                 ('repositories_sha256', '0'*64), ('task_id', 'different'), ('store_id', '0'*32),
                 ('task_definition_sha256', '0'*64), ('stdout_bytes', 1), ('sha256', '0'*64)]
        for key, value in cases:
            with self.subTest(key=key):
                receipt = json.loads(canonical(original))
                target = receipt['pm'] if key in original['pm'] else receipt['observation'] if key == 'stdout_bytes' else receipt['context'] if key == 'sha256' else receipt
                target[key] = value
                self.write(self.root / 'wrong.json', receipt)
                p = self.invoke('continue', '--yield-receipt', self.root / 'wrong.json')
                self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
                self.assertEqual(self.snapshot(self.root / 'pm'), before)

    def test_missing_capture_and_replaced_context_never_claim(self):
        for index, case in enumerate(('capture_missing', 'superseded', 'done', 'stale', 'future', 'no_acceptance')):
            with self.subTest(case=case):
                if index:
                    self.setUp()
                p = self.invoke('produce')
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                receipt = json.loads((self.root / 'yield.json').read_bytes())
                if case == 'capture_missing':
                    shutil.rmtree(self.root / 'results' / receipt['result']['slot'])
                else:
                    row = self.hc('show', receipt['context']['record_id'])['data']['record']
                    row.pop('created_at')
                    row['predecessor'] = row.pop('record_id')
                    row['request_id'] = uuid.uuid4().hex
                    if case == 'done':
                        row['status'] = 'done'
                    elif case in ('stale', 'future'):
                        row['context_as_of'] = '2000-01-01T00:00:00Z' if case == 'stale' else '2099-01-01T00:00:00Z'
                    elif case == 'no_acceptance':
                        row['acceptance_claims'] = []
                    self.hc('record', '--input', '-', input=canonical(row))
                before = self.snapshot(self.root / 'pm')
                p = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
                self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
                self.assertEqual(self.snapshot(self.root / 'pm'), before)

    def test_two_consumers_one_claim(self):
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        argv = [sys.executable, '-I', '-B', str(ENTRY), 'continue', '--selection', str(self.selection),
                '--yield-receipt', str(self.root / 'yield.json')]
        workers = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        replies = [p.communicate(timeout=100) for p in workers]
        self.assertEqual(sorted(p.returncode for p in workers), [0, 3], replies)
        self.assertEqual(len(list((self.root / 'results').iterdir())), 2)
        self.assertEqual(self.pmc('show', self.task_id)['data']['task']['status'], 'done')

    def test_context_change_after_attachment_stops_completion(self):
        proxy = self.proxy('pm', 'evidence', None)
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        config = json.loads(Path(str(proxy) + '.json').read_bytes())
        config.update(fault='change_context', pm_home=str(self.root / 'pm'), pm_executable=str(self.pm),
                      task_id=self.task_id, yield_path=str(self.root / 'yield.json'),
                      handoff_executable=str(self.handoff), handoff_store=str(self.root / 'handoff'))
        self.write(Path(str(proxy) + '.json'), config)
        p = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        state = self.pmc('show', self.task_id)['data']
        self.assertNotEqual(state['task']['status'], 'done')
        self.assertEqual(len(state['task']['evidence']), 1)

    def test_context_change_before_capture_stops_results_mutation(self):
        proxy = self.proxy('reporter', 'scan', None)
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        config = json.loads(Path(str(proxy) + '.json').read_bytes())
        config.update(fault='change_context', pm_home=str(self.root / 'pm'), pm_executable=str(self.pm),
                      task_id=self.task_id, yield_path=str(self.root / 'yield.json'),
                      handoff_executable=str(self.handoff), handoff_store=str(self.root / 'handoff'))
        self.write(Path(str(proxy) + '.json'), config)
        p = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(len(list((self.root / 'results').iterdir())), 1,
                         'changed context must stop before creating a fresh Results slot')

    def test_lost_session_create_response_stays_unknown(self):
        self.helper_fault('create')
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        reply = json.loads(p.stdout)
        capture = reply['outcomes']['capture']
        self.assertEqual(capture['state'], 'session_creation_unknown')
        self.assertNotIn('session_id', capture)
        self.assertNotIn('reference', capture)
        self.assertFalse((self.root / 'yield.json').exists())
        self.entry = ENTRY
        attempt = self.root / 'receipts' / reply['attempt_id'] / 'attempt.json'
        before = self.snapshot()
        p = self.invoke('reconcile', '--attempt-receipt', attempt)
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)['outcomes']['capture']['state'], 'session_creation_unknown')
        self.assertEqual(self.snapshot(), before)

    def test_unknown_capture_reads_known_reference_without_recapture(self):
        self.helper_fault('capture')
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        reply = json.loads(p.stdout)
        self.assertEqual(reply['outcomes']['capture']['state'], 'capture_unknown')
        self.entry = ENTRY
        attempt = self.root / 'receipts' / reply['attempt_id'] / 'attempt.json'
        before = self.snapshot()
        p = self.invoke('reconcile', '--attempt-receipt', attempt)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(result['state'], 'reconciled')
        self.assertEqual(result['outcomes']['capture']['recovery'], 'exact_bytes_observed')
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / 'yield.json').exists())

    def test_lost_component_responses_are_observed_without_replay(self):
        cases = [('pm', 'claim', 'produce'), ('handoff', 'record', 'produce'), ('pm', 'release', 'produce'),
                 ('pm', 'evidence', 'continue'), ('pm', 'transition', 'continue')]
        for index, (component, command, mode) in enumerate(cases):
            with self.subTest(component=component, command=command):
                if index:
                    self.setUp()
                proxy = self.proxy(component, command, None)
                if mode == 'continue':
                    p = self.invoke('produce')
                    self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                config = json.loads(Path(str(proxy) + '.json').read_bytes())
                config['fault'] = 'lose_response'
                self.write(Path(str(proxy) + '.json'), config)
                extra = ('--yield-receipt', self.root / 'yield.json') if mode == 'continue' else ()
                p = self.invoke(mode, *extra)
                self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
                reply = json.loads(p.stdout)
                self.assertEqual(reply['state'], 'reconciliation_required')
                attempt = self.root / 'receipts' / reply['attempt_id'] / 'attempt.json'
                before = {k: self.snapshot(self.root / k) for k in ('pm', 'handoff', 'results', 'receipts')}
                p = self.invoke('reconcile', '--attempt-receipt', attempt)
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                self.assertEqual(json.loads(p.stdout)['original_attempt_resumed'], False)
                self.assertEqual({k: self.snapshot(self.root / k) for k in before}, before)
                self.assertFalse(any((self.root / 'receipts').glob('*/completed.json')))

    def test_failed_intent_launches_no_claim(self):
        self.storage_fault('operation-01.json')
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        data = self.pmc('show', self.task_id)['data']
        self.assertEqual((data['task']['status'], data['claim']['state']), ('todo', 'absent'))
        self.assertFalse((self.root / 'yield.json').exists())
        self.assertEqual(list((self.root / 'results').iterdir()), [])

    def test_malformed_pm_success_stays_unknown_without_established_effect(self):
        for index, (command, mode) in enumerate((('claim', 'produce'), ('release', 'produce'),
                                                  ('evidence', 'continue'), ('transition', 'continue'))):
            with self.subTest(command=command):
                if index:
                    self.setUp()
                proxy = self.proxy('pm', command, None)
                if mode == 'continue':
                    produced = self.invoke('produce')
                    self.assertEqual(produced.returncode, 0, produced.stdout + produced.stderr)
                config_path = Path(str(proxy) + '.json')
                config = json.loads(config_path.read_bytes())
                config['fault'] = 'malformed'
                self.write(config_path, config)
                extra = ('--yield-receipt', self.root / 'yield.json') if mode == 'continue' else ()
                failed = self.invoke(mode, *extra)
                self.assertEqual(failed.returncode, 7, failed.stdout + failed.stderr)
                attempt = self.root / 'receipts' / json.loads(failed.stdout)['attempt_id'] / 'attempt.json'
                before = {k: self.snapshot(self.root / k) for k in ('pm', 'handoff', 'results', 'receipts')}
                reconciled = self.invoke('reconcile', '--attempt-receipt', attempt)
                self.assertEqual(reconciled.returncode, 7, reconciled.stdout + reconciled.stderr)
                reply = json.loads(reconciled.stdout)
                self.assertEqual((reply['state'], reply['reason']), ('reconciliation_required', 'unresolved_operation'))
                self.assertFalse(reply['original_attempt_resumed'])
                self.assertEqual({k: self.snapshot(self.root / k) for k in before}, before)
                calls = [json.loads(line) for line in (self.root / 'calls.jsonl').read_text().splitlines()]
                self.assertEqual(calls.count(['pm', command]), 1, 'reconcile must never repeat the mutation')

    def test_final_yield_persistence_failure_is_not_success(self):
        self.storage_fault('yield.json')
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        self.assertFalse((self.root / 'yield.json').exists())
        data = self.pmc('show', self.task_id)['data']
        self.assertEqual((data['task']['status'], data['claim']['state']), ('todo', 'absent'))

    def test_successor_after_claim_or_scan_cannot_be_released(self):
        for index, (component, command) in enumerate((('pm', 'claim'), ('reporter', 'scan'))):
            with self.subTest(at=command):
                if index:
                    self.setUp()
                proxy = self.proxy(component, command, None)
                p = self.invoke('produce')
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                config = json.loads(Path(str(proxy) + '.json').read_bytes())
                config.update(fault='replace_claim', pm_home=str(self.root / 'pm'), pm_executable=str(self.pm), task_id=self.task_id)
                self.write(Path(str(proxy) + '.json'), config)
                p = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
                self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
                self.assertEqual(self.pmc('show', self.task_id)['data']['claim']['holder'], 'successor')
                self.assertEqual(len(list((self.root / 'results').iterdir())), 1)

    def test_timed_out_owned_group_is_stopped_after_parent_exits(self):
        # A narrow supporting test of the profile's own process seam, not a fake component proof.
        import importlib.util
        spec = importlib.util.spec_from_file_location('profile_process', ENTRY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        marker = self.root / 'child.pid'
        code = ('import subprocess,sys; from pathlib import Path; '
                'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
                'Path(sys.argv[1]).write_text(str(p.pid))')
        with self.assertRaises(module.Stop):
            module.process([sys.executable, '-I', '-c', code, str(marker)],
                           {'PATH': '/usr/bin:/bin'}, 65536, time.monotonic()+0.5)
        pid = int(marker.read_text())
        try:
            # Zombies have stopped executing and need their init owner to reap them.
            status = Path('/proc') / str(pid) / 'stat'
            self.assertTrue(not status.exists() or status.read_text().split(') ')[1][0] in ('Z', 'X'), 'owned child still runs')
        finally:
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass

    def test_two_roots_of_same_repository_are_one_native_repository(self):
        self.value['reporter']['repositories'].append(str(self.workers[0]))
        self.write(self.selection, self.value)
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)['outcomes']['observation']['coverage'], 'complete')

    def test_nonregular_selection_is_refused_without_blocking(self):
        self.selection.unlink()
        os.mkfifo(self.selection, 0o600)
        p = subprocess.run([sys.executable, '-I', '-B', str(ENTRY), 'inspect', '--selection', str(self.selection)],
                           capture_output=True, timeout=1)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)

    def test_boolean_store_version_cannot_pass_preflight(self):
        self.proxy('pm', 'version', 'boolean_store_format')
        p = self.invoke('inspect')
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertFalse((self.root / 'receipts').exists())

    def test_unsupported_capability_refuses_without_claim(self):
        self.proxy('pm', 'version', 'missing_capability')
        p = self.invoke('inspect')
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(self.pmc('show', self.task_id)['data']['claim']['state'], 'absent')

    def test_invalid_arguments_are_payload_free_json(self):
        p = subprocess.run([sys.executable, '-I', '-B', str(ENTRY), 'inspect'], capture_output=True, timeout=5)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertEqual(p.stderr, b'')
        result = json.loads(p.stdout)
        self.assertEqual(result['state'], 'invalid')
        self.assertIn('outcomes', result)

    def test_closed_output_pipe_does_not_claim_delivery(self):
        p = subprocess.Popen([sys.executable, '-I', '-B', str(ENTRY), 'produce', '--selection', str(self.selection)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.stdout.close()
        err = p.stderr.read()
        p.stderr.close()
        code = p.wait(timeout=100)
        self.assertEqual(code, 7, err)
        self.assertEqual(err, b'')

    def test_native_lower_quota_is_known_not_stored(self):
        self.quota_fault()
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        capture = json.loads(p.stdout)['outcomes']['capture']
        self.assertEqual(capture['state'], 'not_stored')
        self.assertEqual(capture['native_code'], 'limit_exceeded')
        from orion_results import inspect_session
        inspection = inspect_session(self.root / 'results' / capture['slot'], capture['session_id'])
        self.assertEqual(inspection.references, ())
        self.assertFalse((self.root / 'yield.json').exists())

    def test_lost_readback_response_never_yields(self):
        self.helper_fault('read')
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)['outcomes']['capture']['state'], 'capture_unknown')
        self.assertFalse((self.root / 'yield.json').exists())

    def test_existing_attempt_is_never_adopted_on_creation_failure(self):
        collision = str(uuid.uuid4())
        parent = self.root / 'receipts'
        parent.mkdir(mode=0o700)
        old = parent / collision
        old.mkdir(mode=0o700)
        self.write(old / 'attempt.json', {'unrelated': 'preserve this attempt'})
        target = self.root / 'profile-under-test'
        target.mkdir(mode=0o700)
        (target / 'run.py').write_text(ENTRY.read_text().replace('self.attempt = str(uuid.uuid4())', 'self.attempt = ' + repr(collision)))
        shutil.copyfile(ROOT / 'profiles/development-evidence/results_io.py', target / 'results_io.py')
        self.entry = target / 'run.py'
        before = self.snapshot(parent)
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        self.assertEqual(self.snapshot(parent), before)
        self.assertEqual(self.pmc('show', self.task_id)['data']['claim']['state'], 'absent')

    def test_corrupt_capture_refuses_before_claim(self):
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        receipt = json.loads((self.root / 'yield.json').read_bytes())
        slot = self.root / 'results' / receipt['result']['slot']
        databases = [x for x in slot.rglob('*') if x.is_file() and x.read_bytes()[:16] == b'SQLite format 3\x00']
        self.assertEqual(len(databases), 1)
        with databases[0].open('r+b') as f:
            f.write(b'controlled corrupt fixture bytes')
        before = self.snapshot(self.root / 'pm')
        p = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        self.assertEqual(self.snapshot(self.root / 'pm'), before)

    def test_close_failure_never_yields_a_capture_receipt(self):
        target = self.root / 'profile-under-test'
        target.mkdir(mode=0o700)
        shutil.copyfile(ENTRY, target / 'run.py')
        helper = ROOT / 'profiles/development-evidence/results_io.py'
        (target / 'results_io.py').write_text(
            'import runpy,sys\nfrom orion_results import Session\n'
            'if sys.argv[1]=="capture":\n'
            '    original=Session.close\n'
            '    def fail_close(self):\n        original(self)\n        raise OSError("controlled close failure")\n'
            '    Session.close=fail_close\n'
            'runpy.run_path(' + repr(str(helper)) + ',run_name="__main__")\n')
        self.entry = target / 'run.py'
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)['outcomes']['capture']['state'], 'capture_unknown')
        self.assertFalse((self.root / 'yield.json').exists())

    def test_final_completion_receipt_failure_preserves_actual_done_state(self):
        self.storage_fault('completed.json')
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        p = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)['state'], 'reconciliation_required')
        self.assertEqual(self.pmc('show', self.task_id)['data']['task']['status'], 'done')
        self.assertFalse(any((self.root / 'receipts').glob('*/completed.json')))
