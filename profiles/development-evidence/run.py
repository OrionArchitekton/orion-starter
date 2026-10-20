"""Manually selected, local development evidence demonstration. No ambient state."""
import argparse
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
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno())
        need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == os.getuid()
             and stat.S_IMODE(s.st_mode) == 0o600 and s.st_size <= limit, 'non_private_file', 2)
        raw = f.read(limit + 1)
    need(len(raw) <= limit, 'file_limit')
    return raw


def definition(task):
    return sha(wire({k: task.get(k) for k in ('id', 'project', 'title', 'description', 'next_action')}))


def selected(path):
    no_links(path)
    raw = path.read_bytes() if path.stat().st_size <= 65536 else b' ' * 65537
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
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    raise Stop('process_stop_unknown') from None
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
        self.outcomes = {'task': None, 'observation': None, 'capture': None, 'context': None}
        self.key = 'de1-' + sha(wire([PROFILE, 1, self.s['run_id'], self.s['pm']['store_id'], self.s['pm']['task_id']]))

    def call(self, component, command, argv, cap, seconds=10, input_bytes=b''):
        self.failed_operation = component + ':' + command
        need(time.monotonic() + seconds <= self.deadline, 'attempt_budget')
        return process(argv, self.env, cap, min(self.deadline, time.monotonic()+seconds), input_bytes)

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
        need(code == 0 and isinstance(e, dict) and e.get('command') == command and e.get('state') == 'ok', 'results_unknown')
        return e['data']

    def inspect(self):
        p = self.pm('version')
        need(p.get('package_version') == '0.1.1' and p.get('api_version') == 1 and p.get('store_format_version') == 1
             and {'tasks.v1', 'coverage.v1', 'claims.v1', 'transitions.v1', 'evidence.v1', 'admission.v1'} <= set(p.get('capabilities', [])), 'pm_version', 3)
        h = self.handoff('--version')
        need(wire(h) == wire({'package_version': '0.1.0', 'interface_version': 1, 'store_version': 1, 'record_version': 1}), 'handoff_version', 3)
        r = self.results('version')
        need(r == {'package_version': '0.1.0', 'reference_version': 1}, 'results_version', 3)
        code, raw, _ = self.call('reporter', 'version', [self.s['reporter']['executable'], '--json', 'version'], 1048576)
        v = strict(raw, 1048576)
        need(code == 0 and v.get('exit') == 0 and type(v.get('interface_version')) is int and v['interface_version'] == 1
             and v.get('command') == 'version' and v.get('package_version') == '0.1.0' and v.get('authority') == 'none'
             and {'inventory.v1', 'dirty-path-overlaps.v1', 'coverage.v1'} <= set(v.get('capabilities', [])), 'reporter_version', 3)
        task = self.pm('show', self.s['pm']['task_id'])
        rows = self.handoff('list', '--task', self.key, '--limit', '50')
        need(type(rows.get('matching_total')) is int and rows['matching_total'] >= 0, 'handoff_list_shape')
        self.outcomes['task'] = {'store_id': task['store_id'], 'task_id': self.s['pm']['task_id'],
                                 'status': task['task']['status'], 'claim_state': task['claim']['state']}

    def reply(self, state, reason=None):
        return {'profile_interface_version': 1, 'profile': PROFILE, 'mode': self.mode, 'run_id': self.s['run_id'],
                'attempt_id': self.attempt, 'state': state, 'reason': reason,
                'failed_operation': self.failed_operation if reason else None, 'versions': VERSIONS, 'outcomes': self.outcomes}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('mode', choices=('inspect', 'produce', 'continue', 'reconcile'))
    parser.add_argument('--selection', required=True)
    parser.add_argument('--yield-receipt')
    parser.add_argument('--attempt-receipt')
    profile = None
    try:
        args = parser.parse_args()
        need((args.mode == 'continue') == bool(args.yield_receipt) and (args.mode == 'reconcile') == bool(args.attempt_receipt), 'invalid_arguments', 2)
        profile = Profile(selected(absolute(args.selection)), args.mode)
        profile.inspect()
        need(args.mode == 'inspect', 'mode_not_implemented', 3)
        reply, code = profile.reply('inspected'), 0
    except (Stop, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, subprocess.SubprocessError) as exc:
        code = exc.code if isinstance(exc, Stop) else 7
        reason = exc.reason if isinstance(exc, Stop) else 'unavailable'
        state = {2: 'invalid', 3: 'refused', 7: 'reconciliation_required'}[code]
        reply = profile.reply(state, reason) if profile else {'profile_interface_version': 1, 'profile': PROFILE,
                                                             'state': state, 'reason': reason}
    raw = wire(reply) + b'\n'
    if len(raw) > 65536:
        raw, code = b'{"state":"reconciliation_required","reason":"profile_output_limit"}\n', 7
    try:
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
    except (BrokenPipeError, OSError):
        return 7
    return code


if __name__ == '__main__':
    raise SystemExit(main())
