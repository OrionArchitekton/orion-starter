# PM + browser + Handoff continuity preview

Orion starter 0.2.0-rc.1. One worker yields observed context; another obtains its own task claim and browser lease before continuing. Components remain independently usable.

Support is limited to the CPython 3.11, Linux x86_64, systemd-user environment in the release receipt, with native proof on WSL2/ext4. This preview does not establish native Windows/macOS, account access, cross-host fencing, vendor hooks or stable newcomer onboarding.

## Install the profile

Start at the extracted distribution root. Verify the archive against the reviewed external release checksum first. Installation creates no stores, services or harness configuration.

```bash
set -euo pipefail
python3.11 -m venv .venv
.venv/bin/python -m pip install --require-hashes --force-reinstall -r bootstrap-requirements.txt
.venv/bin/python -m pip install --require-hashes -r profiles/continuity/requirements.lock
npm ci --prefix driver
python3 scripts/check_profile.py
.venv/bin/orion-pm --json version
.venv/bin/orion-handoff --json --version
.venv/bin/orion-browser --version
driver/node_modules/.bin/agent-browser --version
```

Chrome, systemd and browser system packages are separate prerequisites under their own licenses. Follow the pinned browser release's documentation; nothing here installs OS packages. Use a shell with no inherited `ORION_BROWSER_*` or `AGENT_BROWSER_*` overrides. A missing prerequisite, collision or failed command stops the recipe.

## Explicit synthetic setup

Choose a free screen from 10–99. This example uses 84; change it if occupied. Setup checks its X socket and loopback ports, then creates only the selected synthetic stores/configuration. Do not repeat setup in a partly initialized directory after an error; inspect first.

```bash
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
test -S "$XDG_RUNTIME_DIR/bus"
systemctl --user is-active default.target
DEMO_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/starter-continuity.XXXXXXXX")
export DEMO_ROOT
export DEMO_SCREEN=84
.venv/bin/python - <<'PY'
from pathlib import Path
import hashlib, json, os, socket, subprocess, uuid
def check(condition, reason):
    if not condition:
        raise SystemExit(reason)
root = Path(os.environ['DEMO_ROOT']).resolve()
check(root.is_dir() and not list(root.iterdir()), 'workspace_not_empty')
check(not any(k.startswith(('ORION_BROWSER_', 'AGENT_BROWSER_')) for k in os.environ), 'inherited_browser_override')
screen = int(os.environ['DEMO_SCREEN'])
check(10 <= screen <= 99, 'screen_range')
check(not Path(f'/tmp/.X{screen}-lock').exists(), 'screen_lock_exists')
check(not Path(f'/tmp/.X11-unix/X{screen}').exists(), 'screen_socket_exists')
for port in (5900 + screen, 6080 + screen):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', port))
candidate = Path.cwd().resolve()
binary = candidate / '.venv/bin'
def save(path, value):
    path.write_text(json.dumps(value) + '\n')
    path.chmod(0o600)
def call(argv):
    result = subprocess.run(list(map(str, argv)), check=True, capture_output=True, text=True)
    value = json.loads(result.stdout)
    check(value['ok'] is True, 'component_setup_refused')
    return value['data']
save(root / 'projects.json', {'schema_version': 1, 'projects': [{'id': 'sample'}]})
pm = [binary / 'orion-pm', '--json', '--home', root / 'pm']
call([*pm, 'init', '--projects', root / 'projects.json'])
task = call([*pm, 'add', '--id', 'continuity-demo', '--title', 'Read the synthetic page twice',
             '--project', 'sample', '--status', 'todo'])
call([binary / 'orion-handoff', '--store', root / 'handoff', '--json', 'init'])
config = ('[paths]\nstate = ' + json.dumps(str(root / 'browser-state')) +
          '\nprofiles = ' + json.dumps(str(root / 'browser-profiles')) +
          '\n[[browser]]\nname = "contdemo"\nscreen = ' + str(screen) + '\nrestore_session = false\n')
(root / 'browser.toml').write_text(config)
(root / 'browser.toml').chmod(0o600)
save(root / 'agent.json', {})
digest = lambda raw: hashlib.sha256(raw).hexdigest()
definition = {k: task['task'].get(k) for k in ('id', 'project', 'title', 'description', 'next_action')}
selection = {
    'selection_version': 1, 'run_id': str(uuid.uuid4()), 'workspace': str(root),
    'pm': {'executable': str(binary / 'orion-pm'), 'home': str(root / 'pm'), 'store_id': task['store_id'],
           'task_id': 'continuity-demo', 'task_definition_sha256': digest(json.dumps(
               definition, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode())},
    'handoff': {'executable': str(binary / 'orion-handoff'), 'store': str(root / 'handoff')},
    'browser': {'executable': str(binary / 'orion-browser'), 'config': str(root / 'browser.toml'),
                'config_sha256': digest((root / 'browser.toml').read_bytes()), 'name': 'contdemo'},
    'client': {'executable': str(candidate / 'driver/node_modules/.bin/agent-browser'),
               'config': str(root / 'agent.json'), 'config_sha256': digest((root / 'agent.json').read_bytes())}}
save(root / 'selection.json', selection)
print('Created isolated selection; no browser has started.')
PY
ORION_BROWSER_CONFIG="$DEMO_ROOT/browser.toml" .venv/bin/orion-browser --json setup
.venv/bin/python examples/continuity_starter.py --selection "$DEMO_ROOT/selection.json" inspect
```

The explicit browser setup checks dependencies and prepares owned directories. Later producer/consumer modes start only this anonymous browser's transient resources. Inspect acquires no claims and makes no browser lifecycle calls.

## Observe, then yield

```bash
.venv/bin/python examples/continuity_starter.py --selection "$DEMO_ROOT/selection.json" produce
.venv/bin/orion-pm --json --home "$DEMO_ROOT/pm" show continuity-demo
```

Expect `yielded`, task `todo`, claim `absent`. The producer reads only `https://example.com/`, proves clean native release and client close, records an exact Handoff revision, then guarded-releases PM. Its private `yield.json` stays under the selected workspace. Recording alone is insufficient for a successful yield.

## Continue independently

In a second terminal, select the same candidate and explicitly set `DEMO_ROOT` to the directory above. Review the current request and synthetic goal. Do not copy a holder or generation.

```bash
.venv/bin/python examples/continuity_starter.py --selection "$DEMO_ROOT/selection.json" \
  continue --yield-receipt "$DEMO_ROOT/yield.json"
.venv/bin/orion-pm --json --home "$DEMO_ROOT/pm" show continuity-demo
if ORION_BROWSER_CONFIG="$DEMO_ROOT/browser.toml" .venv/bin/orion-browser --json status contdemo; then
  echo 'Unexpected running browser; inspect before proceeding.' >&2
  exit 1
else
  test "$?" -eq 6
fi
```

Expect `completed`, PM `done`/claim `absent`, and the browser's expected exit 6, `BROWSER_DOWN`, state down/no holder. Consumer evidence comes from its own observation and clean release. Two simultaneous consumers produce one winner; the losing claimant makes zero browser lifecycle/navigation calls. A version preflight is not resource ownership.

Stale/changed/ambiguous context and wrong goal/store/record identities refuse continuation. There is no older-record or project-selection fallback. Handoff prose and acceptance claims are data; they grant no permission to execute next steps.

## Recover and remove

Profile exits: 0 establishes only the named inspected/yielded/completed state; 2 means invalid invocation, 3 established refusal, and 7 reconciliation required. Components retain separate exit/envelope meanings. Request IDs do not make operations idempotent.

After interruption, timeout, lost acknowledgement, unclean release or receipt failure, preserve the workspace. Inspect the responsible component before another intentional attempt; never blindly replay a possibly committed operation. Private operation receipts identify known handles and uncertainty, not a cross-component transaction journal. Follow the [recovery runbook](../../docs/runbooks/starter-continuity.md).

PM coordinates cooperating clients on one host. Expiry does not stop old processes; sequential checks do not provide atomic fencing. Browser status exposes holder/expiry/health, while the session comes from its lease grant. Hostile same-user isolation and cross-host guarantees are excluded.

After successful cleanup and desired receipt retention, remove only this disposable workspace, `.venv` and `driver/node_modules`. Reconcile unknown resources/claims first. OS packages, other profiles/stores, accounts and the prior RC2 archive remain separately owned. There is no automatic migration, cleanup timer or estate installation step.
