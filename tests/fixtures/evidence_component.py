"""Controlled faults around a real selected public command, for process-seam tests."""
import json
import base64
import copy
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
if fault in ('replace_claim', 'change_context'):
    home = config['pm_home']
    pm = config['pm_executable']
    def native_pm(*tail):
        out = subprocess.check_output([pm, '--json', '--home', home, *tail])
        return json.loads(out)['data']
    current = native_pm('show', config['task_id'])
    if fault == 'replace_claim':
        c = current['claim']
        native_pm('release', config['task_id'], '--holder', c['holder'], '--generation', c['generation'],
                  '--expect-revision', current['task']['revision'])
        native_pm('claim', config['task_id'], '--holder', 'successor', '--ttl-hours', '1')
    else:
        receipt = json.loads(Path(config['yield_path']).read_bytes())
        handoff = [config['handoff_executable'], '--json', '--store', config['handoff_store']]
        row = json.loads(subprocess.check_output([*handoff, 'show', receipt['context']['record_id']]))['data']['record']
        old = row.pop('record_id')
        row.pop('created_at')
        row['predecessor'] = old
        row['request_id'] = __import__('uuid').uuid4().hex
        row['last_observed_outcome'] = 'New context invalidates the prior exact tip.'
        subprocess.run([*handoff, 'record', '--input', '-'], input=json.dumps(row).encode(), capture_output=True, check=True)
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
if fault == 'foreign_repository':
    value = json.loads(p.stdout)
    foreign_id = 'sha256:' + 'f' * 64
    def fake_path(text):
        return {'path_b64': base64.b64encode(text.encode()).decode(), 'path_utf8': text}
    repository = copy.deepcopy(value['repositories'][0])
    repository['repository_id'] = foreign_id
    repository['common_directory'] = fake_path('/unselected/repository/.git')
    value['repositories'].append(repository)
    original = next(tree for tree in value['worktrees'] if tree['dirty_paths'])
    pair = []
    for marker in ('d', 'e'):
        tree = copy.deepcopy(original)
        tree['repository_id'] = foreign_id
        tree['worktree_id'] = 'sha256:' + marker * 64
        tree['root'] = fake_path('/unselected/repository/' + marker)
        pair.append(tree['worktree_id'])
        value['worktrees'].append(tree)
    overlap = copy.deepcopy(config['overlap_template'])
    overlap.update(id='sha256:' + 'c' * 64, repository_id=foreign_id, worktree_ids=sorted(pair))
    value['overlaps'] = [overlap]
    for key in ('repositories_selected', 'repositories_discovered'):
        value['coverage'][key] += 1
    for key in ('registered_worktrees', 'worktrees_observed'):
        value['coverage'][key] += 2
    value.update(conclusion='overlap_observed', exit=1)
    p.returncode = 1
    p.stdout = json.dumps(value).encode() + b'\n'
if fault == 'missing_capability':
    value = json.loads(p.stdout)
    value['data']['capabilities'] = []
    p.stdout = json.dumps(value).encode() + b'\n'
if fault == 'boolean_store_format':
    value = json.loads(p.stdout)
    value['data']['store_format_version'] = True
    p.stdout = json.dumps(value).encode() + b'\n'
sys.stdout.buffer.write(p.stdout)
sys.stderr.buffer.write(p.stderr)
raise SystemExit(p.returncode)
