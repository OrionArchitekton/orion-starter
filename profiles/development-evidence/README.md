# Development evidence preview

This optional Orion Starter 0.3.0-rc.1 profile demonstrates one local handover across PM, Handoff, Results and Worktree Report. Its goal is to capture and independently re-observe a deliberate dirty-path overlap. A completed demo says nothing about merge safety or repaired edits.

The profile is manually invoked and needs no browser, npm, systemd, account, provider key or agent hook. Initial native qualification is CPython 3.11 on Linux x86_64 under WSL2 with local ext4, Git 2.43.0 and linked SQLite 3.45.1. Other operating systems, network filesystems, cross-host execution and native Claude/Codex/Grok/Dot integration are unverified. This candidate remains private pending package review.

## Install the four selected packages

Start in the extracted distribution root. Use an empty `.private` directory, CPython 3.11 with venv support and Git. The installer and wheels are downloaded from their original public release locations and verified before execution. The four packages declare no Python runtime dependencies. Downloads and the environment are separate from the private demonstration data.

```bash
set -euo pipefail
umask 077
python3.11 -I -B scripts/check_profile.py
python3.11 -I -B - <<'PY'
from pathlib import Path
import hashlib, json, subprocess, sys, urllib.request, zipfile
root = Path.cwd().resolve()
if sys.version_info[:2] != (3, 11):
    raise SystemExit('CPython 3.11 is the selected interpreter')
private = root / '.private'
if private.exists():
    raise SystemExit('Choose a fresh extraction; .private already exists')
private.mkdir(mode=0o700)
downloads = private / 'downloads'
downloads.mkdir(mode=0o700)
manifest = json.loads((root / 'profiles/development-evidence/manifest.json').read_bytes())
def download(url, filename, checksum):
    raw = urllib.request.urlopen(url, timeout=60).read(32 * 1024 * 1024 + 1)
    if len(raw) > 32 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != checksum:
        raise SystemExit('Artifact verification failed')
    path = downloads / filename
    path.write_bytes(raw)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names) or any(Path(n).is_absolute() or '..' in Path(n).parts for n in names):
            raise SystemExit('Unsafe wheel members')
        if sum(x.file_size for x in archive.infolist()) > 64 * 1024 * 1024:
            raise SystemExit('Expanded artifact limit')
    return path
for package in manifest['components']:
    path = download(package['url'], package['url'].rsplit('/', 1)[1], package['sha256'])
    with zipfile.ZipFile(path) as archive:
        metadata = archive.read(next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))).decode()
        if 'Requires-Dist:' in metadata:
            raise SystemExit('Unexpected runtime dependency')
pip_name = 'pip-26.2.1-py3-none-any.whl'
pip_url = 'https://files.pythonhosted.org/packages/f3/6e/1736e5b4ae2b778ef2f81c47d797de9f891d4d8acb047a24ca37a60294dd/' + pip_name
pip_wheel = download(pip_url, pip_name, '71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e')
installer = private / 'installer'
with zipfile.ZipFile(pip_wheel) as archive:
    archive.extractall(installer)
environment = private / 'evidence-venv'
subprocess.run([sys.executable, '-I', '-m', 'venv', '--without-pip', str(environment)], check=True)
subprocess.run([sys.executable, '-I', str(installer / 'pip'), '--isolated', '--python', str(environment / 'bin/python'),
                'install', '--require-hashes', '--no-index', '--no-deps', '--find-links', str(downloads),
                '-r', str(root / 'profiles/development-evidence/requirements.lock')], check=True)
print('Verified isolated installation; no estate or account state selected.')
PY
```

## Prepare a synthetic run

Fixture setup is separate from inspection. It creates a new private directory outside Git, one PM task, a Handoff store, an empty Results parent and three registered Git worktrees. Two workers deliberately edit the same tracked file. Nothing selects an existing working repository by default. Keep the printed `DEMO_ROOT` for the later terminal.

```bash
set -euo pipefail
umask 077
export DEMO_ROOT="$(mktemp -d /tmp/starter-evidence.XXXXXXXX)"
.private/evidence-venv/bin/python -I -B - <<'PY'
from pathlib import Path
import hashlib, json, os, subprocess, sys, uuid
root = Path(os.environ['DEMO_ROOT'])
if not root.is_absolute() or root.is_symlink() or root.resolve() != root or any(root.iterdir()):
    raise SystemExit('Select an empty real private workspace')
if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o777 != 0o700:
    raise SystemExit('Workspace must be owned and mode 0700')
binary = Path(sys.executable).parent
env = {'PATH': str(binary) + ':/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()
def save(path, value):
    with path.open('xb') as f:
        f.write(encode(value) + b'\n')
    path.chmod(0o600)
def command(argv):
    return subprocess.check_output(list(map(str, argv)), env=env, stderr=subprocess.PIPE)
def pm(*args):
    return json.loads(command([binary / 'orion-pm', '--json', '--home', root / 'pm', *args]))['data']
run_id = str(uuid.uuid4())
task_id = 'evidence-' + run_id.replace('-', '')
save(root / 'projects.json', {'schema_version': 1, 'projects': [{'id': 'sample'}]})
pm('init', '--projects', root / 'projects.json')
task = pm('add', '--id', task_id, '--project', 'sample', '--status', 'todo',
          '--title', 'Demonstrate exact worktree evidence continuation')
command([binary / 'orion-handoff', '--json', '--store', root / 'handoff', 'init'])
(root / 'results').mkdir(mode=0o700)
repo = root / 'repo'
def git(*args, where=repo):
    return command(['git', '-C', where, '-c', 'user.name=Synthetic Worker', '-c',
                    'user.email=worker@example.invalid', '-c', 'core.hooksPath=/dev/null', *args])
git('init', '-b', 'main', repo, where=root)
(repo / 'shared.txt').write_text('baseline\n')
git('add', 'shared.txt')
git('commit', '-m', 'Synthetic baseline')
for index in range(2):
    tree = root / ('worker-' + str(index))
    git('worktree', 'add', '-b', 'worker-' + str(index), tree)
    (tree / 'shared.txt').write_text('deliberate worker edit ' + str(index) + '\n')
fields = {k: task['task'].get(k) for k in ('id', 'project', 'title', 'description', 'next_action')}
selection = {'selection_version': 1, 'profile': 'development-evidence', 'goal': 'capture-and-reobserve-overlap',
 'run_id': run_id, 'workspace': str(root),
 'pm': {'executable': str(binary / 'orion-pm'), 'home': str(root / 'pm'), 'store_id': task['store_id'],
        'task_id': task_id, 'task_definition_sha256': hashlib.sha256(encode(fields)).hexdigest()},
 'handoff': {'executable': str(binary / 'orion-handoff'), 'store': str(root / 'handoff')},
 'results': {'root': str(root / 'results'), 'limits': {'max_input_bytes': 1048576, 'max_results': 1,
             'max_payload_bytes': 1048576, 'inline_bytes': 4000}},
 'reporter': {'executable': str(binary / 'orion-worktree-report'), 'repositories': [str(repo)]}}
save(root / 'selection.json', selection)
print('DEMO_ROOT=' + str(root))
PY
```

## Produce, then continue in another process

Inspection is read-only. Produce claims the selected task, scans the worktrees, retains the exact stdout including its final LF, verifies public readback, records compact context and guarded-releases the task. A successful `yielded` reply and `yield.json` bind that observation and context. Normal output contains metadata, not filenames or raw reports.

```bash
set -euo pipefail
: "${DEMO_ROOT:?Use the synthetic workspace printed above}"
.private/evidence-venv/bin/python -I -B profiles/development-evidence/run.py inspect --selection "$DEMO_ROOT/selection.json"
.private/evidence-venv/bin/python -I -B profiles/development-evidence/run.py produce --selection "$DEMO_ROOT/selection.json"
```

In a fresh terminal, return to this same extracted distribution and set `DEMO_ROOT` to the exact printed workspace. Continue reads the selected receipt, validates the current context and recovers the historical bytes before attempting a new task claim. It captures a separate current observation before completion. Only a fresh complete positive overlap satisfies this synthetic goal.

```bash
set -euo pipefail
: "${DEMO_ROOT:?Set the exact existing demonstration workspace}"
.private/evidence-venv/bin/python -I -B profiles/development-evidence/run.py continue --selection "$DEMO_ROOT/selection.json" --yield-receipt "$DEMO_ROOT/yield.json"
```

## Incomplete coverage is retained, not upgraded

For a second run, repeat only the synthetic-setup block to obtain a fresh workspace. Before produce, add a missing explicit repository as below. The producer can yield its partial positive observation. The consumer retains its own partial observation, refuses completion and releases only its own unchanged claim.

```bash
set -euo pipefail
.private/evidence-venv/bin/python -I -B - <<'PY'
from pathlib import Path
import json, os
root = Path(os.environ['DEMO_ROOT'])
path = root / 'selection.json'
selection = json.loads(path.read_bytes())
selection['reporter']['repositories'].append(str(root / 'missing-repository'))
path.write_text(json.dumps(selection) + '\n')
PY
.private/evidence-venv/bin/python -I -B profiles/development-evidence/run.py produce --selection "$DEMO_ROOT/selection.json"
set +e
.private/evidence-venv/bin/python -I -B profiles/development-evidence/run.py continue --selection "$DEMO_ROOT/selection.json" --yield-receipt "$DEMO_ROOT/yield.json"
outcome=$?
set -e
test "$outcome" -eq 3
```

## Inspect an attempt without replaying it

Exit 2 means invalid input; 3 means established refusal or an unmet goal; 7 means unknown/unavailable and calls for reconciliation. Do not rerun a possibly committed operation. The failed reply's `attempt_id` selects the exact `receipts/<attempt_id>/attempt.json`. Run `reconcile --selection ... --attempt-receipt ...` against it. A reconciled diagnostic does not resume the old attempt or manufacture a yield/completion receipt.

This executable example reconciles the producer's exact recorded attempt from the walkthrough. It also works after the later consumer has completed; observed current state remains distinct from the historical attempt.

```bash
set -euo pipefail
attempt_id="$(.private/evidence-venv/bin/python -I -B -c 'import json,sys; print(json.load(open(sys.argv[1]))["producer_attempt_id"])' "$DEMO_ROOT/yield.json")"
.private/evidence-venv/bin/python -I -B profiles/development-evidence/run.py reconcile --selection "$DEMO_ROOT/selection.json" --attempt-receipt "$DEMO_ROOT/receipts/$attempt_id/attempt.json"
```

A lost create response leaves its known result slot unresolved, with no guessed session ID. A lost capture response can retain a known native reference; read-only reconciliation may establish its exact bytes. Missing/corrupt/incomplete data, changed identities or an unverified response never imply success. See the [recovery runbook](../../docs/runbooks/starter-development-evidence.md) before any explicit native repair or new attempt.

## Quiescent backup and environment removal

After all profile/helper processes for this selected run have exited, copy the selected closed component data as a set. Do not call a live SQLite file copy a backup. The following copies the producer's closed Results slot and verifies the exact reference through the same installed public API. It deliberately refuses an existing backup directory. PM and Handoff have separate backup/restore rules in their released documentation; their identities must be preserved together with the selection and receipts for a full run restore.

```bash
set -euo pipefail
.private/evidence-venv/bin/python -I -B - <<'PY'
from pathlib import Path
import json, os, shutil
from orion_results import read
root = Path(os.environ['DEMO_ROOT'])
receipt = json.loads((root / 'yield.json').read_bytes())
source = root / 'results' / receipt['result']['slot']
backup = root / 'closed-results-backup'
if backup.exists() or source.is_symlink():
    raise SystemExit('Select an unused backup destination and real source')
shutil.copytree(source, backup)
reference = receipt['result']['reference']
if read(source, reference) != read(backup, reference):
    raise SystemExit('Restored exact-reference readback failed')
print('Closed Results backup exact-reference readback verified.')
PY
python3.11 -I -B - <<'PY'
from pathlib import Path
import json, os, shutil
root = Path.cwd().resolve()
manifest = json.loads((root / 'manifest.json').read_bytes())
environment = root / '.private/evidence-venv'
if manifest['distribution'] != 'orion-starter' or environment.is_symlink() or environment.stat().st_uid != os.getuid():
    raise SystemExit('Unexpected selected environment')
shutil.rmtree(environment)
print('Removed only the selected environment; private demonstration data remains.')
PY
```

Retained observations can contain private repository paths and filenames. Removing the environment does not delete them, the fixture, PM state, Handoff context, receipts, downloads or backups. Review the exact printed temporary parent before any deliberate disposal. The profile adds no cleanup command, automatic adoption or background service.
