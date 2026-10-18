"""Exercise the example as a process over installed PM/Handoff commands."""
import hashlib
import json
import os
from pathlib import Path
import re
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

    def proxy(self, kind):
        config = self.root / 'proxy.json'
        values = json.loads(config.read_text()) if config.exists() else {}
        values[kind] = self.value[kind]['executable']
        self.write(config, values)
        path = self.root / (kind + '-proxy')
        path.write_text('#!' + sys.executable + '\n' + (ROOT / 'tests/fixtures/component_cli.py').read_text())
        path.chmod(0o700)
        self.value[kind]['executable'] = str(path)
        self.write(self.selection, self.value)

    def test_inspect_selected_installed_stores_without_mutations(self):
        self.assertTrue(EXAMPLE.is_file(), 'continuity example not implemented')
        before = self.snapshot()
        p = self.invoke('inspect')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(result['state'], 'inspected')
        self.assertEqual(result['run_id'], self.value['run_id'])
        self.assertEqual(self.snapshot(), before)

    def test_documented_setup_guards_survive_optimized_python(self):
        recipe = (ROOT / 'profiles/continuity/README.md').read_text()
        setup = re.search(r"<<'PY'\n(.*?)\nPY", recipe, re.S).group(1)
        candidate = self.root / 'recipe'
        (candidate / '.venv').mkdir(parents=True)
        (candidate / '.venv/bin').symlink_to(self.bin, target_is_directory=True)
        cases = [('workspace_not_empty', '84', True, {}), ('screen_range', '9', False, {}),
                 ('inherited_browser_override', '84', False, {'ORION_BROWSER_CONFIG':'/tmp/unselected-example.toml'})]
        for reason, screen, nonempty, overrides in cases:
            with self.subTest(reason=reason):
                workspace = self.root / reason
                workspace.mkdir(mode=0o700)
                if nonempty:
                    (workspace / 'sentinel').write_text('Unrelated selected data')
                before = {p.name:p.read_bytes() for p in workspace.iterdir()}
                env = {k:v for k,v in os.environ.items() if not k.startswith(('ORION_BROWSER_', 'AGENT_BROWSER_'))}
                env.update(DEMO_ROOT=str(workspace), DEMO_SCREEN=screen, **overrides)
                p = subprocess.run([sys.executable, '-O', '-c', setup], cwd=candidate, env=env,
                                   capture_output=True, text=True, timeout=15)
                self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
                self.assertIn(reason, p.stderr)
                self.assertEqual({p.name:p.read_bytes() for p in workspace.iterdir()}, before)

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

    def test_busy_browser_after_task_claim_requires_reconciliation(self):
        subprocess.run([str(self.fake), '--json', 'lease', 'contdemo', '--holder', 'other-worker'],
                       check=True, capture_output=True)
        p = self.invoke('produce')
        result = json.loads(p.stdout)
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        self.assertEqual(result['state'], 'reconciliation_required')
        self.assertEqual(result['reason'], 'resource_not_free')
        current = self.pmc('show', 'continuity-demo')['data']
        self.assertEqual(current['claim']['holder'], result['outcomes']['pm']['holder'])
        self.assertEqual(current['claim']['state'], 'live')
        self.assertEqual(json.loads((self.root / 'fake-browser.json').read_text())['holder'], 'other-worker')
        calls = [json.loads(x) for x in (self.root / 'calls.jsonl').read_text().splitlines()]
        self.assertEqual(calls.count(['browser', 'lease']), 1)
        self.assertNotIn(['client', 'batch'], calls)
        self.assertFalse((self.root / 'yield.json').exists())

    def test_consumer_observes_again_with_fresh_handles_before_done(self):
        first = self.invoke('produce')
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        producer = json.loads(first.stdout)
        second = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        consumer = json.loads(second.stdout)
        self.assertEqual(consumer['state'], 'completed')
        self.assertNotEqual(producer['outcomes']['pm']['generation'], consumer['outcomes']['pm']['generation'])
        self.assertNotEqual(producer['outcomes']['browser']['session'], consumer['outcomes']['browser']['session'])
        current = self.pmc('show', 'continuity-demo')['data']
        self.assertEqual(current['task']['status'], 'done')
        self.assertEqual(current['claim']['state'], 'absent')
        self.assertEqual(len(current['task']['evidence']), 1)
        calls = [json.loads(x) for x in (self.root / 'calls.jsonl').read_text().splitlines()]
        self.assertEqual(calls.count(['client', 'batch']), 2)

    def test_overlapping_component_state_is_refused_before_claim(self):
        self.config.write_text(self.config.read_text().replace(str(self.root / 'browser-state'), str(self.root / 'pm')))
        self.value['browser']['config_sha256'] = digest(self.config)
        self.write(self.selection, self.value)
        p = self.invoke('inspect')
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertEqual(self.pmc('show', 'continuity-demo')['data']['claim']['state'], 'absent')
        self.assertFalse((self.root / 'calls.jsonl').exists())

    def test_invalid_context_variants_cannot_claim_or_browse(self):
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        receipt = json.loads((self.root / 'yield.json').read_text())
        argv = [str(self.handoff), '--json', '--store', str(self.root / 'handoff')]
        old = json.loads(subprocess.check_output([*argv, 'show', receipt['record_id']]))['data']['record']
        base = {k: v for k, v in old.items() if k not in ('record_id', 'created_at')}
        calls = (self.root / 'calls.jsonl').read_bytes()
        changes = [{'status': 'stale'}, {'status': 'done'}, {'context_as_of': '2000-01-01T00:00:00Z'},
                   {'context_as_of': '2999-01-01T00:00:00Z'}, {'evidence': []},
                   {'acceptance_claims': []}, {'body': '{}'}, {'recorded_next_step': None}]
        for update in changes:
            with self.subTest(update=update):
                value = {**base, **update, 'predecessor': receipt['record_id']}
                p = subprocess.run([*argv, 'record', '--input', '-'], input=json.dumps(value),
                                   capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stdout)
                data = json.loads(p.stdout)['data']
                receipt.update(record_id=data['record_id'], record_sha256=data['sha256'])
                self.write(self.root / 'selected-yield.json', receipt)
                p = self.invoke('continue', '--yield-receipt', self.root / 'selected-yield.json')
                self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
                self.assertEqual((self.root / 'calls.jsonl').read_bytes(), calls)
                current = self.pmc('show', 'continuity-demo')['data']
                self.assertEqual(current['task']['status'], 'todo')
                self.assertEqual(current['claim']['state'], 'absent')

    def test_claim_lost_during_browser_preflight_cannot_acquire_resource(self):
        self.write(self.root / 'faults.json', {'browser:status': 'lose_claim'})
        p = self.invoke('produce')
        self.assertNotEqual(p.returncode, 0)
        calls = [json.loads(x) for x in (self.root / 'calls.jsonl').read_text().splitlines()]
        self.assertNotIn(['browser', 'lease'], calls)
        self.assertEqual(self.pmc('show', 'continuity-demo')['data']['claim']['holder'], 'replacement')

    def test_two_consumers_have_one_winner_and_only_one_browser_read(self):
        first = self.invoke('produce')
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        argv = [sys.executable, str(EXAMPLE), '--selection', str(self.selection), 'continue',
                '--yield-receipt', str(self.root / 'yield.json')]
        workers = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        replies = [p.communicate(timeout=30) for p in workers]
        self.assertEqual(sorted(p.returncode for p in workers), [0, 3], replies)
        states = sorted(json.loads(reply[0])['state'] for reply in replies)
        self.assertEqual(states, ['completed', 'refused'])
        calls = [json.loads(x) for x in (self.root / 'calls.jsonl').read_text().splitlines()]
        self.assertEqual(calls.count(['client', 'batch']), 2)
        self.assertEqual(calls.count(['browser', 'lease']), 2)

    def test_boolean_api_version_is_not_integer_version_one(self):
        self.proxy('pm')
        self.write(self.root / 'faults.json', {'pm:version': 'boolean_api'})
        p = self.invoke('inspect')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)['state'], 'reconciliation_required')

    def test_malformed_context_count_cannot_claim_or_browse(self):
        for index, fault in enumerate(('boolean_total', 'float_total', 'negative_total', 'missing_total')):
            with self.subTest(fault=fault):
                if index:
                    self.setUp()
                self.proxy('handoff')
                self.write(self.root / 'faults.json', {'handoff:list': fault})
                p = self.invoke('produce')
                self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
                self.assertEqual(json.loads(p.stdout)['reason'], 'handoff_list_shape')
                self.assertEqual(self.pmc('show', 'continuity-demo')['data']['claim']['state'], 'absent')
                self.assertFalse((self.root / 'calls.jsonl').exists())

    def test_unbounded_timing_configuration_is_refused_during_inspection(self):
        self.config.write_text('[timing]\nstart_limit_seconds = 999999999999\n' + self.config.read_text())
        self.value['browser']['config_sha256'] = digest(self.config)
        self.write(self.selection, self.value)
        p = self.invoke('inspect')
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)

    def test_corrupt_nested_component_data_is_unknown_without_traceback(self):
        self.proxy('pm')
        self.write(self.root / 'faults.json', {'pm:show': 'bad_task'})
        p = self.invoke('inspect')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        self.assertEqual(p.stderr, '')
        self.assertEqual(json.loads(p.stdout)['state'], 'reconciliation_required')

    def test_producer_interruptions_do_not_replay_or_claim_yield(self):
        points = ['pm:claim', 'browser:lease', 'client:connect', 'client:batch', 'browser:release',
                  'client:close', 'handoff:record', 'pm:release']
        for index, (point, moment) in enumerate((p, m) for p in points for m in ('before', 'after')):
            with self.subTest(point=point, moment=moment):
                if index:
                    self.setUp()
                self.proxy('pm')
                self.proxy('handoff')
                self.write(self.root / 'faults.json', {point: moment})
                p = self.invoke('produce')
                self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
                self.assertEqual(json.loads(p.stdout)['state'], 'reconciliation_required')
                self.assertEqual(p.stderr, '')
                self.assertFalse((self.root / 'yield.json').exists())
                key = point.split(':')
                calls = []
                for file in ('calls.jsonl', 'proxy-calls.jsonl'):
                    if (self.root / file).exists():
                        calls += [json.loads(x) for x in (self.root / file).read_text().splitlines()]
                self.assertEqual(calls.count(key), 1)

    def test_consumer_commit_interruptions_are_not_false_completion(self):
        points = ['pm:claim', 'pm:evidence:attach', 'pm:transition']
        for index, (point, moment) in enumerate((p, m) for p in points for m in ('before', 'after')):
            with self.subTest(point=point, moment=moment):
                if index:
                    self.setUp()
                p = self.invoke('produce')
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                self.proxy('pm')
                self.write(self.root / 'faults.json', {point: moment})
                p = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
                self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
                self.assertEqual(json.loads(p.stdout)['state'], 'reconciliation_required')
                calls = [json.loads(x) for x in (self.root / 'proxy-calls.jsonl').read_text().splitlines()]
                self.assertEqual(calls.count(['pm', point[3:]]), 1)
                current = self.pmc('show', 'continuity-demo')['data']
                self.assertEqual(current['task']['status'], 'done' if point == 'pm:transition' and moment == 'after'
                                 else 'todo' if point == 'pm:claim' and moment == 'before' else 'in_progress')

    def test_receipt_storage_failure_stops_forward_work(self):
        for index, fault in enumerate(('readonly_log', 'fill_log')):
            with self.subTest(fault=fault):
                if index:
                    self.setUp()
                self.write(self.root / 'faults.json', {'client:batch': fault})
                p = self.invoke('produce')
                self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
                self.assertEqual(json.loads(p.stdout)['state'], 'reconciliation_required')
                self.assertFalse((self.root / 'yield.json').exists())
                calls = [json.loads(x) for x in (self.root / 'calls.jsonl').read_text().splitlines()]
                self.assertNotIn(['browser', 'release'], calls)
                for directory in (self.root / 'receipts').iterdir():
                    directory.chmod(0o700)

    def test_explicit_reconciliation_then_new_attempt_can_finish(self):
        self.write(self.root / 'faults.json', {'client:batch': 'after'})
        failed = self.invoke('produce')
        self.assertEqual(failed.returncode, 7, failed.stdout + failed.stderr)
        current = self.pmc('show', 'continuity-demo')['data']
        holder = current['claim']['holder']
        subprocess.run([str(self.fake), '--json', 'release', 'contdemo', '--holder', holder],
                       check=True, capture_output=True)
        self.pmc('release', 'continuity-demo', '--holder', holder, '--generation', current['claim']['generation'],
                 '--expect-revision', current['task']['revision'])
        self.write(self.root / 'faults.json', {})
        repaired = self.invoke('produce')
        self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
        self.assertNotEqual(json.loads(failed.stdout)['attempt_id'], json.loads(repaired.stdout)['attempt_id'])
        done = self.invoke('continue', '--yield-receipt', self.root / 'yield.json')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_oversized_version_output_is_bounded_and_not_echoed(self):
        self.fake.write_text('#!' + sys.executable + '\nprint("x" * 600000)\n')
        p = self.invoke('inspect')
        self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
        self.assertLess(len(p.stdout), 65536)
        self.assertEqual(json.loads(p.stdout)['reason'], 'output_limit')
        self.assertEqual(p.stderr, '')

    def test_lost_result_pipe_exits_unknown_without_traceback(self):
        p = subprocess.Popen([sys.executable, str(EXAMPLE), '--selection', str(self.selection), 'inspect'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.stdout.close()
        error = p.stderr.read()
        p.stderr.close()
        self.assertEqual(p.wait(timeout=20), 7, error)
        self.assertEqual(error, b'')

    def test_corrupt_record_digest_cannot_expand_public_output(self):
        self.proxy('handoff')
        self.write(self.root / 'faults.json', {'handoff:record': 'huge_digest', 'handoff:show': 'huge_digest'})
        p = self.invoke('produce')
        self.assertEqual(p.returncode, 7)
        self.assertLess(len(p.stdout.encode()), 65536)
        self.assertEqual(json.loads(p.stdout)['state'], 'reconciliation_required')


if __name__ == '__main__':
    unittest.main()
