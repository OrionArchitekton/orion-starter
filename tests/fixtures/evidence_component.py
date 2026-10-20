"""Controlled faults around a real selected public command, for process-seam tests."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

config = json.loads(Path(__file__ + '.json').read_text())
args = sys.argv[1:]
kind = config['component']
if kind == 'reporter':
    command = 'scan' if 'scan' in args else 'version'
elif kind == 'handoff':
    command = next((v for v in ('record', 'show', 'pickup', 'list') if v in args), 'version')
else:
    command = next((v for v in ('claim', 'release', 'transition', 'show', 'evidence', 'claim-admission') if v in args), 'version')
log = Path(config['log'])
with log.open('a') as f:
    f.write(json.dumps([kind, command]) + '\n')
fault = config.get('fault') if command == config.get('at') else None
if fault == 'oversize':
    sys.stdout.buffer.write(b'x' * 1100000)
    raise SystemExit(0)
if fault == 'stderr_overflow':
    sys.stderr.buffer.write(b'x' * 70000)
    raise SystemExit(0)
if fault == 'malformed':
    print('{')
    raise SystemExit(0)
if fault == 'signal':
    os.kill(os.getpid(), signal.SIGTERM)
if fault == 'exit74':
    raise SystemExit(74)
if fault == 'exit70':
    print('{"incomplete":"internal failure"}')
    raise SystemExit(70)
data = sys.stdin.buffer.read() if command == 'record' else None
p = subprocess.run([config['executable'], *args], input=data, capture_output=True)
if fault == 'lose_response':
    raise SystemExit(74)
if fault == 'wrong_count':
    value = json.loads(p.stdout)
    value['coverage']['worktrees_observed'] = True
    p.stdout = json.dumps(value).encode() + b'\n'
if fault == 'wrong_path_label':
    value = json.loads(p.stdout)
    value['worktrees'][0]['root']['path_utf8'] = '/unselected/display'
    p.stdout = json.dumps(value).encode() + b'\n'
if fault == 'missing_capability':
    value = json.loads(p.stdout)
    value['data']['capabilities'] = []
    p.stdout = json.dumps(value).encode() + b'\n'
sys.stdout.buffer.write(p.stdout)
sys.stderr.buffer.write(p.stderr)
raise SystemExit(p.returncode)
