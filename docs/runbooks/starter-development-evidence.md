---
verified: 2026-10-19
review_after: 2026-11-19
topics: [starter, development-evidence, recovery]
references:
  - profiles/development-evidence/run.py
  - profiles/development-evidence/results_io.py
  - profiles/development-evidence/manifest.json
  - specs/starter-development-evidence-spec.md
---

# Development evidence operations

Use the [standalone walkthrough](../../profiles/development-evidence/README.md) for installation and explicit synthetic setup. This is an opt-in local preview. No daemon, hook, shared store, browser or account is activated. Keep previous distribution/environment and component backups until exact readback is accepted.

## Observe the selected outcome

`inspect` reads the selected public component contracts and exact task/store/definition. It creates no stores or receipts. `produce` succeeds only at `yielded` with a durable exact yield receipt and native todo/absent readback. `continue` succeeds only at `completed` with a new claim/capture and done/absent plus exact current evidence. Completion is the synthetic overlap demonstration only. Reports are observations, not file locks or merge-safety verdicts.

Partial/unavailable reports are diagnostic captures. Fresh incomplete or negative observations leave this goal unfinished. stdout is bounded metadata; raw reports and operation intents remain private. IDs/references also warrant private handling.

## Stop and diagnose uncertainty

Exit 7 stops forward work. Retain the failed JSON reply, exact selection and `receipts/<attempt_id>/attempt.json`. Invoke the same profile with `reconcile --selection <absolute selection> --attempt-receipt <exact existing attempt>`. This performs public reads only. It never claims, renews, releases, captures, records, transitions, rewrites receipts or repeats a mutation. `reconciled` means diagnostic readback only; `original_attempt_resumed` remains false.

| Failure point | Inspect and preserve | Authority for a later action |
|---|---|---|
| Intent could not be persisted | No mutation was launched; keep the failure and unchanged native state. | Repair only profile-owned storage, then choose a new attempt. |
| Claim response lost | Read the exact PM task. Compare the attempt-derived holder and native generation. | No auto takeover or renewal. Current request and PM admission still apply. |
| Session creation response lost | Keep that exact result slot. No capture has been requested. | Do not list/guess its session and do not reuse/delete the slot. Explicit native diagnosis is separate. |
| Capture/readback/close response lost | Use the saved known SID/reference and selected slot for read-only inspect/read. | Missing/incomplete/corrupt data is not a capture. Writable native recovery is separate. |
| Handoff response lost | Inspect at most the selected task's bounded records; require one exact request/binding match. | A found record does not create a yield receipt or transfer ownership. |
| Release response lost | Observe exact current PM task/claim and context tip. | Never release a successor's generation or blindly resend. |
| Evidence/completion response lost | Observe exact task/evidence and current claim. | Done is current observed state, not proof this attempt completed it. |
| Final receipt/pipe persistence failed | Preserve component readbacks and prior intents. | Reconciliation never fabricates a successful original delivery. |

Changed definition, store/run/task identity, context tip, stale/future context or unusable historical capture refuses continuation before a new claim. Ownership/context are checked again before later mutations. These are cooperative checks, not a distributed transaction or adversarial fencing.

## Explicit component recovery

Quiesce the selected attempt and its owned process group. Use the exact pinned component's documented public diagnostic/recovery/backup interface. Never edit its JSON records, SQLite rows or task files to make this recipe pass. Request IDs correlate attempts; they do not make writes idempotent. Never copy an active Results SQLite database as a valid backup. A public read may expose incomplete/corrupt state that needs a separate explicit writable recovery; profile reconcile does not perform it.

After a deliberately reviewed native repair, choose a fresh attempt with fresh handles. A changed Handoff tip requires a separately reviewed replacement receipt or a new run. A producer does not silently replace an existing context/yield. Restoring a full run requires matching PM/Handoff/Results data plus selection/receipts under the same pinned artifacts and explicit mapping. Prove native readback before resuming; a successful file copy alone proves nothing about restore validity.

## Bounds, monitoring and rollback

The living spec defines per-process/output/depth/disk limits. Operations reserve their bounded duration plus termination grace before launch. Only the invocation's newly created process group/session is stopped; no estate orphan sweep runs. Host scheduling/uninterruptible I/O can defeat hard wall-clock claims; an unobserved stop remains unknown.

Monitor with an attended exact mode reply and native readback. There is no timer or telemetry. Roll back by selecting the prior immutable distribution/environment and matching backups. Do not point old binaries at changed stores without native restore proof. Remove only the selected environment after quiescence; retained reports, context and PM state remain until deliberately reviewed disposal. No estate runtime adoption is part of this package.
