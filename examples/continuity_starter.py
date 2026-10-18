"""Manual synthetic continuity recipe over the installed public commands only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid
from urllib.parse import urlparse


class Refusal(Exception):
    def __init__(self, reason, exit_code=7):
        self.reason, self.exit_code = reason, exit_code


def require(condition, reason, exit_code=7):
    if not condition:
        raise Refusal(reason, exit_code)


def wire(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw, limit=65536):
    require(len(raw) <= limit, 'output_limit')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_key')
            result[key] = value
        return result
    def constant(_):
        raise Refusal('non_finite_json')
    try:
        # Reject deeply nested input before the JSON parser allocates its tree.
        text = raw.decode('utf-8')
        depth, quoted, escaped = 0, False, False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in '[{':
                depth += 1
                require(depth <= 16, 'json_depth')
            elif char in ']}':
                depth -= 1
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise Refusal('invalid_json') from None


def shape(value, keys):
    require(isinstance(value, dict) and set(value) == set(keys.split()), 'invalid_shape', 2)


def absolute(value):
    require(isinstance(value, str) and value.startswith('/') and str(Path(value)) == value
            and '..' not in Path(value).parts, 'invalid_path', 2)
    return Path(value)


def owned(path, root, *, exists=False, file=False):
    path = absolute(str(path))
    require(path == root or root in path.parents, 'path_outside_workspace', 2)
    for level in (path, *path.parents):
        require(not level.is_symlink(), 'symlink_path', 2)
        if level == root:
            break
    if path.exists():
        info = path.stat()
        require(info.st_uid == os.getuid(), 'wrong_owner', 2)
        if file:
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                    and stat.S_IMODE(info.st_mode) == 0o600, 'non_private_file', 2)
    else:
        require(not exists, 'missing_selected_path', 2)
    return path


def read_private(path, root):
    owned(path, root, exists=True, file=True)
    with open(path, 'rb') as f:
        raw = f.read(65537)
    require(len(raw) <= 65536, 'input_limit', 2)
    return raw


def definition(task):
    return sha(wire({k: task.get(k) for k in ('id', 'project', 'title', 'description', 'next_action')}))


def stamp():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def private_dir(path, root):
    owned(path, root)
    if not path.exists():
        path.mkdir(mode=0o700)
    require(path.is_dir() and stat.S_IMODE(path.stat().st_mode) == 0o700, 'non_private_directory')


def durable_file(path, value, root, replace=False):
    owned(path, root, file=path.exists())
    raw = wire(value) + b'\n'
    require(len(raw) <= 65536, 'receipt_limit')
    target = path.with_name(path.name + '.' + uuid.uuid4().hex) if replace else path
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        if replace:
            os.replace(target, path)
        directory = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        raise Refusal('receipt_write_unknown') from None


def bounded_command(argv, env, limit, timeout=10, input_bytes=b''):
    chunks = [bytearray(), bytearray()]
    process = None
    try:
        with tempfile.TemporaryFile() as incoming, selectors.DefaultSelector() as selector:
            incoming.write(input_bytes)
            incoming.seek(0)
            process = subprocess.Popen(argv, stdin=incoming, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, env=env, start_new_session=True)
            for i, pipe in enumerate((process.stdout, process.stderr)):
                selector.register(pipe, selectors.EVENT_READ, i)
            deadline = time.monotonic() + timeout
            while selector.get_map():
                require(time.monotonic() < deadline, 'command_timeout')
                for key, _ in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
                    data = os.read(key.fd, 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    i = key.data
                    require(len(chunks[i]) + len(data) <= (limit if i == 0 else 65536), 'output_limit')
                    chunks[i].extend(data)
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
            return code, bytes(chunks[0]), bytes(chunks[1])
    except (OSError, subprocess.TimeoutExpired):
        raise Refusal('command_unavailable_or_unknown') from None
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()


class Profile:
    def __init__(self, selection):
        p = absolute(selection)
        # Read the selected file only after checking its parent and permissions.
        self.root = p.parent
        require(self.root.is_dir() and self.root.stat().st_uid == os.getuid()
                and stat.S_IMODE(self.root.stat().st_mode) == 0o700, 'non_private_workspace', 2)
        require(not any(a.is_symlink() for a in (self.root, *self.root.parents)), 'symlink_workspace', 2)
        require(not any((a / '.git').exists() for a in (self.root, *self.root.parents)), 'workspace_in_git', 2)
        self.s = strict_json(read_private(p, self.root))
        shape(self.s, 'selection_version run_id workspace pm handoff browser client')
        require(type(self.s['selection_version']) is int and self.s['selection_version'] == 1, 'selection_version', 2)
        require(str(uuid.UUID(self.s['run_id'])) == self.s['run_id'], 'run_id', 2)
        require(absolute(self.s['workspace']) == self.root, 'workspace_mismatch', 2)
        for name, keys in [('pm', 'executable home store_id task_id task_definition_sha256'),
                           ('handoff', 'executable store'), ('browser', 'executable config config_sha256 name'),
                           ('client', 'executable config config_sha256')]:
            shape(self.s[name], keys)
            require(absolute(self.s[name]['executable']).is_file(), 'missing_executable', 2)
        require(all(isinstance(self.s['pm'][k], str) and self.s['pm'][k] for k in
                    ('store_id', 'task_id', 'task_definition_sha256')), 'pm_selection', 2)
        for name, key in [('pm', 'home'), ('handoff', 'store')]:
            owned(absolute(self.s[name][key]), self.root, exists=True)
        for name in ('browser', 'client'):
            raw = read_private(absolute(self.s[name]['config']), self.root)
            require(sha(raw) == self.s[name]['config_sha256'], 'config_changed', 2)
            if name == 'browser':
                self.config = tomllib.loads(raw.decode())
            else:
                require(strict_json(raw) == {}, 'client_config_overrides', 2)
        cfg = self.config
        require(set(cfg) <= {'paths', 'browser', 'timing', 'lease'}, 'browser_config_overrides', 2)
        timing = cfg.get('timing', {})
        require(isinstance(timing, dict) and set(timing) <= {'start_limit_seconds', 'stop_grace_seconds',
                'service_stop_timeout_seconds'}, 'timing_config', 2)
        for key, low, high, default in [('start_limit_seconds', 2, 600, 30), ('stop_grace_seconds', 1, 300, 15),
                                        ('service_stop_timeout_seconds', 11, 600, 30)]:
            value = timing.get(key, default)
            require(type(value) is int and low <= value <= high, 'timing_config', 2)
        require(timing.get('service_stop_timeout_seconds', 30) >= timing.get('stop_grace_seconds', 15) + 10,
                'timing_config', 2)
        lease_config = cfg.get('lease', {})
        require(isinstance(lease_config, dict) and set(lease_config) <= {'ttl_minutes', 'max_minutes'}, 'lease_config', 2)
        ttl, maximum = lease_config.get('ttl_minutes', 30), lease_config.get('max_minutes', 240)
        require(type(ttl) is int and type(maximum) is int and 1 <= ttl <= maximum <= 10080 and maximum >= 3,
                'lease_config', 2)
        shape(cfg['paths'], 'state profiles')
        for path in cfg['paths'].values():
            owned(absolute(path), self.root)
        states = [absolute(self.s['pm']['home']), absolute(self.s['handoff']['store']),
                  *(absolute(p) for p in cfg['paths'].values()), self.root / 'receipts', self.root / 'client-sockets']
        require(all(a != self.root and all(a != b and a not in b.parents and b not in a.parents
                    for b in states[i + 1:]) for i, a in enumerate(states)), 'overlapping_state', 2)
        require(len(cfg['browser']) == 1, 'browser_selection', 2)
        browser = cfg['browser'][0]
        shape(browser, 'name screen restore_session')
        require(browser['name'] == self.s['browser']['name'] and re.fullmatch('[a-z0-9]{1,16}', browser['name'])
                and browser['restore_session'] is False and type(browser['screen']) is int
                and 10 <= browser['screen'] <= 99, 'browser_selection', 2)
        require(not any(k.startswith(('ORION_BROWSER_', 'AGENT_BROWSER_')) for k in os.environ),
                'inherited_browser_override', 2)
        self.env = {k: os.environ[k] for k in ('HOME', 'LANG') if k in os.environ}
        node = shutil.which('node')
        self.env['PATH'] = (str(Path(node).parent) + ':' if node else '') + os.defpath
        self.env['XDG_RUNTIME_DIR'] = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
        self.env['DBUS_SESSION_BUS_ADDRESS'] = os.environ.get('DBUS_SESSION_BUS_ADDRESS',
                                                          'unix:path=' + self.env['XDG_RUNTIME_DIR'] + '/bus')
        self.env['ORION_BROWSER_CONFIG'] = self.s['browser']['config']
        self.env['AGENT_BROWSER_SOCKET_DIR'] = str(self.root / 'client-sockets')
        self.env['PYTHONDONTWRITEBYTECODE'] = '1'
        self.run_id, self.attempt = self.s['run_id'], uuid.uuid4().hex
        self.key = 'pm1-' + sha(wire(['orion-starter-continuity', 1, self.s['pm']['store_id'], self.s['pm']['task_id']]))
        self.failed_operation = None
        self.journal = None
        self.operations = 0
        self.outcomes = {}
        self.claim = None
        self.holder = 'cont-' + self.attempt
        self.resource = None

    def begin(self):
        parent = self.root / 'receipts'
        private_dir(parent, self.root)
        self.journal = parent / self.attempt
        private_dir(self.journal, self.root)
        durable_file(self.journal / 'attempt.json', {'run_id': self.run_id, 'attempt_id': self.attempt,
                                                    'holder': self.holder}, self.root)

    def execute(self, component, command, argv, limit, timeout=10, input_bytes=b''):
        self.failed_operation = component + ':' + command
        record, path = None, None
        if self.journal:
            require(self.operations < 64 and sum(p.stat().st_size for p in self.journal.iterdir()) < 900000,
                    'receipt_budget')
            self.operations += 1
            path = self.journal / f'{self.operations:02d}.json'
            record = {'operation_id': uuid.uuid4().hex, 'component': component, 'command': command,
                      'state': 'intent', 'at': stamp(), 'arguments_sha256': sha(wire(argv[1:])),
                      'input_sha256': sha(input_bytes), 'handles': self.outcomes}
            durable_file(path, record, self.root)
        code, raw, err = bounded_command(argv, self.env, limit, timeout, input_bytes)
        if record:
            record = {**record, 'state': 'returned', 'exit': code, 'stdout_sha256': sha(raw),
                      'stdout_bytes': len(raw), 'stderr_sha256': sha(err), 'stderr_bytes': len(err)}
            durable_file(path, record, self.root, replace=True)
        return code, raw, err

    def pm(self, *args):
        request = uuid.uuid4().hex
        self.failed_operation = 'pm:' + args[0]
        code, raw, _ = self.execute('pm', args[0], [self.s['pm']['executable'], '--json', '--home', self.s['pm']['home'],
                                       '--request-id', request, '--api-version', '1', *map(str, args)],
                                      8 * 1024 * 1024)
        result = strict_json(raw, 8 * 1024 * 1024)
        require(isinstance(result, dict) and type(result.get('api_version')) is int
                and result.get('api_version') == 1 and result.get('request_id') == request
                and result.get('command') == (' '.join(args[:2]) if args[0] == 'evidence' else args[0]), 'pm_envelope')
        if result.get('ok') is False and code == 3 and result.get('outcome') == 'rejected':
            raise Refusal('pm_refused', 3)
        require(code == 0 and result.get('ok') is True and result.get('error') is None
                and result.get('outcome') in ('observed', 'committed', 'no_change')
                and isinstance(result.get('data'), dict), 'pm_unknown')
        data = result['data']
        if args[0] in ('show', 'claim', 'release', 'transition', 'evidence'):
            require(isinstance(data.get('task'), dict) and isinstance(data.get('claim'), dict), 'pm_task_shape')
        if args[0] != 'version':
            require(data.get('store_id') == self.s['pm']['store_id'], 'pm_store_changed', 3)
        return data

    def handoff(self, *args, input_bytes=b''):
        self.failed_operation = 'handoff:' + args[0]
        code, raw, _ = self.execute('handoff', args[0], [self.s['handoff']['executable'], '--store', self.s['handoff']['store'],
                                       '--json', *map(str, args)], 524288, input_bytes=input_bytes)
        result = strict_json(raw, 524288)
        require(isinstance(result, dict) and type(result.get('interface_version')) is int
                and result.get('interface_version') == 1 and result.get('authority') == 'none'
                and result.get('command') == ('version' if args[0] == '--version' else args[0]), 'handoff_envelope')
        refusals = {10: {'inspect_only'}, 11: {'no_match', 'ambiguous', 'not_found', 'no_task_context'},
                    65: {'invalid_input'}, 73: {'conflict', 'busy', 'id_collision'}}
        if result.get('ok') is False and result.get('code') in refusals.get(code, set()):
            raise Refusal('handoff_refused', 3)
        require(code == 0 and result.get('ok') is True and isinstance(result.get('data'), dict), 'handoff_unknown')
        return result['data']

    def inspect(self):
        pm = self.pm('version')
        require(pm.get('package_version') == '0.1.1' and type(pm.get('api_version')) is int and pm.get('api_version') == 1
                and {'tasks.v1', 'claims.v1', 'transitions.v1', 'evidence.v1', 'coverage.v1'}
                <= set(pm.get('capabilities', [])), 'pm_version', 3)
        h = self.handoff('--version')
        require(wire(h) == wire({'package_version': '0.1.0', 'interface_version': 1, 'store_version': 1, 'record_version': 1}),
                'handoff_version', 3)
        for component, expected in [('browser', b'orion-browser 0.1.0'), ('client', b'agent-browser 0.25.4')]:
            self.failed_operation = component + ':version'
            code, raw, _ = bounded_command([self.s[component]['executable'], '--version'], self.env, 524288)
            require(code == 0 and raw.strip() == expected, 'unsupported_' + component, 3)
        task = self.pm('show', self.s['pm']['task_id'])
        require(task.get('task', {}).get('id') == self.s['pm']['task_id']
                and definition(task['task']) == self.s['pm']['task_definition_sha256'], 'task_changed', 3)
        rows = self.handoff('list', '--task', self.key, '--limit', '50')
        return {'task_status': task['task']['status'], 'claim_state': task['claim']['state'],
                'context_records': rows['matching_total']}

    def current_claim(self):
        data = self.pm('show', self.s['pm']['task_id'])
        c = data.get('claim', {})
        require(data.get('task', {}).get('id') == self.s['pm']['task_id']
                and definition(data['task']) == self.s['pm']['task_definition_sha256']
                and data['task']['status'] == 'in_progress'
                and c.get('state') == 'live' and c.get('holder') == self.holder
                and self.claim is not None and c.get('generation') == self.claim['generation'], 'claim_changed', 3)
        return data

    def acquire(self):
        coverage = self.pm('probe', self.s['pm']['task_id'])
        require(coverage.get('coverage') in ('clear', 'matches'), 'coverage_unknown')
        data = self.pm('claim', self.s['pm']['task_id'], '--holder', self.holder, '--ttl-hours', '1')
        self.claim = data.get('claim', {})
        require(isinstance(self.claim.get('generation'), str)
                and re.fullmatch('[0-9a-f]{32}', self.claim['generation']), 'claim_result')
        self.outcomes['pm'] = {'holder': self.holder, 'generation': self.claim['generation'], 'state': 'claimed'}
        self.current_claim()

    def browser(self, command, *args):
        require(sha(read_private(absolute(self.s['browser']['config']), self.root)) ==
                self.s['browser']['config_sha256'], 'config_changed', 3)
        timing = self.config.get('timing', {})
        timeout = 615 + 2 * timing.get('start_limit_seconds', 30) + timing.get('service_stop_timeout_seconds', 30)
        code, raw, _ = self.execute('browser', command, [self.s['browser']['executable'], '--json',
                                   command, self.s['browser']['name'], *args], 524288, timeout)
        result = strict_json(raw, 524288)
        require(isinstance(result, dict) and type(result.get('exit')) is int and result.get('exit') == code
                and result.get('ok') is (code == 0) and result.get('code') == {0: 'OK', 3: 'BUSY', 4: 'NOT_HOLDER',
                    6: 'BROWSER_DOWN', 7: 'UNHEALTHY', 1: 'INTERNAL', 2: 'USAGE'}.get(code)
                and isinstance(result.get('data'), dict), 'browser_envelope')
        require(code == 0 or (command == 'status' and code == 6), 'browser_refused', 3 if code in (3, 4) else 7)
        data = result['data']
        require(data.get('browser') == self.s['browser']['name'], 'browser_identity')
        return data

    def native_owner(self):
        self.current_claim()
        data = self.browser('status')
        require(data.get('holder') == self.holder and data.get('state') == 'healthy'
                and data.get('expires_at') == self.resource['expires_at'] and data.get('expired') is False,
                'resource_changed', 3)
        expires = datetime.fromisoformat(data['expires_at'])
        require((expires - datetime.now(timezone.utc)).total_seconds() > 45, 'resource_expiring', 3)
        self.current_claim()

    def client(self, command, *args):
        require(sha(read_private(absolute(self.s['client']['config']), self.root)) ==
                self.s['client']['config_sha256'], 'config_changed', 3)
        code, raw, _ = self.execute('client', command, [self.s['client']['executable'], '--session', self.holder,
                                   '--config', self.s['client']['config'], '--json', command, *args], 524288, 35)
        result = strict_json(raw, 524288)
        require(code == 0, 'client_unknown')
        if command != 'batch':
            require(isinstance(result, dict) and result.get('success') is True
                    and result.get('error') is None and isinstance(result.get('data'), dict), 'client_envelope')
            require(result['data'].get('launched' if command == 'connect' else 'closed') is True, 'client_result')
        return result

    def observe(self):
        self.current_claim()
        before = self.browser('status')
        require(before.get('state') == 'down' and before.get('holder') is None, 'resource_not_free', 3)
        self.current_claim()
        self.resource = self.browser('lease', '--holder', self.holder, '--minutes', '3')
        r = self.resource
        require(r.get('holder') == self.holder and isinstance(r.get('session'), str)
                and 1 <= len(r['session']) <= 128, 'resource_grant')
        endpoint = urlparse(r.get('endpoint', ''))
        require(endpoint.scheme == 'ws' and endpoint.hostname == '127.0.0.1' and endpoint.port == r.get('port')
                and endpoint.username is None and endpoint.password is None and not endpoint.query
                and not endpoint.fragment and endpoint.path.startswith('/devtools/browser/'), 'resource_endpoint')
        self.outcomes['browser'] = {'holder': self.holder, 'session': r['session'], 'state': 'leased'}
        private_dir(self.root / 'client-sockets', self.root)
        self.native_owner()
        self.client('connect', r['endpoint'])
        self.native_owner()
        result = self.client('batch', '--bail', 'open https://example.com/', 'get title', 'get url')
        expected = [(['open', 'https://example.com/'], {'title': 'Example Domain', 'url': 'https://example.com/'}),
                    (['get', 'title'], {'title': 'Example Domain'}), (['get', 'url'], {'url': 'https://example.com/'})]
        require(isinstance(result, list) and len(result) == len(expected), 'read_shape')
        for item, (command, value) in zip(result, expected):
            require(isinstance(item, dict) and item.get('command') == command and item.get('success') is True
                    and item.get('error') is None and item.get('result') == value, 'read_result')
        observed_at = stamp()
        self.native_owner()
        released = self.browser('release', '--holder', self.holder)
        require(released.get('stop') == 'clean', 'release_not_clean')
        self.outcomes['browser']['state'] = 'released'
        self.client('close')
        down = self.browser('status')
        require(down.get('state') == 'down' and down.get('holder') is None, 'resource_not_down')
        self.outcomes['browser']['state'] = 'clean_down'
        return {'sha256': sha(wire({'title': 'Example Domain', 'url': 'https://example.com/'})),
                'observed_at': observed_at}

    def produce(self):
        require(not (self.root / 'yield.json').exists(), 'yield_already_exists', 3)
        self.begin()
        self.acquire()
        observation = self.observe()
        body = {'binding_version': 1, 'run_id': self.run_id, 'pm_store_id': self.s['pm']['store_id'],
                'pm_task_id': self.s['pm']['task_id'], 'task_definition_sha256': self.s['pm']['task_definition_sha256'],
                'producer_claim_generation': self.claim['generation'], 'producer_observation_sha256': observation['sha256']}
        value = {'record_version': 1, 'task_key': self.key, 'predecessor': None,
                 'project_key': 'starter-' + self.run_id, 'title': 'Synthetic page continuation', 'status': 'active',
                 'actor': self.holder, 'request_id': self.attempt, 'context_as_of': observation['observed_at'],
                 'last_observed_outcome': 'Example Domain at https://example.com/; native browser released cleanly.',
                 'unfinished_step': 'Independently observe the page and clean up before task completion.',
                 'recorded_next_step': 'Review the current request, then obtain new task and browser ownership.',
                 'remaining_authority': 'none; consult the current request',
                 'acceptance_claims': [{'baseline': 'starter-synthetic-read-v1', 'reference': 'https://example.com/',
                                        'accepted_at': observation['observed_at']}],
                 'evidence': [{'source': 'starter-producer', 'artifact': 'sha256:' + observation['sha256'],
                               'observed_at': observation['observed_at'], 'scope': 'Synthetic page read and clean release.',
                               'reference': 'https://example.com/'}], 'body': wire(body).decode()}
        self.current_claim()
        recorded = self.handoff('record', '--input', '-', input_bytes=wire(value))
        require(isinstance(recorded.get('record_id'), str) and len(recorded['record_id']) == 36
                and str(uuid.UUID(recorded['record_id'])) == recorded['record_id']
                and isinstance(recorded.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', recorded['sha256']),
                'record_result')
        shown = self.handoff('show', recorded['record_id'])
        require(shown.get('sha256') == recorded.get('sha256') and shown.get('current') is True
                and {k: v for k, v in shown['record'].items() if k not in ('record_id', 'created_at')} == value,
                'record_readback')
        self.outcomes['handoff'] = {'record_id': recorded['record_id'], 'sha256': recorded['sha256'], 'state': 'verified'}
        data = self.current_claim()
        self.pm('release', self.s['pm']['task_id'], '--holder', self.holder, '--generation', self.claim['generation'],
                '--expect-revision', data['task']['revision'])
        current = self.pm('show', self.s['pm']['task_id'])
        require(current['task']['status'] == 'todo' and current['claim']['state'] == 'absent', 'yield_not_observed')
        self.outcomes['pm']['state'] = 'yielded'
        receipt = {'receipt_version': 1, 'run_id': self.run_id, 'producer_attempt_id': self.attempt,
                   'pm_store_id': self.s['pm']['store_id'], 'pm_task_id': self.s['pm']['task_id'],
                   'task_definition_sha256': self.s['pm']['task_definition_sha256'],
                   'producer_generation': self.claim['generation'], 'producer_holder': self.holder,
                   'browser_session': self.resource['session'], 'handoff_task_key': self.key,
                   'handoff_store_role': 'selected_handoff', 'record_id': recorded['record_id'],
                   'record_sha256': recorded['sha256'], 'observation': observation, 'resource_stop': 'clean',
                   'client_closed': True, 'browser_down': True, 'pm_yield': {'task_status': 'todo', 'claim_state': 'absent'}}
        durable_file(self.root / 'yield.json', receipt, self.root)
        return self.outcomes

    def context(self, receipt):
        picked = self.handoff('pickup', '--task', self.key, '--max-age-seconds', '86400')
        require(picked.get('match') == 'task' and picked.get('integrity') == 'valid'
                and picked.get('disposition') == 'context_available' and picked.get('recency') == 'within_window'
                and picked.get('acceptance') == 'recorded' and picked.get('task_key') == self.key
                and picked.get('selected_record_id') == receipt['record_id']
                and picked.get('continuation') is not None and picked.get('reasons') == [], 'context_unusable', 3)
        shown = self.handoff('show', receipt['record_id'])
        require(shown.get('sha256') == receipt['record_sha256'] and shown.get('current') is True
                and shown.get('record') == picked.get('record'), 'record_changed', 3)
        record = shown['record']
        require(all(isinstance(record.get(k), str) and record[k].strip() for k in
                    ('last_observed_outcome', 'unfinished_step', 'recorded_next_step', 'remaining_authority')),
                'incomplete_context', 3)
        require(record.get('record_version') == 1 and record.get('record_id') == receipt['record_id']
                and record.get('task_key') == self.key and record.get('project_key') == 'starter-' + self.run_id
                and record.get('status') == 'active' and record.get('actor') == receipt['producer_holder']
                and record.get('request_id') == receipt['producer_attempt_id']
                and record.get('context_as_of') == receipt['observation']['observed_at'], 'record_binding', 3)
        body = record.get('body')
        require(isinstance(body, str) and len(body.encode()) <= 4096, 'record_body', 3)
        require(wire(strict_json(body.encode(), 4096)) == wire({
            'binding_version': 1, 'run_id': self.run_id, 'pm_store_id': self.s['pm']['store_id'],
            'pm_task_id': self.s['pm']['task_id'], 'task_definition_sha256': self.s['pm']['task_definition_sha256'],
            'producer_claim_generation': receipt['producer_generation'],
            'producer_observation_sha256': receipt['observation']['sha256']}), 'context_binding', 3)
        require(record.get('acceptance_claims') == [{'baseline': 'starter-synthetic-read-v1',
                'reference': 'https://example.com/', 'accepted_at': receipt['observation']['observed_at']}]
                and record.get('evidence') == [{'source': 'starter-producer',
                'artifact': 'sha256:' + receipt['observation']['sha256'],
                'observed_at': receipt['observation']['observed_at'],
                'scope': 'Synthetic page read and clean release.', 'reference': 'https://example.com/'}],
                'context_evidence', 3)
        self.outcomes['handoff'] = {'record_id': receipt['record_id'], 'sha256': receipt['record_sha256'], 'state': 'verified'}

    def continue_task(self, filename):
        receipt = strict_json(read_private(absolute(filename), self.root))
        shape(receipt, 'receipt_version run_id producer_attempt_id pm_store_id pm_task_id task_definition_sha256 '
              'producer_generation producer_holder browser_session handoff_task_key handoff_store_role record_id '
              'record_sha256 observation resource_stop client_closed browser_down pm_yield')
        shape(receipt['observation'], 'sha256 observed_at')
        for key, expected in [('receipt_version', 1), ('run_id', self.run_id), ('pm_store_id', self.s['pm']['store_id']),
                              ('pm_task_id', self.s['pm']['task_id']), ('handoff_task_key', self.key),
                              ('task_definition_sha256', self.s['pm']['task_definition_sha256']),
                              ('handoff_store_role', 'selected_handoff'), ('resource_stop', 'clean'),
                              ('client_closed', True), ('browser_down', True),
                              ('pm_yield', {'task_status': 'todo', 'claim_state': 'absent'})]:
            require(receipt[key] == expected and type(receipt[key]) is type(expected), 'yield_receipt_mismatch', 3)
        for key, length in [('producer_attempt_id', 32), ('producer_generation', 32), ('record_sha256', 64)]:
            require(isinstance(receipt[key], str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', receipt[key]),
                    'receipt_identity', 3)
        require(receipt['producer_holder'] == 'cont-' + receipt['producer_attempt_id']
                and isinstance(receipt['browser_session'], str) and 1 <= len(receipt['browser_session']) <= 128
                and str(uuid.UUID(receipt['record_id'])) == receipt['record_id']
                and receipt['observation']['sha256'] == sha(wire({'title': 'Example Domain', 'url': 'https://example.com/'})),
                'receipt_identity', 3)
        self.begin()
        self.context(receipt)
        self.acquire()
        require(self.claim['generation'] != receipt['producer_generation'], 'reused_generation')
        self.context(receipt)
        observation = self.observe()
        require(self.resource['session'] != receipt['browser_session'], 'reused_resource_session')
        evidence = {'id': 'continuity-' + self.attempt, 'source': 'starter-consumer',
                    'artifact': 'sha256:' + observation['sha256'], 'observed_at': observation['observed_at'],
                    'scope': 'Independent consumer read and clean native browser release.', 'ref': 'https://example.com/'}
        evidence_file = self.journal / 'evidence.json'
        durable_file(evidence_file, evidence, self.root)
        data = self.current_claim()
        flags = ['--holder', self.holder, '--generation', self.claim['generation']]
        attached = self.pm('evidence', 'attach', self.s['pm']['task_id'], '--input', str(evidence_file),
                           '--expect-revision', data['task']['revision'], *flags)
        current = self.current_claim()
        require(current['task']['revision'] == attached['task']['revision'], 'revision_changed', 3)
        self.pm('transition', self.s['pm']['task_id'], 'done', '--expect-revision', attached['task']['revision'], *flags)
        final = self.pm('show', self.s['pm']['task_id'])
        require(final['task']['status'] == 'done' and final['claim']['state'] == 'absent'
                and evidence in final['task']['evidence'], 'completion_not_observed')
        self.outcomes['pm']['state'] = 'completed'
        self.outcomes['evidence'] = {'id': evidence['id'], **observation}
        durable_file(self.journal / 'completed.json', self.outcomes, self.root)
        return self.outcomes


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refusal('invalid_arguments', 2)


def main():
    profile, mode = None, None
    output = {'profile_interface_version': 1, 'run_id': None, 'attempt_id': None, 'mode': None}
    try:
        p = Parser(description=__doc__, allow_abbrev=False)
        p.add_argument('--selection', required=True)
        p.add_argument('mode', choices=('inspect', 'produce', 'continue'))
        p.add_argument('--yield-receipt')
        args = p.parse_args()
        mode = args.mode
        require((args.yield_receipt is not None) == (mode == 'continue'), 'yield_receipt_argument', 2)
        profile = Profile(args.selection)
        output.update(run_id=profile.run_id, attempt_id=profile.attempt, mode=mode)
        outcomes = profile.inspect()
        if mode == 'produce':
            require(outcomes['context_records'] == 0, 'context_already_exists', 3)
            outcomes = profile.produce()
        elif mode == 'continue':
            outcomes = profile.continue_task(args.yield_receipt)
        else:
            require(mode == 'inspect', 'mode_not_implemented', 3)
        output.update(state={'produce': 'yielded', 'continue': 'completed', 'inspect': 'inspected'}[mode],
                      outcomes=outcomes, failed_operation=None)
        code = 0
    except (Exception, KeyboardInterrupt) as exc:
        fault = exc if isinstance(exc, Refusal) else Refusal('invalid_selection_or_unavailable', 7 if profile else 2)
        code = fault.exit_code
        if code == 3 and profile and (profile.outcomes.get('pm', {}).get('state') == 'claimed'
                                      or profile.outcomes.get('browser', {}).get('state') in ('leased', 'released')):
            code = 7
        output.update(state='reconciliation_required' if code == 7 else 'refused', reason=fault.reason,
                      failed_operation=profile.failed_operation if profile else None, outcomes=profile.outcomes if profile else {})
    raw = wire(output)
    if len(raw) + 1 > 65536:
        code = 7
        raw = wire({**output, 'state': 'reconciliation_required', 'reason': 'output_limit', 'outcomes': {}})
    try:
        print(raw.decode(), flush=True)
    except BrokenPipeError:
        # Suppress the interpreter's later flush traceback; delivery remains unknown.
        fd = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(fd, sys.stdout.fileno())
        finally:
            os.close(fd)
        return 7
    return code


if __name__ == '__main__':
    raise SystemExit(main())
