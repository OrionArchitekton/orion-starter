"""Manually selected, local development evidence demonstration. No ambient state."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

PROFILE = 'development-evidence'
TITLE = 'Demonstrate exact worktree evidence continuation'
LIMITS = {'max_input_bytes': 1048576, 'max_results': 1, 'max_payload_bytes': 1048576, 'inline_bytes': 4000}
VERSIONS = {'orion-pm': '0.1.1', 'orion-handoff': '0.1.0', 'orion-results': '0.1.0', 'orion-worktree-report': '0.1.0'}
HELPER = Path(__file__).with_name('results_io.py')


class Stop(Exception):
    def __init__(self, reason, code=7):
        self.reason, self.code = reason, code


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # Parser diagnostics must not echo caller payloads or paths.
        raise Stop('invalid_arguments', 2)


def need(condition, reason, code=7):
    if not condition:
        raise Stop(reason, code)


def wire(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def utc(value):
    need(isinstance(value, str) and len(value) <= 40, 'invalid_time')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(result.tzinfo is not None and result.utcoffset().total_seconds() == 0, 'invalid_time')
    return result


def uid(value):
    need(isinstance(value, str), 'invalid_uuid', 2)
    parsed = uuid.UUID(value)
    need(parsed.version == 4 and str(parsed) == value, 'invalid_uuid', 2)
    return value


def keys(value, names):
    need(isinstance(value, dict) and set(value) == set(names.split()), 'invalid_shape', 2)


def strict(raw, limit=65536):
    need(len(raw) <= limit, 'json_limit')
    # Bound nesting before decoding so deeply nested untrusted JSON is never allocated.
    depth = 0
    quoted = escaped = False
    for c in raw:
        if quoted:
            if escaped:
                escaped = False
            elif c == 92:
                escaped = True
            elif c == 34:
                quoted = False
        elif c == 34:
            quoted = True
        elif c in (91, 123):
            depth += 1
            need(depth <= 16, 'json_depth')
        elif c in (93, 125):
            depth -= 1
    def pairs(items):
        out = {}
        for k, v in items:
            need(k not in out, 'duplicate_json_key')
            out[k] = v
        return out
    def bad(_):
        raise Stop('nonfinite_json')
    return json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=pairs, parse_constant=bad)


def absolute(value):
    need(isinstance(value, str) and '\x00' not in value and len(value.encode('utf-8')) <= 4096, 'invalid_path', 2)
    p = Path(value)
    need(p.is_absolute() and '..' not in p.parts and str(p) == value, 'invalid_path', 2)
    return p


def no_links(path):
    for part in (*reversed(path.parents), path):
        need(not part.is_symlink(), 'symlink_path', 2)


def private_dir(path):
    no_links(path)
    s = path.stat()
    need(stat.S_ISDIR(s.st_mode) and s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == 0o700,
         'non_private_directory', 2)


def read_private(path, root, limit=65536):
    need(root in path.parents, 'outside_workspace', 2)
    no_links(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno())
        need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == os.getuid()
             and stat.S_IMODE(s.st_mode) == 0o600 and s.st_size <= limit, 'non_private_file', 2)
        raw = f.read(limit + 1)
    need(len(raw) <= limit, 'file_limit')
    return raw


def definition(task):
    return sha(wire({k: task.get(k) for k in ('id', 'project', 'title', 'description', 'next_action')}))


def durable(path, raw, replace=False):
    """Private same-directory atomic replacement; directory and bytes are synced."""
    private_dir(path.parent)
    if path.exists():
        need(replace, 'existing_output', 3)
        read_private(path, path.parent.parent, 1048576)
    temp = path.with_name('.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        if replace:
            os.replace(temp, path)
        else:
            os.link(temp, path, follow_symlinks=False)
            temp.unlink()
        d = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(d)
        finally:
            os.close(d)
    finally:
        if temp.exists():
            temp.unlink()


def selected(path):
    no_links(path)
    raw = read_private(path, path.parent)
    try:
        s = strict(raw)
    except (Stop, ValueError, UnicodeError):
        raise Stop('invalid_selection', 2) from None
    keys(s, 'selection_version profile goal run_id workspace pm handoff results reporter')
    need(type(s['selection_version']) is int and s['selection_version'] == 1 and s['profile'] == PROFILE
         and s['goal'] == 'capture-and-reobserve-overlap', 'unsupported_selection', 2)
    uid(s['run_id'])
    root = absolute(s['workspace'])
    private_dir(root)
    read_private(path, root)
    need(not any((p / '.git').exists() for p in (root, *root.parents)), 'workspace_in_git', 2)
    keys(s['pm'], 'executable home store_id task_id task_definition_sha256')
    keys(s['handoff'], 'executable store')
    keys(s['results'], 'root limits')
    keys(s['reporter'], 'executable repositories')
    need(wire(s['results']['limits']) == wire(LIMITS), 'unsupported_limits', 2)
    for key, pattern in [('store_id', '[0-9a-f]{32}'), ('task_definition_sha256', '[0-9a-f]{64}'),
                         ('task_id', '[A-Za-z0-9][A-Za-z0-9._-]{0,127}')]:
        need(isinstance(s['pm'][key], str) and re.fullmatch(pattern, s['pm'][key]), 'invalid_identity', 2)
    paths = [absolute(s['pm']['home']), absolute(s['handoff']['store']), absolute(s['results']['root']), root / 'receipts']
    for p in paths:
        need(root in p.parents, 'state_outside_workspace', 2)
        no_links(p)
        if p.exists():
            private_dir(p)
            need(not (p / '.git').exists(), 'state_in_git', 2)
    for i, p in enumerate(paths):
        need(all(p != q and p not in q.parents and q not in p.parents for q in paths[i+1:]), 'state_overlap', 2)
    for component in ('pm', 'handoff', 'reporter'):
        p = absolute(s[component]['executable'])
        need(p.is_file() and os.access(p, os.X_OK), 'missing_executable', 2)
    repos = s['reporter']['repositories']
    need(isinstance(repos, list) and 1 <= len(repos) <= 8, 'invalid_repositories', 2)
    for value in repos:
        p = absolute(value)
        need(all(p != x and p not in x.parents for x in paths), 'state_in_repository', 2)
    need(len(set(repos)) == len(repos), 'duplicate_repositories', 2)
    return s


def live_owned_group(group):
    """Observe only members of this invocation's new process group and session."""
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / 'stat').read_text().rsplit(') ', 1)[1].split()
            if int(fields[2]) == group and int(fields[3]) == group and fields[0] not in ('Z', 'X'):
                return True
        except (FileNotFoundError, ProcessLookupError):
            continue
    return False


def stop_owned_group(p):
    # A parent can exit while a descendant retains its pipes. Parent exit alone
    # never proves that this invocation's owned group has stopped.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(p.pid, sig)
        except ProcessLookupError:
            pass
        until = time.monotonic() + 5
        while time.monotonic() < until:
            p.poll()
            if not live_owned_group(p.pid):
                p.wait(timeout=max(0.001, until-time.monotonic()))
                return
            time.sleep(0.01)
    raise Stop('process_stop_unknown')


def process(argv, env, cap, deadline, input_bytes=b''):
    p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         env=env, cwd='/', start_new_session=True)
    selector = selectors.DefaultSelector()
    streams = {p.stdout: bytearray(), p.stderr: bytearray()}
    for stream in streams:
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ)
    offset = 0
    if input_bytes:
        os.set_blocking(p.stdin.fileno(), False)
        selector.register(p.stdin, selectors.EVENT_WRITE)
    else:
        p.stdin.close()
    try:
        while selector.get_map():
            need(time.monotonic() < deadline, 'process_timeout')
            for event, _ in selector.select(min(0.1, max(0, deadline-time.monotonic()))):
                stream = event.fileobj
                if stream is p.stdin:
                    offset += os.write(stream.fileno(), input_bytes[offset:offset+4096])
                    if offset == len(input_bytes):
                        selector.unregister(stream)
                        stream.close()
                    continue
                chunk = os.read(stream.fileno(), 65536)
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                else:
                    need(len(streams[stream]) + len(chunk) <= (cap if stream is p.stdout else 65536), 'process_output_limit')
                    streams[stream].extend(chunk)
        code = p.wait(timeout=max(0.001, deadline-time.monotonic()))
        need(code >= 0, 'process_signal')
        return code, bytes(streams[p.stdout]), bytes(streams[p.stderr])
    finally:
        selector.close()
        stop_owned_group(p)
        for stream in (p.stdin, p.stdout, p.stderr):
            if not stream.closed:
                stream.close()


class Profile:
    def __init__(self, selection, mode):
        self.s, self.mode = selection, mode
        self.root = Path(selection['workspace'])
        self.env = {'PATH': str(Path(sys.executable).parent) + ':/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
        self.deadline = time.monotonic() + 240
        self.failed_operation = None
        self.attempt = None
        self.journal = None
        self.operations = 0
        self.claim = None
        self.prior_context = None
        self.outcomes = {'task': None, 'observation': None, 'capture': None, 'context': None}
        self.key = 'de1-' + sha(wire([PROFILE, 1, self.s['run_id'], self.s['pm']['store_id'], self.s['pm']['task_id']]))

    def call(self, component, command, argv, cap, seconds=10, input_bytes=b''):
        self.failed_operation = component + ':' + command
        need(time.monotonic() + seconds + 10 <= self.deadline, 'attempt_budget')
        mutating = (component, command) in {('pm', 'claim'), ('pm', 'release'), ('pm', 'evidence attach'),
                    ('pm', 'transition'), ('handoff', 'record'), ('results', 'create'), ('results', 'capture')}
        record = None
        if mutating:
            need(self.journal is not None, 'missing_attempt_intent')
            self.operations += 1
            record = {'operation_version': 1, 'operation_id': uuid.uuid4().hex, 'component': component,
                      'command': command, 'state': 'intent', 'at': stamp(), 'run_id': self.s['run_id'],
                      'attempt_id': self.attempt, 'arguments_sha256': sha(wire(argv)),
                      'input_sha256': sha(input_bytes), 'outcomes': self.outcomes}
            record_path = self.journal / f'operation-{self.operations:02d}.json'
            self.save(record_path, wire(record))
        try:
            result = process(argv, self.env, cap, min(self.deadline, time.monotonic()+seconds), input_bytes)
        except (Stop, OSError, subprocess.SubprocessError):
            if record:
                self.save(record_path, wire({**record, 'state': 'unknown'}), True)
            raise
        if record:
            code, raw, err = result
            self.save(record_path, wire({**record, 'state': 'returned', 'exit': code, 'stdout_sha256': sha(raw),
                                        'stdout_bytes': len(raw), 'stderr_sha256': sha(err), 'stderr_bytes': len(err)}), True)
        return result

    def save(self, path, raw, replace=False):
        need(len(raw) <= (1048576 if path.suffix == '.raw' else 65536), 'receipt_file_limit')
        need(self.operations <= 32 and time.monotonic() < self.deadline, 'receipt_budget')
        if self.journal:
            size = sum(p.stat().st_size for p in self.journal.iterdir() if p.is_file())
            need(size + len(raw) <= 8*1024*1024, 'receipt_budget')
        durable(path, raw, replace)

    def checkpoint(self, state='in_progress'):
        self.save(self.journal / 'attempt.json', wire({
            'attempt_version': 1, 'profile': PROFILE, 'mode': self.mode, 'run_id': self.s['run_id'],
            'attempt_id': self.attempt, 'selection_sha256': sha(wire(self.s)), 'state': state,
            'failed_operation': self.failed_operation, 'outcomes': self.outcomes}), True)

    def begin(self):
        parent = self.root / 'receipts'
        if not parent.exists():
            parent.mkdir(mode=0o700)
        private_dir(parent)
        self.attempt = str(uuid.uuid4())
        self.holder = 'dev-evidence-' + self.attempt.replace('-', '')
        new_journal = parent / self.attempt
        new_journal.mkdir(mode=0o700)
        self.journal = new_journal
        self.checkpoint()

    def pm(self, *args):
        request = uuid.uuid4().hex
        command = ' '.join(args[:2]) if args[0] in ('evidence', 'claim-admission') else args[0]
        code, raw, _ = self.call('pm', command, [self.s['pm']['executable'], '--json', '--home', self.s['pm']['home'],
                                '--request-id', request, '--api-version', '1', *map(str, args)], 8*1024*1024)
        e = strict(raw, 8*1024*1024)
        need(isinstance(e, dict) and type(e.get('api_version')) is int and e['api_version'] == 1
             and e.get('command') == command and e.get('request_id') == request, 'pm_envelope')
        if code == 3 and e.get('ok') is False and e.get('outcome') == 'rejected':
            raise Stop('pm_refused', 3)
        need(code == 0 and e.get('ok') is True and e.get('error') is None
             and e.get('outcome') in ('observed', 'committed', 'no_change') and isinstance(e.get('data'), dict), 'pm_unknown')
        data = e['data']
        if args[0] != 'version':
            need(data.get('store_id') == self.s['pm']['store_id'], 'pm_store_changed', 3)
        if args[0] in ('show', 'claim', 'release', 'transition', 'evidence'):
            need(isinstance(data.get('task'), dict) and isinstance(data.get('claim'), dict), 'pm_task_shape')
            need(data['task'].get('id') == self.s['pm']['task_id'] and definition(data['task']) == self.s['pm']['task_definition_sha256']
                 and data['task'].get('title') == TITLE, 'task_changed', 3)
        return data

    def handoff(self, *args, input_bytes=b''):
        command = 'version' if args[0] == '--version' else args[0]
        code, raw, _ = self.call('handoff', command, [self.s['handoff']['executable'], '--json', '--store', self.s['handoff']['store'],
                                     *map(str, args)], 524288, input_bytes=input_bytes)
        e = strict(raw, 524288)
        need(isinstance(e, dict) and type(e.get('interface_version')) is int and e['interface_version'] == 1
             and e.get('authority') == 'none' and e.get('command') == command, 'handoff_envelope')
        if e.get('ok') is False and e.get('code') in {10: {'inspect_only'}, 11: {'no_match', 'ambiguous', 'not_found', 'no_task_context'},
                                                     65: {'invalid_input'}, 73: {'conflict', 'busy', 'id_collision'}}.get(code, set()):
            raise Stop('handoff_refused', 3)
        expected = {'version': 'version', 'list': 'listed', 'show': 'shown', 'record': 'recorded',
                    'pickup': 'context_available'}
        need(code == 0 and e.get('ok') is True and e.get('code') == expected.get(command)
             and isinstance(e.get('data'), dict), 'handoff_unknown')
        return e['data']

    def results(self, command, **data):
        code, raw, _ = self.call('results', command, [sys.executable, '-I', '-B', str(HELPER), command], 65536, 30, wire(data))
        e = strict(raw)
        if (code == 3 and isinstance(e, dict) and e.get('command') == command and e.get('state') == 'error'
                and e.get('outcome') == 'not_stored' and isinstance(e.get('code'), str)
                and re.fullmatch('[a-z_]{1,64}', e['code'])):
            if command == 'capture' and self.outcomes['capture']:
                self.outcomes['capture'].update(state='not_stored', native_code=e['code'], native_outcome='not_stored')
            raise Stop('results_refused', 3)
        need(code == 0 and isinstance(e, dict) and e.get('command') == command and e.get('state') == 'ok', 'results_unknown')
        return e['data']

    def inspect(self):
        p = self.pm('version')
        need(p.get('package_version') == '0.1.1' and type(p.get('api_version')) is int and p['api_version'] == 1
             and type(p.get('store_format_version')) is int and p['store_format_version'] == 1
             and {'tasks.v1', 'coverage.v1', 'claims.v1', 'transitions.v1', 'evidence.v1', 'admission.v1'} <= set(p.get('capabilities', [])), 'pm_version', 3)
        h = self.handoff('--version')
        need(wire(h) == wire({'package_version': '0.1.0', 'interface_version': 1, 'store_version': 1, 'record_version': 1}), 'handoff_version', 3)
        r = self.results('version')
        need(r == {'package_version': '0.1.0', 'reference_version': 1}, 'results_version', 3)
        code, raw, _ = self.call('reporter', 'version', [self.s['reporter']['executable'], '--json', 'version'], 1048576)
        v = strict(raw, 1048576)
        need(code == 0 and type(v.get('exit')) is int and v['exit'] == 0 and type(v.get('interface_version')) is int and v['interface_version'] == 1
             and v.get('command') == 'version' and v.get('package_version') == '0.1.0' and v.get('authority') == 'none'
             and {'inventory.v1', 'dirty-path-overlaps.v1', 'coverage.v1'} <= set(v.get('capabilities', [])), 'reporter_version', 3)
        task = self.pm('show', self.s['pm']['task_id'])
        admission = self.pm('claim-admission', 'status')
        need(isinstance(admission.get('admission'), dict), 'admission_shape')
        rows = self.handoff('list', '--task', self.key, '--limit', '50')
        need(type(rows.get('matching_total')) is int and rows['matching_total'] >= 0, 'handoff_list_shape')
        self.outcomes['task'] = {'store_id': task['store_id'], 'task_id': self.s['pm']['task_id'],
                                 'status': task['task']['status'], 'claim_state': task['claim']['state']}

    def acquire(self):
        data = self.pm('claim', self.s['pm']['task_id'], '--holder', self.holder, '--ttl-hours', '1')
        c = data['claim']
        need(isinstance(c.get('generation'), str) and re.fullmatch('[0-9a-f]{32}', c['generation']), 'claim_shape')
        self.claim = c
        self.outcomes['task'] = {'store_id': data['store_id'], 'task_id': self.s['pm']['task_id'],
                                 'holder': self.holder, 'generation': c['generation'], 'state': 'claimed'}
        self.checkpoint()
        self.owned(75)

    def owned(self, seconds=10):
        data = self.pm('show', self.s['pm']['task_id'])
        c = data['claim']
        need(self.claim is not None and c.get('state') == 'live' and c.get('holder') == self.holder
             and c.get('generation') == self.claim['generation'] and data['task'].get('status') == 'in_progress', 'claim_changed', 3)
        need((utc(c.get('expires_at'))-datetime.now(timezone.utc)).total_seconds() > seconds+10, 'claim_expiring', 3)
        if self.prior_context is not None:
            self.pickup(*self.prior_context)
        return data

    def observe(self):
        self.owned(75)
        argv = [self.s['reporter']['executable'], '--json', 'scan']
        for root in self.s['reporter']['repositories']:
            argv += ['--repo', root]
        code, raw, err = self.call('reporter', 'scan', argv, 1048576, 75)
        try:
            report = self.report(raw, code)
        except (Stop, ValueError, TypeError, KeyError, AttributeError):
            self.save(self.journal / 'diagnostic-report.raw', raw)
            self.save(self.journal / 'diagnostic-stderr.raw', err)
            raise Stop('report_not_established', 3 if code == 2 else 7) from None
        self.save(self.journal / 'report.raw', raw)
        self.outcomes['observation'] = {'interface_version': 1, 'package_version': '0.1.0',
            'scan_id': report['scan_id'], 'stdout_sha256': sha(raw), 'stdout_bytes': len(raw),
            'exit': code, 'coverage': report['coverage']['status'], 'conclusion': report['conclusion'],
            'started_at': report['started_at'], 'finished_at': report['finished_at']}
        self.checkpoint()
        return raw

    def report(self, raw, code):
        need(code in (0, 1, 3, 4), 'report_execution', 3 if code == 2 else 7)
        need(raw.endswith(b'\n') and not raw.endswith(b'\n\n'), 'report_wire')
        r = strict(raw, 1048576)
        need(isinstance(r, dict) and type(r.get('interface_version')) is int and r['interface_version'] == 1
             and r.get('package_version') == '0.1.0' and r.get('authority') == 'none' and r.get('command') == 'scan'
             and type(r.get('exit')) is int and r['exit'] == code and r.get('scope') == 'registered-worktrees/dirty-paths'
             and r.get('ignore_policy') == 'repository-only', 'report_envelope')
        uid(r['scan_id'])
        need(utc(r['started_at']) <= utc(r['finished_at']) <= datetime.now(timezone.utc), 'report_time')
        keys(r, 'interface_version package_version command authority scan_id started_at finished_at scope ignore_policy inputs repositories worktrees overlaps coverage problems conclusion exit')
        def path(value):
            keys(value, 'path_b64 path_utf8')
            need(isinstance(value['path_b64'], str), 'report_path')
            b = base64.b64decode(value['path_b64'], validate=True)
            need(b and b'\x00' not in b and base64.b64encode(b).decode('ascii') == value['path_b64'], 'report_path')
            try:
                label = b.decode('utf-8')
            except UnicodeError:
                label = None
            need(value['path_utf8'] == label, 'report_path_label')
            return b
        def identity(value):
            need(isinstance(value, str) and re.fullmatch('sha256:[0-9a-f]{64}', value), 'report_identity')
            return value
        def problem(value):
            codes = {'invalid_invocation', 'git_missing', 'unsupported_git_version', 'repository_unavailable', 'checkout_unavailable',
                     'git_failed', 'git_timeout', 'command_output_limit', 'status_parse_error', 'state_changed', 'worktree_limit',
                     'path_limit', 'overlap_limit', 'index_limit', 'config_limit', 'scan_deadline', 'output_limit', 'internal_error',
                     'unsupported_repository_feature'}
            need(isinstance(value, dict) and value.get('code') in codes, 'report_problem')
            if value['code'] == 'unsupported_repository_feature':
                need(value.get('feature') in {'bare', 'content_filter', 'included_config', 'submodule', 'sparse', 'split_index',
                                             'partial_clone', 'unproven_read_effect'}, 'report_feature')
        c = r['coverage']
        keys(c, 'status repositories_selected repositories_discovered registered_worktrees worktrees_observed worktrees_unavailable')
        for k in ('repositories_selected', 'repositories_discovered', 'worktrees_observed', 'worktrees_unavailable'):
            need(type(c[k]) is int and c[k] >= 0, 'report_count')
        need(c['registered_worktrees'] is None or type(c['registered_worktrees']) is int and c['registered_worktrees'] >= 0, 'report_count')
        for k, limit in [('inputs', 8), ('repositories', 8), ('worktrees', 64), ('overlaps', 1000), ('problems', 4096)]:
            need(isinstance(r[k], list) and len(r[k]) <= limit, 'report_list')
        inputs = [path(x['root']) for x in r['inputs']]
        need(sorted(inputs) == sorted(p.encode('utf-8') for p in self.s['reporter']['repositories'])
             and len(set(inputs)) == len(inputs), 'report_selected_inputs')
        repos = {identity(x['repository_id']): x for x in r['repositories']}
        trees = {identity(x['worktree_id']): x for x in r['worktrees']}
        need(len(repos) == len(r['repositories']) and len(trees) == len(r['worktrees']), 'report_duplicate_identity')
        for x in r['inputs']:
            need((x['repository_id'] is None) == (x['problem'] is not None), 'report_input_state')
            if x['repository_id'] is not None:
                need(x['repository_id'] in repos, 'report_input_repository')
            else:
                problem(x['problem'])
        need(c['repositories_selected'] == len(repos) + sum(x['repository_id'] is None for x in r['inputs']), 'report_selected_count')
        for x in repos.values():
            path(x['common_directory'])
            need(x['discovery_state'] in ('observed', 'changed', 'unavailable'), 'report_repository_state')
        observed = 0
        dirty = {}
        for key, x in trees.items():
            path(x['root'])
            need(x['repository_id'] in repos, 'report_worktree_repository')
            if x['observation_state'] == 'observed':
                observed += 1
                h = x['head']
                need(h['state'] in ('commit', 'unborn') and (h['oid'] is None) == (h['state'] == 'unborn'), 'report_head')
                if h['oid'] is not None:
                    need(isinstance(h['oid'], str) and re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', h['oid']), 'report_oid')
                if h['branch'] is not None:
                    path(h['branch'])
                need(isinstance(x['dirty_paths'], list) and len(x['dirty_paths']) <= 4096
                     and isinstance(x['renames'], list) and len(x['renames']) <= 4096, 'report_dirty_paths')
                values = [path(v) for v in x['dirty_paths']]
                need(len(set(values)) == len(values) and all(not p.startswith(b'/') and b'..' not in p.split(b'/') for p in values), 'report_dirty_paths')
                dirty[key] = set(values)
                for v in x['renames']:
                    need(v['kind'] in ('rename', 'copy') and path(v['source']) in dirty[key]
                         and path(v['destination']) in dirty[key], 'report_rename')
            else:
                need(x['observation_state'] in ('changed', 'unavailable', 'unsupported')
                     and x['head'] is None and x['dirty_paths'] is None and x['renames'] is None, 'report_worktree_state')
        need(c['worktrees_observed'] == observed and c['worktrees_unavailable'] == len(trees)-observed
             and (c['registered_worktrees'] is None or c['registered_worktrees'] == len(trees))
             and c['repositories_discovered'] == sum(x['discovery_state'] == 'observed' for x in repos.values())
             and c['repositories_selected'] >= len(repos), 'report_counts')
        seen = set()
        for overlap in r['overlaps']:
            pair = overlap['worktree_ids']
            need(isinstance(pair, list) and len(pair) == 2 and pair == sorted(set(pair)), 'report_overlap_pair')
            key = identity(overlap['id'])
            need(key not in seen, 'report_duplicate_overlap')
            seen.add(key)
            p = path(overlap['path'])
            for key in pair:
                need(key in dirty and p in dirty[key] and trees[key]['repository_id'] == overlap['repository_id'], 'report_overlap_path')
        for value in r['problems']:
            problem(value)
        if c['status'] == 'complete':
            need(observed > 0 and not r['problems'] and c['registered_worktrees'] == observed
                 and c['repositories_selected'] == c['repositories_discovered']
                 and (code, r['conclusion']) == ((1, 'overlap_observed') if r['overlaps'] else (0, 'no_overlap_observed')), 'report_coverage')
        elif c['status'] == 'partial':
            need(observed > 0 and r['problems'] and code == 3
                 and r['conclusion'] == ('overlap_observed' if r['overlaps'] else 'indeterminate'), 'report_coverage')
        else:
            need(c['status'] == 'unavailable' and observed == 0 and not r['overlaps'] and r['problems']
                 and code == 4 and r['conclusion'] == 'indeterminate', 'report_coverage')
        return r

    def capture(self, raw):
        self.owned(30)
        slot = self.attempt
        root = Path(self.s['results']['root']) / slot
        need(not root.exists(), 'existing_result_slot', 3)
        root.mkdir(mode=0o700)
        self.outcomes['capture'] = {'slot': slot, 'state': 'session_creation_unknown'}
        self.checkpoint()
        created = self.results('create', root=str(root), limits=LIMITS)
        sid = created.get('session_id')
        need(isinstance(sid, str) and re.fullmatch('[0-9a-f]{32}', sid), 'session_identity')
        reference = f'r1:{sid}:{sha(raw)}:{len(raw)}'
        self.outcomes['capture'] = {'slot': slot, 'session_id': sid, 'reference': reference, 'state': 'capture_not_requested'}
        self.checkpoint()
        self.owned(30)
        self.outcomes['capture']['state'] = 'capture_unknown'
        self.checkpoint()
        receipt = self.results('capture', root=str(root), session_id=sid, reference=reference,
                               report_path=str(self.journal / 'report.raw'))
        need(receipt.get('reference') == reference and receipt.get('sha256') == sha(raw)
             and receipt.get('utf8_bytes') == len(raw) and receipt.get('closed') is True, 'capture_receipt')
        self.owned(30)
        recovered = self.journal / 'capture-readback.raw'
        readback = self.results('read', root=str(root), reference=reference, output=str(recovered))
        need(read_private(recovered, self.root, 1048576) == raw and readback.get('reference') == reference,
             'capture_readback')
        snapshot = receipt['snapshot']
        need(isinstance(snapshot, dict) and isinstance(snapshot.get('text'), str)
             and len(snapshot['text'].encode('utf-8')) <= 4096 and snapshot.get('include_content') is False, 'snapshot_shape')
        self.outcomes['capture'].update(state='verified', verified_at=stamp(), snapshot=snapshot)
        self.checkpoint()

    def binding(self):
        c, p = self.outcomes['capture'], self.s['pm']
        return {'binding_version': 1, 'profile': PROFILE, 'run_id': self.s['run_id'], 'producer_attempt_id': self.attempt,
                'selection_sha256': sha(wire(self.s)), 'repositories_sha256': sha(wire(sorted(set(self.s['reporter']['repositories'])))),
                'pm': {'store_id': p['store_id'], 'task_id': p['task_id'], 'task_definition_sha256': p['task_definition_sha256'],
                       'producer_generation': self.claim['generation']}, 'result': {'slot': c['slot'], 'reference': c['reference']},
                'observation': self.outcomes['observation']}

    def context(self, binding):
        body = wire(binding).decode('ascii')
        need(len(body.encode()) <= 4096, 'context_body_limit')
        obs = binding['observation']
        reference = binding['result']['reference']
        record = {'record_version': 1, 'task_key': self.key, 'predecessor': None,
                  'project_key': 'starter-development-evidence-' + self.s['run_id'], 'title': 'Synthetic worktree evidence handover',
                  'status': 'active', 'actor': self.holder, 'request_id': uuid.uuid4().hex,
                  'context_as_of': obs['finished_at'], 'last_observed_outcome': obs['coverage'] + ' coverage; ' + obs['conclusion'] + '; exact report retained.',
                  'unfinished_step': 'Recover exact historical bytes and independently re-observe the selected worktrees.',
                  'recorded_next_step': 'Review the current request, validate this exact binding, and obtain fresh task ownership.',
                  'remaining_authority': 'none; consult the current request',
                  'acceptance_claims': [{'baseline': 'starter-development-evidence-capture-v1', 'reference': reference,
                                         'accepted_at': self.outcomes['capture']['verified_at']}],
                  'evidence': [{'source': 'orion-worktree-report/0.1.0', 'artifact': 'sha256:' + obs['stdout_sha256'],
                                'observed_at': obs['finished_at'], 'scope': 'registered-worktrees/dirty-paths; ' + obs['coverage'],
                                'reference': reference}], 'body': body}
        need(len(wire(record)) <= 65536, 'context_record_limit')
        self.owned()
        self.outcomes['context'] = {'request_id': record['request_id'], 'binding_sha256': sha(wire(binding)), 'state': 'record_unknown'}
        self.checkpoint()
        result = self.handoff('record', '--input', '-', input_bytes=wire(record))
        self.outcomes['context'].update(record_id=result['record_id'], sha256=result['sha256'])
        self.checkpoint()
        shown = self.handoff('show', result['record_id'])
        need(shown.get('current') is True and shown.get('sha256') == result['sha256']
             and shown.get('record', {}).get('body') == body, 'context_readback')
        self.outcomes['context']['state'] = 'verified'
        self.checkpoint()

    def exact_context(self):
        c = self.outcomes['context']
        shown = self.handoff('show', c['record_id'])
        need(shown.get('current') is True and shown.get('sha256') == c['sha256'], 'context_changed', 3)
        return shown

    def release(self):
        data = self.owned()
        self.pm('release', self.s['pm']['task_id'], '--holder', self.holder, '--generation', self.claim['generation'],
                '--expect-revision', data['task']['revision'])
        data = self.pm('show', self.s['pm']['task_id'])
        need(data['task']['status'] == 'todo' and data['claim']['state'] == 'absent', 'yield_readback')
        self.outcomes['task']['state'] = 'yielded' if self.mode == 'produce' else 'released_unfinished'
        self.checkpoint()

    def produce(self):
        rows = self.handoff('list', '--task', self.key, '--limit', '50')
        need(rows['matching_total'] == 0, 'existing_context', 3)
        need(not (self.root / 'yield.json').exists(), 'existing_yield', 3)
        self.begin()
        self.acquire()
        raw = self.observe()
        self.capture(raw)
        binding = self.binding()
        self.context(binding)
        self.exact_context()
        self.release()
        self.exact_context()
        receipt = {k: v for k, v in binding.items() if k != 'binding_version'}
        receipt.update(receipt_version=1, context={k: self.outcomes['context'][k] for k in ('record_id', 'sha256')},
                       pm_yield={'task_status': 'todo', 'claim_state': 'absent'})
        self.save(self.root / 'yield.json', wire(receipt))
        self.checkpoint('yielded')
        return self.reply('yielded')

    def yield_binding(self, receipt):
        keys(receipt, 'receipt_version profile run_id producer_attempt_id selection_sha256 repositories_sha256 pm result observation context pm_yield')
        need(type(receipt['receipt_version']) is int and receipt['receipt_version'] == 1 and receipt['profile'] == PROFILE
             and receipt['run_id'] == self.s['run_id'] and receipt['selection_sha256'] == sha(wire(self.s))
             and receipt['repositories_sha256'] == sha(wire(sorted(set(self.s['reporter']['repositories']))))
             and receipt['pm_yield'] == {'task_status': 'todo', 'claim_state': 'absent'}, 'yield_identity', 3)
        uid(receipt['producer_attempt_id'])
        keys(receipt['pm'], 'store_id task_id task_definition_sha256 producer_generation')
        need(all(receipt['pm'][k] == self.s['pm'][k] for k in ('store_id', 'task_id', 'task_definition_sha256'))
             and isinstance(receipt['pm']['producer_generation'], str)
             and re.fullmatch('[0-9a-f]{32}', receipt['pm']['producer_generation']), 'yield_task', 3)
        keys(receipt['result'], 'slot reference')
        need(receipt['result']['slot'] == receipt['producer_attempt_id'], 'yield_slot', 3)
        reference = receipt['result']['reference']
        need(isinstance(reference, str) and re.fullmatch(r'r1:[0-9a-f]{32}:[0-9a-f]{64}:(0|[1-9][0-9]{0,6})', reference), 'yield_reference', 3)
        obs = receipt['observation']
        keys(obs, 'interface_version package_version scan_id stdout_sha256 stdout_bytes exit coverage conclusion started_at finished_at')
        need(type(obs['stdout_bytes']) is int and 0 < obs['stdout_bytes'] <= 1048576
             and reference.split(':')[2:] == [obs['stdout_sha256'], str(obs['stdout_bytes'])], 'yield_content_identity', 3)
        keys(receipt['context'], 'record_id sha256')
        uid(receipt['context']['record_id'])
        need(isinstance(receipt['context']['sha256'], str) and re.fullmatch('[0-9a-f]{64}', receipt['context']['sha256']), 'context_digest', 3)
        return {'binding_version': 1, **{k: receipt[k] for k in ('profile', 'run_id', 'producer_attempt_id',
                'selection_sha256', 'repositories_sha256', 'pm', 'result', 'observation')}}

    def pickup(self, receipt, binding):
        picked = self.handoff('pickup', '--task', self.key, '--max-age-seconds', '86400')
        need(picked.get('match') == 'task' and picked.get('integrity') == 'valid' and picked.get('recency') == 'within_window'
             and picked.get('acceptance') == 'recorded' and picked.get('disposition') == 'context_available'
             and picked.get('task_key') == self.key and picked.get('selected_record_id') == receipt['context']['record_id']
             and picked.get('reasons') == [], 'pickup_refused', 3)
        shown = self.handoff('show', receipt['context']['record_id'])
        r = shown['record']
        native_bytes = (json.dumps(r, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
        obs = receipt['observation']
        need(shown.get('current') is True and shown.get('sha256') == receipt['context']['sha256'] == sha(native_bytes)
             and picked.get('record') == r and r.get('record_id') == receipt['context']['record_id']
             and r.get('task_key') == self.key and r.get('status') == 'active' and r.get('predecessor') is None
             and r.get('project_key') == 'starter-development-evidence-' + self.s['run_id']
             and r.get('actor') == 'dev-evidence-' + receipt['producer_attempt_id'].replace('-', '')
             and isinstance(r.get('body'), str) and r['body'].encode('utf-8') == wire(binding), 'context_binding', 3)
        now = datetime.now(timezone.utc)
        need(utc(obs['started_at']) <= utc(obs['finished_at']) == utc(r['context_as_of']) <= utc(r['created_at']) <= now
             and (now-utc(r['context_as_of'])).total_seconds() <= 86400, 'context_time', 3)
        acceptance = r.get('acceptance_claims')
        need(isinstance(acceptance, list) and len(acceptance) == 1, 'capture_acceptance', 3)
        a = acceptance[0]
        need(isinstance(a, dict) and set(a) == {'baseline', 'reference', 'accepted_at'}
             and a['baseline'] == 'starter-development-evidence-capture-v1' and a['reference'] == receipt['result']['reference']
             and utc(obs['finished_at']) <= utc(a['accepted_at']) <= utc(r['created_at']), 'capture_acceptance', 3)
        evidence = r.get('evidence')
        need(isinstance(evidence, list) and len(evidence) == 1 and evidence[0] == {
            'source': 'orion-worktree-report/0.1.0', 'artifact': 'sha256:' + obs['stdout_sha256'],
            'reference': receipt['result']['reference'], 'observed_at': r['context_as_of'],
            'scope': 'registered-worktrees/dirty-paths; ' + obs['coverage']}
            and r.get('remaining_authority') == 'none; consult the current request', 'capture_evidence', 3)
        self.outcomes['context'] = {**receipt['context'], 'state': 'verified'}

    def recover(self, receipt, name):
        slot = receipt['result']['slot']
        root = Path(self.s['results']['root']) / slot
        private_dir(root)
        destination = self.journal / name
        meta = self.results('read', root=str(root), reference=receipt['result']['reference'], output=str(destination))
        raw = read_private(destination, self.root, 1048576)
        obs = receipt['observation']
        need(meta['reference'] == receipt['result']['reference'] and len(raw) == obs['stdout_bytes']
             and sha(raw) == obs['stdout_sha256'], 'historical_capture_changed', 3)
        r = self.report(raw, obs['exit'])
        need(all(r[k] == obs[k] for k in ('scan_id', 'started_at', 'finished_at', 'conclusion'))
             and r['coverage']['status'] == obs['coverage'], 'historical_observation_changed', 3)

    def consume(self, path):
        receipt = strict(read_private(path, self.root))
        binding = self.yield_binding(receipt)
        self.pickup(receipt, binding)
        self.prior_context = (receipt, binding)
        self.begin()
        self.recover(receipt, 'historical.raw')
        current = self.pm('show', self.s['pm']['task_id'])
        need(current['task']['status'] == 'todo' and current['claim']['state'] == 'absent', 'task_not_available', 3)
        self.acquire()
        need(self.claim['generation'] != receipt['pm']['producer_generation'], 'reused_generation')
        self.pickup(receipt, binding)
        self.recover(receipt, 'historical-after-claim.raw')
        raw = self.observe()
        self.capture(raw)
        obs = self.outcomes['observation']
        if obs['coverage'] != 'complete' or obs['conclusion'] != 'overlap_observed':
            self.release()
            raise Stop('fresh_observation_does_not_meet_goal', 3)
        evidence = {'id': 'development-evidence-' + self.attempt, 'source': 'starter-consumer',
                    'artifact': 'sha256:' + obs['stdout_sha256'], 'observed_at': obs['finished_at'],
                    'scope': 'Independent complete positive dirty-path overlap observation; no merge-safety claim.',
                    'ref': self.outcomes['capture']['reference']}
        self.save(self.journal / 'evidence.json', wire(evidence))
        self.pickup(receipt, binding)
        data = self.owned()
        flags = ['--holder', self.holder, '--generation', self.claim['generation']]
        attached = self.pm('evidence', 'attach', self.s['pm']['task_id'], '--input', str(self.journal / 'evidence.json'),
                           '--expect-revision', data['task']['revision'], *flags)
        data = self.owned()
        self.pickup(receipt, binding)
        need(data['task']['revision'] == attached['task']['revision'], 'revision_changed', 3)
        self.pm('transition', self.s['pm']['task_id'], 'done', '--expect-revision', data['task']['revision'], *flags)
        final = self.pm('show', self.s['pm']['task_id'])
        need(final['task']['status'] == 'done' and final['claim']['state'] == 'absent'
             and evidence in final['task']['evidence'], 'completion_not_observed')
        self.outcomes['task']['state'] = 'completed'
        self.checkpoint('completed')
        self.save(self.journal / 'completed.json', wire(self.reply('completed')))
        return self.reply('completed')

    def reconcile(self, path):
        need(path.name == 'attempt.json' and path.parent.parent == self.root / 'receipts', 'invalid_attempt_path', 2)
        uid(path.parent.name)
        saved = strict(read_private(path, self.root))
        keys(saved, 'attempt_version profile mode run_id attempt_id selection_sha256 state failed_operation outcomes')
        need(type(saved['attempt_version']) is int and saved['attempt_version'] == 1 and saved['profile'] == PROFILE
             and saved['mode'] in ('produce', 'continue') and saved['run_id'] == self.s['run_id']
             and saved['selection_sha256'] == sha(wire(self.s)) and saved['attempt_id'] == path.parent.name, 'attempt_identity', 3)
        self.attempt = saved['attempt_id']
        # Deliberately do not adopt a journal: no call can persist an intent or mutate.
        self.outcomes = saved['outcomes']
        keys(self.outcomes, 'task observation capture context')
        current = self.pm('show', self.s['pm']['task_id'])
        holder = 'dev-evidence-' + self.attempt.replace('-', '')
        task = self.outcomes['task'] or {}
        self.outcomes['task'] = {**task, 'observed_status': current['task']['status'], 'observed_claim_state': current['claim']['state'],
                                 'same_attempt_holder_observed': current['claim'].get('holder') == holder}
        unresolved = False
        capture = self.outcomes['capture']
        if capture:
            need(capture.get('slot') == self.attempt, 'attempt_result_slot', 3)
            if not capture.get('session_id'):
                # The exact slot stays unresolved; never discover its unknown native SID.
                unresolved = True
            else:
                need(isinstance(capture['session_id'], str) and re.fullmatch('[0-9a-f]{32}', capture['session_id']), 'attempt_session', 3)
                meta = self.results('inspect', root=str(Path(self.s['results']['root']) / self.attempt),
                                    session_id=capture['session_id'], reference=capture.get('reference'))
                self.outcomes['capture'] = {**capture, **meta}
                unresolved = meta.get('status') != 'complete' or bool(capture.get('reference') and meta.get('recovery') != 'exact_bytes_observed')
        context = self.outcomes['context']
        if context:
            if context.get('record_id'):
                shown = self.handoff('show', context['record_id'])
                need(shown['sha256'] == context['sha256'], 'context_changed', 3)
                self.outcomes['context'] = {**context, 'recovery': 'exact_record_observed', 'current': shown['current']}
            else:
                rows = self.handoff('list', '--task', self.key, '--limit', '50')
                matches = []
                if rows.get('truncated') is False and type(rows.get('matching_total')) is int and rows['matching_total'] <= 50:
                    for row in rows['records']:
                        shown = self.handoff('show', row['record_id'])
                        r = shown['record']
                        if r.get('request_id') == context.get('request_id') and sha(r['body'].encode('utf-8')) == context.get('binding_sha256'):
                            matches.append(shown)
                if len(matches) == 1:
                    shown = matches[0]
                    self.outcomes['context'] = {**context, 'record_id': shown['record']['record_id'], 'sha256': shown['sha256'],
                                                'recovery': 'exact_record_observed', 'current': shown['current']}
                else:
                    unresolved = True
        # Every intent is bounded and exact. Readback observes state; it never replays it.
        for n in range(1, 33):
            op = path.parent / f'operation-{n:02d}.json'
            if not op.exists():
                break
            value = strict(read_private(op, self.root))
            need(value.get('attempt_id') == self.attempt and value.get('run_id') == self.s['run_id'], 'operation_identity', 3)
            if value.get('state') in ('intent', 'unknown') or value.get('state') == 'returned' and value.get('exit') not in (0, 3):
                if value.get('component') == 'pm':
                    command = value.get('command')
                    established = ((command == 'claim' and current['claim'].get('holder') == holder)
                                   or (command == 'release' and current['task']['status'] == 'todo' and current['claim']['state'] == 'absent')
                                   or (command == 'evidence attach' and any(x['id'] == 'development-evidence-' + self.attempt for x in current['task']['evidence']))
                                   or (command == 'transition' and current['task']['status'] == 'done'
                                       and any(x['id'] == 'development-evidence-' + self.attempt for x in current['task']['evidence'])))
                    unresolved = unresolved or not established
        reply = self.reply('reconciliation_required' if unresolved else 'reconciled', 'unresolved_operation' if unresolved else None)
        reply['original_attempt_resumed'] = False
        return reply, 7 if unresolved else 0

    def reply(self, state, reason=None):
        return {'profile_interface_version': 1, 'profile': PROFILE, 'mode': self.mode, 'run_id': self.s['run_id'],
                'attempt_id': self.attempt, 'state': state, 'reason': reason,
                'failed_operation': self.failed_operation if reason else None, 'versions': VERSIONS, 'outcomes': self.outcomes}


def main():
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument('mode', choices=('inspect', 'produce', 'continue', 'reconcile'))
    parser.add_argument('--selection', required=True)
    parser.add_argument('--yield-receipt')
    parser.add_argument('--attempt-receipt')
    profile = None
    args = None
    try:
        args = parser.parse_args()
        need((args.mode == 'continue') == bool(args.yield_receipt) and (args.mode == 'reconcile') == bool(args.attempt_receipt), 'invalid_arguments', 2)
        profile = Profile(selected(absolute(args.selection)), args.mode)
        profile.inspect()
        code = 0
        if args.mode == 'produce':
            reply = profile.produce()
        elif args.mode == 'continue':
            reply = profile.consume(absolute(args.yield_receipt))
        elif args.mode == 'reconcile':
            reply, code = profile.reconcile(absolute(args.attempt_receipt))
        else:
            need(args.mode == 'inspect', 'mode_not_implemented', 3)
            reply = profile.reply('inspected')
    except (Stop, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, subprocess.SubprocessError) as exc:
        code = exc.code if isinstance(exc, Stop) else 7
        reason = exc.reason if isinstance(exc, Stop) else 'unavailable'
        if profile and profile.journal:
            try:
                profile.checkpoint('refused' if code == 3 else 'reconciliation_required')
            except (Stop, OSError):
                reason, code = 'receipt_persistence_unknown', 7
        state = {2: 'invalid', 3: 'refused', 7: 'reconciliation_required'}[code]
        reply = profile.reply(state, reason) if profile else {
            'profile_interface_version': 1, 'profile': PROFILE, 'mode': getattr(args, 'mode', None), 'run_id': None,
            'attempt_id': None, 'state': state, 'reason': reason, 'failed_operation': 'selection' if args else 'arguments',
            'outcomes': {'task': None, 'observation': None, 'capture': None, 'context': None}}
    raw = wire(reply) + b'\n'
    if len(raw) > 65536:
        raw, code = b'{"state":"reconciliation_required","reason":"profile_output_limit"}\n', 7
    try:
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
    except (BrokenPipeError, OSError):
        if profile and profile.journal:
            try:
                profile.checkpoint('output_delivery_unknown')
            except (Stop, OSError):
                pass
        # Do not let Python's interpreter-shutdown flush turn exit 7 into 120
        # or echo an unraisable traceback after the caller closes its pipe.
        descriptor = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(descriptor, sys.stdout.fileno())
        finally:
            os.close(descriptor)
        return 7
    return code


if __name__ == '__main__':
    raise SystemExit(main())
