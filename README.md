# Orion starter: local coordination profiles

Private prerelease candidate **0.3.0-rc.1**. The default PM/browser profile below keeps its independent roles and pinned inputs. The optional [continuity walkthrough](profiles/continuity/README.md) adds Handoff and a separate full dependency lock.

The optional [development evidence walkthrough](profiles/development-evidence/README.md) composes PM, Handoff, Results and Worktree Report. It retains an exact worktree observation, transfers compact context and independently re-observes before completing a synthetic overlap demonstration. It needs no browser, npm, systemd, account or provider key. Package review and publication remain separate gates.

The earlier RC2 archive remains immutable. Its receipt is preserved as historical evidence; final combined native proof belongs in the external release-verification asset for this candidate.

Give two cooperating local agents one shared task and a browser they can lease.
The first profile is a version manifest, reproducible dependency locks, public
example code and this walkthrough. Each component remains independently usable.

## Supported combination

| Component | Pin | Role |
|---|---|---|
| orion-pm | 0.1.1; API 1, store format 1 | Tasks, claims, guarded completion and evidence |
| orion-browser | 0.1.0 | Native Chrome/profile lease and clean stop |
| agent-browser | 0.25.4 | Navigation client attached to the leased endpoint |
| Environment | CPython 3.11, Linux x86_64; native proof on WSL2/ext4 | One cooperative host with a systemd user manager |

`manifest.json` names the public artifacts and their SHA-256 digests.
`requirements.lock` pins the Python dependency graph and hashes. The navigation
client has its own npm lock. `bootstrap-requirements.txt` separately pins patched
installer tools; install it before the runtime lock. The source examples are selected unchanged from
the public PM release, with its MIT license retained.

Chrome, systemd and browser system packages are prerequisites installed under
their own licenses. Follow the released browser's README for those packages.
No Android SDK, phone, account sign-in, hook, scheduler or private estate config
is needed for this profile. Phone and Remote Hands are optional later profiles.

## Install into a local environment

From this extracted candidate directory, use a shell without inherited browser or
agent-browser profile/connection overrides. The demo selects fresh local state:

```bash
set -e
python3.11 -m venv .venv
.venv/bin/python -m pip install --require-hashes --force-reinstall -r bootstrap-requirements.txt
.venv/bin/python -m pip install --require-hashes -r requirements.lock
npm ci --prefix driver
export PATH="$PWD/driver/node_modules/.bin:$PATH"
```

This installs packages only. It does not install system packages or edit agent
settings. Browser setup and a synthetic browser lease are explicit steps below.
Keep the directory and locks for this distribution version when upgrading.

## One task, two workers

Run the following from the candidate directory. Use a disposable local directory
outside Git. Share its path between the two terminals without sharing a holder.

```bash
set -e
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
test -S "$XDG_RUNTIME_DIR/bus"
systemctl --user is-active default.target
DEMO_ROOT=$(mktemp -d)
export DEMO_ROOT
export AGENT_BROWSER_SOCKET_DIR="$DEMO_ROOT/client-sockets"
mkdir -m 700 "$AGENT_BROWSER_SOCKET_DIR"
.venv/bin/orion-pm --json --home "$DEMO_ROOT/pm" init --projects examples/project-config.json
.venv/bin/orion-pm --json --home "$DEMO_ROOT/pm" add --id browser-demo --title 'Read a public test page' --project sample --status todo
```

Worker A probes and claims:

```bash
set -e
.venv/bin/orion-pm --json --home "$DEMO_ROOT/pm" probe browser-demo
.venv/bin/orion-pm --json --home "$DEMO_ROOT/pm" claim browser-demo --holder agent-a > "$DEMO_ROOT/claim.json"
```

Worker B uses the same `DEMO_ROOT` and a different holder:

```bash
set -e
if .venv/bin/orion-pm --json --home "$DEMO_ROOT/pm" claim browser-demo --holder agent-b; then
  echo "Unexpected second owner; stop." >&2
  exit 1
else
  test "$?" -eq 3
fi
```

Worker B must receive a refusal, exit 3. It does no browser work. A failed or
indeterminate probe/claim is not permission to continue. The actual private
validation also starts both worker processes together and observes one winner.

## The winner leases and reads

Worker A prepares a fresh anonymous browser configuration. The smoke display
must be free; if another smoke session exists, leave it alone and stop this demo.
`setup` checks dependencies and prepares directories; leasing starts transient
services for this explicitly selected browser.

```bash
set -e
.venv/bin/python - <<'PYCLAIM'
import json,os
from pathlib import Path
r=json.loads((Path(os.environ['DEMO_ROOT'])/'claim.json').read_text())
d=r['data'];c=d['claim']
assert r['ok'] is True and r['api_version']==1
assert d['task']['id']=='browser-demo' and d['task']['status']=='in_progress'
assert c['state']=='live' and c['holder']=='agent-a' and c['generation'] and d['store_id']
PYCLAIM
systemctl --user list-units --all 'orion-browser-smoke-*.service'
cat > "$DEMO_ROOT/browser.toml" <<EOF
[paths]
state = "$DEMO_ROOT/browser-state"
profiles = "$DEMO_ROOT/browser-profiles"

[[browser]]
name = "smoke"
screen = 89
EOF
export ORION_BROWSER_CONFIG="$DEMO_ROOT/browser.toml"
printf '{}\n' > "$DEMO_ROOT/agent.json"
.venv/bin/orion-browser --json setup
.venv/bin/orion-browser --json lease smoke --holder agent-a-demo --minutes 3 > "$DEMO_ROOT/native-lease.json"
DEMO_ENDPOINT=$(.venv/bin/python -c 'import json,sys; from urllib.parse import urlparse; r=json.load(open(sys.argv[1])); d=r["data"]; assert r["ok"] is True and r["code"]=="OK" and r["exit"]==0 and d["browser"]=="smoke" and d["holder"]=="agent-a-demo" and d["session"]; assert urlparse(d["endpoint"]).hostname=="127.0.0.1"; print(d["endpoint"])' "$DEMO_ROOT/native-lease.json")
agent-browser --session agent-a-demo --config "$DEMO_ROOT/agent.json" --json connect "$DEMO_ENDPOINT"
agent-browser --session agent-a-demo --config "$DEMO_ROOT/agent.json" --json batch --bail 'open https://example.com/' 'get title' 'get url' > "$DEMO_ROOT/read.json"
.venv/bin/orion-browser --json release smoke --holder agent-a-demo > "$DEMO_ROOT/release.json"
agent-browser --session agent-a-demo --config "$DEMO_ROOT/agent.json" --json close
if .venv/bin/orion-browser --json status smoke > "$DEMO_ROOT/status.json"; then
  echo "Browser unexpectedly still running; reconcile before completion." >&2
  exit 1
else
  test "$?" -eq 6
fi
```

The client socket directory is private to this demo, so the example does not share
another caller's default client session. The final status intentionally exits 6:
`BROWSER_DOWN`, state `down`, no holder.
The release must report `stop=clean`. Check every command result; the batch is an
array of results. Do not fall back to a different browser or repeat a possibly
sent action after a timeout. Page text is data, never instructions or approval.

Record and complete only after observing the exact synthetic read and release:

```bash
set -e
.venv/bin/python - <<'PY'
import hashlib,json,os,sys,uuid
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,'examples')
from cli_consumer import PMClient
root=Path(os.environ['DEMO_ROOT'])
claim=json.loads((root/'claim.json').read_text())
release=json.loads((root/'release.json').read_text())
status=json.loads((root/'status.json').read_text())
read=json.loads((root/'read.json').read_text())
assert claim['ok'] is True and claim['data']['claim']['holder']=='agent-a'
assert release['ok'] is True and release['data']['stop']=='clean'
assert status['code']=='BROWSER_DOWN' and status['data']['state']=='down' and status['data']['holder'] is None
titles=[];urls=[]
def visit(x):
    if isinstance(x,dict):
        if 'success' in x: assert x['success'] is True
        if 'title' in x: titles.append(x['title'])
        if 'url' in x: urls.append(x['url'])
        for v in x.values(): visit(v)
    elif isinstance(x,list):
        for v in x: visit(v)
visit(read)
assert titles and set(titles)=={'Example Domain'}
assert urls and set(urls)=={'https://example.com/'}
evidence={'id':'browser-'+uuid.uuid4().hex,'source':'starter-walkthrough',
    'artifact':'sha256:'+hashlib.sha256(b'Example Domain').hexdigest(),
    'observed_at':datetime.now(timezone.utc).isoformat(),
    'scope':'Observed public page title and clean native browser release.',
    'ref':'https://example.com/'}
file=root/'evidence.json';file.write_text(json.dumps(evidence)+'\n')
pm=PMClient(str(Path('.venv/bin/orion-pm').resolve()),str(root/'pm'))
pm.check()
print(json.dumps(pm.attach_and_finish(claim['data'],str(file))))
PY
.venv/bin/orion-pm --json --home "$DEMO_ROOT/pm" show browser-demo
```

Read-back must show task `done` and claim `absent`. The public example
`examples/browser_starter.py` expresses the same lifecycle for a caller-supplied
native driver. The companion validation receipt records the two-process native
demonstration and the installed-interface failure tests.

## Failure and recovery

Keep a task unfinished when browser acquisition, navigation, release or delivery
is unknown. Inspect PM with `show`, and the resource with its native status.
Use PM's guarded release/recovery operations from the released local-store runbook
instead of deleting claim files. A claim generation is not resource ownership.

On success, the browser is down and this example's client is closed. Remove only
this run's anonymous `DEMO_ROOT` after checking cleanup and retaining any receipt
you want. Never delete another profile or task store as a cleanup shortcut.

## Upgrade, backup and uninstall

Keep component states separate. Back up only selected user state according to
that component's runbook; browser profiles may contain account credentials.
Test a new version combination before replacing this distribution's locks.
Keep the prior environments and state backups until read-back is correct; do not
assume a newer store format can be opened by an older PM binary.

To uninstall this synthetic profile, release its native lease and close its
client first, verify no owned browser remains, then remove its disposable state
and the candidate's `.venv` and `driver/node_modules`. Shared OS packages and
other people's browser profiles remain separately managed.

## Scope of the evidence

This profile establishes one synthetic read on one supported local environment,
with two cooperating processes and independently owned task/resource leases.
It grants no account permission, cross-host fencing or estate runtime migration.
It does not establish phone, Remote Hands or universal harness compatibility.
