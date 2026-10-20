# Starter development evidence profile

Status: **private implementation authorized**, October 19, 2026 (Pacific). Publication and estate runtime adoption remain unapproved. Proposed distribution version: **0.3.0-rc.1**, explicitly a preview. Profile name: **development-evidence**.

## Outcome and scope

Two cooperating local workers retain the exact observations behind a task handoff. The producer claims a selected demonstration task, observes explicitly selected Git worktrees, captures the complete report in a private Results session, verifies it, records compact Handoff context and yields the unfinished task. A separately invoked consumer validates that exact context, obtains a different live task claim, recovers the historical bytes, independently observes current worktrees and completes only the demonstration's stated goal.

The fixed demonstration goal is **capture and independently re-observe a deliberately created dirty-path overlap**. A complete positive report is expected. Finishing this demonstration never means the branches are merge-safe, edits were repaired or a file lock exists. A yielded report may instead be partial or unavailable; it remains useful diagnostic context, and its limitations must survive capture and pickup. Task completion still requires the consumer's fresh complete positive observation.

The optional profile composes PM 0.1.1, Handoff 0.1.0, Results 0.1.0 and Worktree Report 0.1.0. Use the installed public commands for PM/Handoff/Worktree Report and the installed public Results Python API. No component implementation imports or direct component-store edits are permitted. The profile is not another foundational library, daemon, approval service or shared SDK.

Existing PM/browser and PM/browser/Handoff profiles remain available with unchanged component pins and workflow semantics. The new profile needs no browser, npm client, phone, account, desktop bridge, hook, systemd manager, provider key or estate state. It performs no repository edits, cleanup/prune/merge preview, cross-host execution, automatic claim takeover or native agent integration.

## Domain vocabulary and ownership

| Term | Meaning |
|---|---|
| Selection | Caller-selected configuration for one demonstration run, task/store identities, component locations, private state roots and repository roots. |
| Attempt | One produce or continue invocation, with its own UUID and holder. It is not a retry token or task identity. |
| Observation | One complete emitted worktree-report object and its process exit, scan identity, scope and as-of times. Complete output does not necessarily mean complete coverage. |
| Capture | Results' committed retention of the exact report text, identified by its native reference and verified by readback. |
| Result slot | A profile-owned attempt UUID selecting one child of the caller's Results root. It is a location mapping, not a Results store ID or authorization token. |
| Context record | One immutable Handoff record and digest binding the selected task, observation and capture. It transfers no claim. |
| Yield receipt | Profile-owned evidence identifying a verified context record/capture and an observed PM yield. |
| Operation receipt | Bounded private intent/outcome metadata for one attempted operation. It is not an atomic cross-component journal or authoritative event log. |

Use **observation**, **capture**, **context record** and **yield receipt** for these distinct concepts; do not use an undifferentiated "result" to imply all four succeeded. PM owns task revisions, claims and evidence. Results owns retained text and its session lifecycle. Handoff owns context records and pickup assessments. Worktree Report owns the observation contract. The profile owns only its explicit selection, private input/output files and receipts.

## Selection and isolation

Selection version 1 has exactly these logical sections: profile/run identity, a private workspace, PM selection, Handoff selection, Results selection and reporter selection. The profile identity is `development-evidence`; the goal is `capture-and-reobserve-overlap`. Reject missing sections, unknown keys, duplicate keys, non-finite values, invalid UTF-8 and unsupported versions. There are no home-directory, environment, latest-record, provider-session or project-title fallbacks.

The run ID is a canonical UUID4. PM selection names an absolute installed command, an explicit private home, its observed store ID, the exact task ID and the task-definition digest. Handoff selection names its absolute command and explicit store. Results selection names a private parent root and the limits below; its API runs with the profile's selected virtual-environment interpreter. Reporter selection names its absolute installed command and one to eight explicit absolute UTF-8 repository roots. A component location is trusted caller configuration, never content read from Handoff.

The workspace is outside Git, owned by the current user and mode 0700. Its component states and receipt directories are separate children with no ancestor/descendant overlap. Writable profile files are regular, single-link, mode 0600; directories are 0700 regardless of umask. Reject symlink traversal and unexpected existing attempt paths. Preserve other owners' permissions/state rather than repairing or adopting them. Executable/environment files are separately trusted installed artifacts and need not live inside the workspace.

Repository roots are explicit read selections; they may be outside the workspace in general use. Component state/receipts must not lie inside any selected Git working tree. The acceptance walkthrough uses only fresh synthetic repositories and registrations inside its disposable workspace. No normal estate repository or runtime store is a default or test input. The scanner's own supported scope and cooperative stable-configuration assumptions still apply.

Derive the task-definition digest from the public task fields `id`, `project`, `title`, `description` and `next_action`, normalizing absent optional values to null. Canonical JSON uses sorted keys, ASCII escaping, no extra whitespace, no non-finite values and no trailing LF. Status, claim, evidence and timestamps are excluded. A description is fingerprinted data, never instructions to execute. The documented fixture uses the title `Demonstrate exact worktree evidence continuation` and a fresh run-specific task ID; other task goals are outside this recipe.

The repository-selection digest covers the sorted deduplicated selected absolute root strings in canonical JSON. The selection digest covers the complete validated selection, including state mappings and component locations. These digests detect changes under cooperative use; they do not authenticate an actor or defend against an adversarial same-user replacement.

Derive the Handoff task key as `de1-` plus SHA-256 of canonical JSON for `["development-evidence",1,run_id,pm_store_id,pm_task_id]`. The project key is `starter-development-evidence-<run UUID>`. Exact task pickup is required; project resume and latest-record fallback are excluded. Handoff 0.1.0 exposes no store ID, so bind its selected canonical path through the selection digest without inventing stronger restoration detection.

## Invocation and observable result

One manually invoked profile entry point has four modes: **inspect**, **produce**, **continue**, and **reconcile**. Every mode takes an explicit selection. Continue takes an exact yield receipt; reconcile takes an exact existing attempt receipt. A caller invocation selects only this documented workflow; the profile never executes narrative instructions, arbitrary commands, network URLs or paths supplied by a context record.

Inspect checks selected versions/capabilities, task/store/definition and Handoff store availability. It creates no stores, sessions, claims, receipts or repository state. Reconcile reads existing profile receipts and public component state only; it creates no session, capture, context record, claim, renewal, release or transition. Their diagnostic reads never mean a failed attempt resumed or completed.

Each produce/continue attempt uses a new UUID and holder `dev-evidence-<attempt UUID without hyphens>`. PM claims use a one-hour native TTL. Before a scan, Results/context mutation or PM mutation, re-read the task/store/definition, require the exact live holder/generation, and require enough remaining lease time for the next bounded operation plus its termination grace. A changed/expired claim stops forward work; no automatic renewal, takeover, recovery or replay is provided. PM's native admission rules still apply.

Return one UTF-8 JSON object plus LF, at most 65,536 bytes. It has profile interface version 1, profile/mode/run/attempt identities, a state, failed operation when applicable, and separate task/observation/capture/context outcomes. Successful mode states are `inspected`, `yielded`, `completed` and `reconciled`; exit 0 means only that named state. Exit 2 is invalid invocation/configuration, 3 is established refusal or unmet demonstration acceptance, and 7 is an unknown/unavailable execution outcome requiring reconciliation. Diagnostic reconcile output may explicitly retain an unknown operation and exits 7 in that case. The demonstration's `completed` state is never inferred from process exit alone.

Raw reports, absolute roots, filenames, task prose and environment values are absent from normal profile stdout. It may contain opaque IDs, references, digests/byte counts, coverage/conclusion, timestamps and the bounded metadata-only snapshot. Those identifiers still warrant private handling. Diagnostic errors use fixed categories, not raw component stderr or exception text.

## Observation and capture contract

Require the exact pinned package versions, PM API/store format 1 and task/claim/transition/evidence/admission capabilities, Handoff interface/store/record version 1, Results reference format 1 and Worktree Report interface 1 with its declared inventory/dirty-path/coverage capabilities. A missing version or capability refuses the profile. No declared package interface is a promise of native harness or cross-host compatibility.

PM replies must match command, request ID, API version, selected store/task and operation-specific exit/envelope/outcome. Handoff replies are decoded separately: require expected command, `authority: none`, coherent code/exit and required data. It has no PM-style request envelope. A request ID correlates an attempt; it does not make a mutation idempotent.

Launch commands as argument arrays with only an explicitly selected PATH and the needed locale/temporary-directory values. Do not inherit Python import overrides, Git redirection/configuration, Orion state overrides, provider credentials or browser settings. Git itself remains a trusted executable on that PATH. Run the Results helper with isolated imports and bytecode writes disabled. Inspect/reconcile must not create a temporary directory merely to perform a read; writing modes may use their own private temporary child.

The reporter is invoked with its selected executable and argument array for `--json scan` plus the selected roots. Validate one complete public version-1 report and its cross-field exit/coverage/conclusion/count/path identities; do not import its internal validator or reproduce Git analysis. Keep exact Base64 filename identities distinct from display labels. Check the emitted selected inputs against this invocation. Reject malformed/duplicate/non-finite/excessively nested output and trailing material.

| Reporter outcome | Profile handling |
|---|---|
| Exit 0, complete, no overlap observed | Valid observation, capturable/yieldable; does not meet this demonstration's final positive-overlap goal. |
| Exit 1, complete, overlap observed | Valid positive observation. Nonzero is expected, not a subprocess failure. |
| Exit 3, partial | Valid incomplete observation, including a known positive subset or indeterminate absence. Preserve coverage/problems. |
| Exit 4, unavailable, indeterminate | Valid diagnostic observation, capturable/yieldable with explicit unavailable coverage. |
| Exit 2 | Invalid invocation; no successful producer yield. |
| Exit 70 | Internal execution failure; retain bounded private diagnostics, no successful yield/completion. |
| Exit 74, timeout, signal, output overflow or inconsistent bytes/envelope | Output/execution not established; no capture presented as a complete report, no successful yield/completion. |

The captured value is the exact decoded stdout text, including its final LF. UTF-8 re-encoding must reproduce every original byte; no whitespace normalization, reserialization or truncation. The native reference digest/length must equal that stdout digest/length. A report's scan ID/time remains historical after it is retained. The consumer's fresh scan has its own ID/time/capture and never overwrites or relabels the producer's capture.

Use the public Results API serially in an owned helper process, with no shared Session handles or simultaneous in-process storage calls. For each attempt reserve a fresh result slot, create one session, return/close it, and durably record its generated session ID before any capture. The API does not accept a caller-chosen session ID. If creation's response is lost, mark `session_creation_unknown`; leave that exact slot untouched and do not discover a guessed session by walking other stores. No capture has yet been requested.

Once the session ID is known, derive the expected public reference from the report text before capture and save it in the operation intent. Capture through Session.open/capture, obtain the native receipt, perform separate public exact readback, request a metadata-only snapshot and close the helper's Session. The parent verifies identity, digest/length, captured bytes and helper completion before proceeding. A metadata snapshot is not a substitute for readback. If a receipt/readback/close/response is indeterminate, preserve the expected reference and stop without recapturing. Reconciliation may inspect/read that exact known session/reference; any writable SQLite recovery is a separate explicit native operation.

### Fixed profile limits

| Surface | Limit |
|---|---|
| Selection / profile JSON / each operation metadata file | 65,536 bytes each; control JSON nesting at most 16. |
| Reporter stdout / stderr | 1,048,576 / 65,536 bytes, bounded while receiving. |
| PM stdout / Handoff stdout / Results helper response | 8 MiB / 512 KiB / 65,536 bytes; stderr 65,536 bytes each. |
| Handoff body / full encoded record | Profile body at most 4,096 bytes; native full record at most 65,536 bytes. |
| Results per-attempt session | max_input_bytes 1,048,576; max_results 1; max_payload_bytes 1,048,576; inline_bytes 4,000. |
| Selected snapshot | budget_bytes 4,096; include_content false. Applies only to Snapshot.text. |
| Reporter / PM-Handoff / Results helper deadline | 75 / 10 / 30 seconds per operation. |
| Attempt budget / owned process shutdown | 240 seconds monotonic budget; terminate own process group, allow 5 seconds, then kill/reap with 5 more seconds. |
| Profile receipts | At most 32 operations and 8 MiB of profile-owned files per attempt; component storage is governed separately. |

Budget checks precede launching an operation or writing its receipt; do not accumulate an overflowing stream. Reporter grammar/count limits and eight-root maximum remain those of the pinned component. Results quotas bound payload, not SQLite/disk overhead. Snapshot bytes do not bound the wrapper, tokens, earlier strings or a whole model context. These process deadlines cannot provide a hard wall-clock guarantee under host scheduling or uninterruptible I/O; a child not observed stopped remains unknown. Never kill unrelated Git, Python or agent processes.

Lower storage quotas are exercised as controlled acceptance faults, not a silent fallback profile. No selection flag disables validation, increases bounds or turns on inline report content.

## Context binding and workflow ordering

The Handoff body is canonical profile data with an exact shape: binding_version 1; profile, run and producer-attempt IDs; selection and repository-selection digests; PM store/task/definition identity; historical producer generation; result slot; native reference; report interface/package version, scan ID, stdout SHA-256/byte count, exit, coverage/conclusion and start/finish times. No component store path, full report or receipt path is taken from Handoff. Result slot is exactly the producer-attempt UUID, mapped only beneath the caller-selected Results root.

Structured context fields state what was actually observed, whether coverage was incomplete, the unfinished independent check and `remaining_authority: none; consult the current request`. One recorded acceptance claim uses baseline `starter-development-evidence-capture-v1`, the exact native result reference and actual successful capture/readback time. It accepts that retention event only, including when the retained observation is partial. It never accepts complete coverage or authorizes continuation. Evidence identifies the report digest/reference/as-of time and exact observation scope. Body metadata and structured claims/evidence must agree.

Producer ordering is strict:

1. Inspect the explicit selection; establish the fixed demonstration goal and current native claim admission.
2. Durably create a unique attempt intent, then claim the exact task and verify its live generation/definition.
3. Observe selected repositories; preserve validated raw report bytes privately and record their identity.
4. Create/identify the Results session, record expected reference before capture, capture and independently recover exact bytes; close the owned writer.
5. Recheck ownership; record Handoff with a fresh request ID and no predecessor; verify returned record ID/digest through show and require it is current.
6. Recheck ownership/definition; guarded-release with the exact generation and current revision; read back task todo/claim absent. Recheck the exact context tip.
7. Emit a successful yield receipt only after all those observations. The receipt binds the exact Handoff ID/digest and capture metadata, and observed yield. Failure to save that final receipt leaves handover delivery unknown even if components committed.

Consumer ordering is strict:

1. Read the exact selected yield receipt and selection. Exact-task pickup uses max_age_seconds 86,400, valid integrity, within-window recency, recorded capture acceptance, context_available and no reasons. Reject future times, changed/done/stale context, missing evidence, wrong identity or different selected tip. Validate show against the exact ID/digest and binding; never fall back to another revision.
2. Resolve only the explicit Results mapping and exact native reference; recover/validate the old bytes and binding. Missing, incomplete or corrupt data refuses progress. Retaining a reference alone is insufficient.
3. Claim with a fresh holder and generation different from the producer. Re-read definition, exact context tip/digest and prior capture after claiming. A losing/changed claimant stops before a fresh scan or component mutation.
4. Independently scan the same selected roots, retain a fresh capture through the same bounded process and verify it. Preserve both the historic and current observation identities, even if coverage or content changed.
5. Require current complete coverage and a positive dirty-path overlap for this demonstration. A fresh partial/unavailable/no-overlap report is retained and reported as unmet acceptance; it never produces `completed`.
6. Recheck ownership/definition/context; attach current evidence through PM using its native generation/revision guards, then re-read PM and the exact current context after attachment. Guarded-complete only with the current generation and returned revision. Read back done/claim absent and the exact evidence identity. Emit `completed` only then.

Producer acceptance is a verified handover, not complete task acceptance. A diagnostic partial report may be handed over and later followed by a complete fresh report. For negative cases the documented fixture explicitly introduces missing selections; ordinary acceptance uses only the selected synthetic fixtures. No mode removes the deliberately dirty paths.

## Refusal and interruption recovery

Before each mutation, write and fsync a private intent describing operation ID, command/category, exact selected identities, expected native reference or generation where known, and argument/input hashes. Atomically replace its outcome record after observing the component response. Do not launch if intent persistence fails. Record no raw report/prose in metadata. The raw report is a separate owned private file.

Unknown claim, capture, Handoff record, PM yield, evidence attachment or completion stops forward work. Reconcile observes the exact PM task and explicit Handoff/Results identities without repeating mutations. A lost Handoff response may be checked by exact task and the known request/binding; if the expected record cannot be uniquely established, it stays unknown. A successful native readback may establish what committed; reconcile does not manufacture a successful original yield/completion receipt or acquire ownership.

If the consumer retained a new incomplete report or lost ownership, leave the task unfinished. For an established refusal while still owning the exact live claim, the profile may guarded-release only that claim and observe todo/absent; release uncertainty is reconciliation_required. Never release a successor's claim. A lost final completion response is inspected through PM; done by another actor is observed state, not proof that this attempt completed it. No automatic retry of a possibly committed operation is provided.

A later caller may inspect/repair the component through its native documented recovery and then start a fresh explicitly selected attempt with new IDs/handles. A changed context tip requires a separately reviewed replacement yield receipt or a new run; a new producer invocation never silently supersedes the prior record. Existing slots/sessions and observations are retained until their owner deliberately removes them. No profile cleanup command or Session deletion API is added.

These are cooperative checks, not an atomic distributed transaction or fencing against same-user writers. Rechecks cannot prove nothing changed and changed back between reads. Handoff freshness and matching snapshots do not establish current source compatibility. A PM generation coordinates a task rather than authorizing execution or stopping an expired process.

## Test seam and acceptance scenarios

**Primary seam decision:** invoke the extracted profile entry point in an isolated installed environment against native public components and disposable real Git repositories, with separate producer/consumer processes. Users and acceptance tests cross the same seam. Controlled component/process adapters inject faults at that seam. Narrow pure parsing tests support adversarial bytes, but private component internals, fixture-only successes or package-import checks do not prove the combined workflow.

Implement one vertical scenario and its RED-to-GREEN cycle at a time. Each scenario traverses the profile input, installed component interaction, observable result and retained state that it exercises. Future scenario IDs below are commitments, not test results already achieved.

| Scenario | Observable acceptance criteria |
|---|---|
| S1. Select and inspect | A clean extracted-profile install uses only its four components and locked installer, with no browser/npm/systemd/key requirement. Explicit fixture setup is separate. Inspect reports exact versions and selected task/store identity with no state/receipt/claim/session writes. Missing executable, invalid selection, wrong store or unsupported capability refuses; a clean unrelated sentinel is unchanged. |
| S2. Produce retained evidence | A native producer claims, observes a real synthetic overlap, captures and reads back identical bytes, records/verifies exact context and guarded-yields. PM readback is todo/absent, the Results writer is closed, and the yield receipt identifies the actual capture and context. A report larger than the Handoff body limit is retained without embedding/truncating it. |
| S3. Recover and re-observe | A separate consumer recovers the exact historical bytes, obtains a different live generation, makes/captures a fresh complete positive observation, attaches current evidence and reads back done/absent. Old and new capture/scan identities stay distinct. Changing the fixture between attempts demonstrates that the old capture remains unchanged while the fresh observation reflects current state. |
| S4. Preserve incomplete observations | Native complete-negative, complete-positive, partial-positive, partial-indeterminate and unavailable reports retain coherent exit/coverage/problems through capture/pickup/readback. A partial producer may yield diagnostic context; fresh partial/unavailable/negative consumer observations cannot complete this goal. Malformed, oversize, signaled, exit-74 and internal-error executions produce no successful handover/completion. Odd byte filenames preserve native exact identity without display-based comparison. |
| S5. Refuse mismatched context or storage | Wrong run/task/store/definition, swapped result slot/reference, changed digest/length, stale/future/done/superseded/missing context, forged acceptance and missing/corrupt/incomplete capture prevent continuation. No ambient store/latest/project fallback, arbitrary path/command execution, older-record retry, claim acquisition before usable context or silent success. |
| S6. Contend and lose ownership | Two native consumers start after one yield; exactly one claims. The loser makes no fresh scan, capture, context or PM mutation. Controlled generation/definition/context changes immediately after the winner's claim or before each mutation stop forward work. No stale attempt completes or releases a successor's claim; component readback records the actual state. |
| S7. Interrupt and reconcile | Inject interruption before launch and after possible effects at claim, session create, capture, context record, PM yield, evidence attachment and completion. Saved intents distinguish not-started from unknown. Read-only reconcile examines exact known identities with zero mutations/replays. Lost create response remains an unresolved slot, not a guessed session. Failed close/readback/output persistence never becomes a successful receipt. A separately repaired fresh attempt can prove its own outcome. |
| S8. Package, retain and remove | Selected archive members, exact component/installer locks, MIT license and required notices verify after extraction. Existing profile pins/examples/locks and immutable archives remain intact; both existing workflows are regression-checked at their declared seams. Uninstall removes the selected environment and preserves retained reports/component state. Explicit quiescent backup/restore under the same pinned artifacts recovers exact selected references. Any synthetic cleanup is restricted to a deliberately selected owned temporary parent, with unrelated state unchanged. |

The initial native qualification target is CPython 3.11 on Linux x86_64 under WSL2, local ext4, Git 2.43.0 and the Results acceptance runtime's linked SQLite 3.45.1. Record exact actual interpreter/Git/SQLite/filesystem versions. CI on another environment is useful regression evidence, not additional platform certification. Bare Windows/macOS, network filesystems, multi-host fencing, native Claude/Codex/Grok/Dot integration and independent newcomer adoption remain unverified unless separately demonstrated and accepted.

Release acceptance also requires the exact selected archive walkthrough, privacy/license review, truthful guide and source/asset binding described in the accompanying release plan. Existing browser profile native replays use a separate isolated test target; lack of that target remains a regression-evidence gap, never permission to use the estate's signed-in resources.
