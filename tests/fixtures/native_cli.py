"""Deterministic executables mirroring observed pinned native JSON shapes."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import uuid

p = Path(sys.argv[0]).parent
args = sys.argv[1:]
kind = Path(sys.argv[0]).name
if '--version' in args:
    print('orion-browser 0.1.0' if kind == 'browser' else 'agent-browser 0.25.4')
    raise SystemExit(0)

if kind == 'browser':
    command = args[1]
else:
    command = args[5]

fd = os.open(p / 'calls.jsonl', os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
os.write(fd, (json.dumps([kind, command]) + '\n').encode())
os.close(fd)
faults = json.loads((p / 'faults.json').read_text()) if (p / 'faults.json').exists() else {}
fault = faults.get(kind + ':' + command)
if fault == 'before':
    raise SystemExit(1)

state = p / 'fake-browser.json'
lease = json.loads(state.read_text()) if state.exists() else None
if kind == 'browser':
    code, data = 0, {}
    if command == 'status':
        code = 0 if lease else 6
        data = {'browser': 'contdemo', 'holder': lease['holder'] if lease else None,
                'expires_at': lease['expires_at'] if lease else None,
                'expired': False, 'state': 'healthy' if lease else 'down'}
    elif command == 'lease':
        lease = {'browser': 'contdemo', 'holder': args[args.index('--holder') + 1],
                 'session': uuid.uuid4().hex[:12],
                 'endpoint': 'ws://127.0.0.1:9001/devtools/browser/11111111-1111-4111-8111-111111111111',
                 'port': 9001, 'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat()}
        if fault == 'bad_time':
            lease['expires_at'] = 'unparseable'
        state.write_text(json.dumps(lease))
        state.chmod(0o600)
        data = lease
    elif command == 'release':
        if not lease or lease['holder'] != args[args.index('--holder') + 1]:
            code, data = 4, {'browser': 'contdemo'}
        else:
            state.unlink()
            data = {'browser': 'contdemo', 'stop': 'clean'}
    else:
        raise SystemExit(2)
    result = {'ok': code == 0, 'code': {0: 'OK', 6: 'BROWSER_DOWN', 4: 'NOT_HOLDER'}[code],
              'exit': code, 'message': '', 'data': data}
else:
    code = 0
    if command == 'batch':
        result = [{'command': ['open', 'https://example.com/'], 'error': None,
                   'result': {'title': 'Example Domain', 'url': 'https://example.com/'}, 'success': True},
                  {'command': ['get', 'title'], 'error': None, 'result': {'title': 'Example Domain'}, 'success': True},
                  {'command': ['get', 'url'], 'error': None, 'result': {'url': 'https://example.com/'}, 'success': True}]
    else:
        result = {'success': True, 'data': {'launched': True} if command == 'connect' else {'closed': True},
                  'error': None}
if fault == 'after':
    raise SystemExit(1)
print(json.dumps(result))
raise SystemExit(code)
