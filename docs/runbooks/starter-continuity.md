---
status: private-candidate-verified
verified: 2026-10-17
review_after: 2026-10-31
topics: [orion-starter, continuity, local-claims, browser-cleanup, release-rollback]
references:
  - specs/starter-continuity-spec.md
  - docs/plans/2026-10-17-starter-continuity-release-plan.md
  - RUNBOOK.md
  - manifest.json
---

# Starter continuity operation and recovery

Private candidate runbook. The documented source walkthrough and representative interruption/receipt-failure paths have been exercised; selected stopped-writer PM/Handoff backups preserve task and record bytes on read-back. The external release-verification receipt must additionally bind native results to the final extracted archive. Publication and estate adoption remain separately approved actions.

## Rollout and observation

Prepare the profile in a separate environment and a newly selected private workspace outside Git. Review exact component pins, store/configuration paths, task goal and the public synthetic target. Installation creates no stores or services; explicit setup initializes only those selected synthetic stores/configuration. Native browser start is a visible later operation. A missing system prerequisite is a stop condition, not authorization to install OS packages or repurpose another browser.

Run inspect first, then produce and continue as separate worker processes. The successful states are specific: inspected context; yielded unfinished work; or completed task with current evidence. Read PM and the selected native browser after each mutation chain. Keep private intent/result receipts until cleanup and reconciliation are observed. Do not turn a process exit, available context, accepted command or deployment status into a stronger outcome.

The profile creates no recurring monitor. During an explicitly invoked attempt, inspect operation results and remaining lease time before the next browser action. Unknown result, receipt failure, expired ownership, unavailable component or cleanup discrepancy halts forward work. A machine/process restart does not resume an attempt automatically.

## Common diagnostic sequence

1. Stop the example's forward work. Preserve its selection, bounded operation receipts and exact binaries/locks. Never delete a claim/store/profile as a repair shortcut.
2. Confirm the intended run and absolute store/configuration paths. Do not fall back to a default estate home or a browser inferred from an environment variable.
3. Use the installed PM CLI with the explicit home to inspect `show <task>` and, if necessary, `triage <task>`. Compare store ID, current revision, holder, generation, expiry and task status. PM events are best-effort and cannot prove that an operation never happened.
4. Use Handoff with its explicit store: `list --task <derived key> --limit 50`, `show <record ID>` and exact-task `pickup --task <key> --max-age-seconds 86400`. Validate all exits/envelopes. A truncated list, unreadable store or absent result after a timeout cannot prove no commit.
5. Use the browser CLI with the selected configuration to inspect `status <browser>`. Compare holder/session to this attempt. Status may run the native health check; keep it separate from the example's strictly read-only inspect mode. No blind `lease` as a diagnostic.
6. Report each component's established state separately. Reconcile uncertainty with the responsible component's release runbook. A later explicit invocation starts a new attempt and revalidates the record/goal; it never continues from a merely cached success flag.

These are command fragments for the pinned installed CLIs, not commands to run against an unspecified existing environment. Exact executable paths, JSON switches and supported response shapes must be included in the implemented walkthrough and exercised from the extracted candidate.

## Interrupted operation decisions

| Interrupted point | Inspect and decide | Forbidden shortcut |
|---|---|---|
| Before durable operation intent | No launch is allowed. Repair owned receipt storage before a fresh invocation. | Running with unrecorded side effects. |
| PM claim/renew | Read current claim/task. Matching known generation may still be owned; an unknown/new generation cannot be adopted merely from its holder text. Reconcile using PM's sanctioned interface. | Reissuing claim, assuming expiry stops a process, or editing lock files. |
| Browser acquisition | Native status may show a session that started despite the missing command result. Identify this attempt's unique holder/session and reconcile through the native contract. | Starting another browser or treating timeout as “not started.” |
| Navigation/client close | Read current native ownership and retained client result. A missing result stays unknown even for a read. Cleanup of this attempt is allowed; a new read belongs to a new explicit attempt. | Falling back to another endpoint/session or replaying a possibly sent action. |
| Browser release | Status down/no holder establishes present absence only. Without a recorded clean release/client-close result, the prior attempt remains unqualified. If its own resource is still held, use native release with the exact attempt holder; re-read state. If another holder owns it, stop. | Releasing another holder, killing arbitrary processes, or reporting clean shutdown from absence alone. |
| Handoff record | If the error provides a candidate record ID, inspect it with public `show`; otherwise list the exact task and match the unique attempt request ID, binding and full intended input through `show`. A complete unique current match can establish a commit; a partial list/conflict/integrity fault leaves it unknown. | Repeating `record` on the assumption request IDs deduplicate, selecting by timestamp, or overwriting record files. |
| PM producer release | Read task/claim. Todo/absent confirms present yield only when the verified producer context/resource evidence is already retained. Mixed status/claim residue requires PM recovery. | Treating a recorded context as a successful yield or allowing a consumer to reuse the old generation. |
| Evidence attach / done transition | Inspect current evidence ID/content, revision, status and claim. Reconcile the exact operation before any later mutation. Done/absent proves task state; it does not reconstruct a lost current browser observation or prove this attempt caused it. | Reattaching different evidence under the same ID, blindly retrying completion, or claiming this attempt succeeded from task status alone. |

After reconciliation, any repaired attempt still needs current user-selected scope and fresh ownership. The example never invokes takeover, recover, service control or deletion automatically. PM's explicit guarded release can handle its own expired generation under the pinned contract; takeover/orphan recovery needs separate inspection and intentional operator invocation. Preserve mismatches instead of “fixing” task files directly.

## Ownership, storage and context limits

Private stores may contain future real work even if this demo is synthetic. Keep workspace directories 0700 and receipts 0600; do not log raw environment, endpoint credentials, page content or Handoff prose. Before a new command, enforce the attempt budget of 64 operations/1 MiB. A full disk, permission error, cap hit or failed durable receipt write stops new operations, including automatic mutating cleanup that cannot record intent. Preserve handles and report reconciliation required; the operator can explicitly perform native cleanup after inspection. Never report success because a best-effort cleanup might have happened.

Handoff's 512-record capacity has no automatic archive/deletion. Use a fresh isolated demo store for a new independent run. For a real selected store, use its stopped-writer backup/recovery procedure; never prune it automatically. Context marked stale/done, newly superseded, too old or incompatible with the selected goal stays unusable. Restoring a copy does not make old evidence current.

## Backup, uninstall and rollback

Before backing up, stop this profile's workers and reconcile their resources. Back up each explicitly selected component according to its own runbook; do not snapshot unrelated estate stores. Preserve the exact component versions and configuration alongside matching backups. This profile changes no component store format and promises no migration or downgrade path.

To uninstall a successful synthetic run, release only its own native resource, close its client connection, observe browser down/no holder and the intended PM final state, then remove only that run's disposable workspace and environments. Preserve this native-release-before-client-close order from the base walkthrough. If ownership or cleanup is unknown, preserve it for inspection. Shared OS packages, accounts, unrelated stores, browser profiles and other workers remain separately managed. Retention/deletion is an explicit operator action; nothing is installed to clean up later.

To roll back a private candidate, return to the preserved RC2 profile/environment. Keep Handoff records and any backups; RC2 simply does not consume them. Do not open newer incompatible stores with an older component binary. A published artifact is immutable: after a later approved release, issue a reviewed successor version for a package correction. Web rollback restores the previously approved guide/link content through protected source changes and the site's normal deployment flow; exact prior source/deployment identities must be captured in the final release packet. No production rollback is authorized by this planning document.

## Acceptance before release

Exercise successful rollout and cleanup, representative command interruptions, a disk/receipt-write failure, wrong ownership, and removal on the declared disposable environment. Bind results to final artifact hashes and record remaining unknowns. Source checks are not an exact-archive verification. Retain the external release-verification receipt and scoped evidence; tests or runbook prose cannot stand in for the native three-component result. Browser credential/profile restore is not part of this anonymous demonstration's backup claim.
