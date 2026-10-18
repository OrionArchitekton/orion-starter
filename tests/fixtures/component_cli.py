"""Forward to a real installed component, optionally lose/corrupt its reply."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

p = Path(sys.argv[0]).parent
kind = Path(sys.argv[0]).name.split('-')[0]
args = sys.argv[1:]
cfg = json.loads((p / 'proxy.json').read_text())
command = args[7] if kind == 'pm' else args[3]
if command == 'evidence':
    command += ':' + args[8]
faults = json.loads((p / 'faults.json').read_text())
fault = faults.get(kind + ':' + command)
fd = os.open(p / 'proxy-calls.jsonl', os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
os.write(fd, (json.dumps([kind, command]) + '\n').encode())
os.close(fd)
if fault == 'before':
    raise SystemExit(1)
result = subprocess.run([cfg[kind], *args], input=sys.stdin.buffer.read(), capture_output=True)
if fault == 'after':
    os.kill(os.getpid(), signal.SIGKILL)
if fault in ('boolean_api', 'bad_task', 'huge_digest', 'boolean_total', 'float_total', 'negative_total', 'missing_total', 'bad_pickup'):
    value = json.loads(result.stdout)
    if fault == 'boolean_api':
        value['api_version'] = True
    elif fault == 'bad_task':
        value['data']['task'] = []
    elif fault == 'bad_pickup':
        value['data'] = []
    elif fault in ('boolean_total', 'float_total', 'negative_total', 'missing_total'):
        if fault == 'missing_total':
            value['data'].pop('matching_total', None)
        else:
            value['data']['matching_total'] = {'boolean_total': False, 'float_total': 0.0, 'negative_total': -1}[fault]
    else:
        value['data']['sha256'] = 'z' * 70000
    print(json.dumps(value))
else:
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
raise SystemExit(result.returncode)
