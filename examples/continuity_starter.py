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
        shape(cfg['paths'], 'state profiles')
        for path in cfg['paths'].values():
            owned(absolute(path), self.root)
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

    def pm(self, *args):
        request = uuid.uuid4().hex
        self.failed_operation = 'pm:' + args[0]
        code, raw, _ = bounded_command([self.s['pm']['executable'], '--json', '--home', self.s['pm']['home'],
                                       '--request-id', request, '--api-version', '1', *map(str, args)],
                                      self.env, 8 * 1024 * 1024)
        result = strict_json(raw, 8 * 1024 * 1024)
        require(isinstance(result, dict) and result.get('api_version') == 1 and result.get('request_id') == request
                and result.get('command') == (' '.join(args[:2]) if args[0] == 'evidence' else args[0]), 'pm_envelope')
        if result.get('ok') is False and code == 3 and result.get('outcome') == 'rejected':
            raise Refusal('pm_refused', 3)
        require(code == 0 and result.get('ok') is True and result.get('error') is None
                and result.get('outcome') in ('observed', 'committed', 'no_change')
                and isinstance(result.get('data'), dict), 'pm_unknown')
        data = result['data']
        if args[0] != 'version':
            require(data.get('store_id') == self.s['pm']['store_id'], 'pm_store_changed', 3)
        return data

    def handoff(self, *args, input_bytes=b''):
        self.failed_operation = 'handoff:' + args[0]
        code, raw, _ = bounded_command([self.s['handoff']['executable'], '--store', self.s['handoff']['store'],
                                       '--json', *map(str, args)], self.env, 524288, input_bytes=input_bytes)
        result = strict_json(raw, 524288)
        require(isinstance(result, dict) and result.get('interface_version') == 1 and result.get('authority') == 'none'
                and result.get('command') == ('version' if args[0] == '--version' else args[0]), 'handoff_envelope')
        require(code == 0 and result.get('ok') is True and isinstance(result.get('data'), dict), 'handoff_unknown')
        return result['data']

    def inspect(self):
        pm = self.pm('version')
        require(pm.get('package_version') == '0.1.1' and pm.get('api_version') == 1
                and {'tasks.v1', 'claims.v1', 'transitions.v1', 'evidence.v1', 'coverage.v1'}
                <= set(pm.get('capabilities', [])), 'pm_version', 3)
        h = self.handoff('--version')
        require(h == {'package_version': '0.1.0', 'interface_version': 1, 'store_version': 1, 'record_version': 1},
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
        require(mode == 'inspect', 'mode_not_implemented', 3)
        output.update(state='inspected', outcomes=outcomes, failed_operation=None)
        code = 0
    except (Refusal, OSError, ValueError, KeyError, TypeError) as exc:
        fault = exc if isinstance(exc, Refusal) else Refusal('invalid_selection_or_unavailable', 2)
        code = fault.exit_code
        output.update(state='reconciliation_required' if code == 7 else 'refused', reason=fault.reason,
                      failed_operation=profile.failed_operation if profile else None, outcomes={})
    print(wire(output).decode())
    return code


if __name__ == '__main__':
    raise SystemExit(main())
