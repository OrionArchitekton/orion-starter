# Starter continuity implementation and release plan

Private preparation, 2026-10-17. The current request authorizes this specification and plan. Implementation and publication remain later decisions. The [living spec](../../specs/starter-continuity-spec.md) defines observable behavior; this plan defines the implementation sequence and release evidence. The [runbook](../runbooks/starter-continuity.md) defines recovery and rollback.

## Baseline and proposed destinations

Source baseline: `OrionArchitekton/orion-starter`, main `79d10d7ec78ad1b0f8200fa26b97b4e17c26e5e5`. That repository is public; preparation remains in a local worktree with no remote branch, PR or draft release. Existing CI verifies profile hashes, compiles examples, scans secrets and aggregates required checks; it does not prove a native browser workflow. The current PM example imports no PM internals and is the existing public-interface pattern to follow.

| Item | Decision for the candidate |
|---|---|
| Distribution | Existing `OrionArchitekton/orion-starter`; proposed tag `v0.2.0-rc.1`, GitHub prerelease. No new repo or PyPI package. |
| Base profile | Keep the PM/browser walkthrough and pins. Root manifest remains schema 1 with the PM/browser component list; update its distribution version and add a continuity-profile descriptor. |
| Continuity profile | Add `profiles/continuity/manifest.json`, full hash-locked Python dependencies, and its own walkthrough. Handoff is optional for base-profile users. |
| Guide | Proposed canonical route `https://www.danmercede.com/guides/continue-agent-tasks-with-orion-starter`; new article in the existing hub, subject to copy review. |
| Works | Add narrowly scoped links from existing PM and Handoff Works surfaces after the guide/package exist. No new microsite, redesign or distribution-wide branding campaign. |
| License | Retain existing MIT license and component notices. Confirm provenance/rights for new glue and guide assets at full-package review; do not import private helpers. |
| Support | Preview on CPython 3.11, Linux x86_64 with a systemd user manager; exact WSL2/ext4 environment only after its new native receipt. No stable or universal-harness claim. |

The root manifest's outdated phone description is corrected in the **new version** to public-but-not-included/not-tested-in-this-profile. Do not include phone or imply combined compatibility. Keep the existing RC2 archive and tag untouched:

`orion-starter-0.1.0-rc.2.zip` — SHA-256 `014398530c0643a6b0e9b9b8e04d61e486259b06b45e7e29817d62fc9a7823ea`.

### Exact proposed inputs

| Artifact | Version | SHA-256 |
|---|---|---|
| `orion_pm-0.1.1-py3-none-any.whl` | PM 0.1.1, API/store 1 | `54f28272550054c32958c67fd84094b825bb387f91ad3efe3b342d463b9c16c7` |
| `orion_browser-0.1.0-py3-none-any.whl` | Browser 0.1.0 | `ba793c5271dc7f1909f88823be88195b84f43fbbf58e5e9cd39c5efb085a746a` |
| `orion_handoff-0.1.0-py3-none-any.whl` | Handoff 0.1.0, interface/store/record 1 | `e1f3e1e43839cfd2896cfc553bef9366867c1cf50bce1e4d4762cdbec9977e41` |
| `driver/package-lock.json` | agent-browser 0.25.4 | `72628cdcdd2d64c8cc5abe8a0fc6625b4447f12374e61f51b17654ba8ad65264` |
| `requirements.lock` | Existing PM/browser graph | `defb94ad874c7f0ba6d0bc302aeca1b76ea4a7eef99c9faa184b823820e01449` |
| `bootstrap-requirements.txt` | pip 26.2 / setuptools 84.0.0 | `4aed17ced2b8225bf1957cbc2fc7b056bf14ef0906aa5a09ad5c75ee5f6467ca` |

Wheel URLs are the existing versioned GitHub release-download URLs, matching the root manifest plus Handoff's v0.1.0 wheel. Verify bytes against these pins before installing. The new continuity lock must include the complete existing Python graph plus Handoff and must have its own digest. The table is a baseline, not a fresh vulnerability-clearance result. Re-audit Python, npm and installer tools during implementation; any changed pin requires updated locks and appropriate combination proof. No component main branch substitutes for a released wheel.

## Implementation shape

Add one standard-library example, `examples/continuity_starter.py`, with the three modes in the spec. Keep component-specific decoding private to that example. Reuse the existing command-only PM pattern, but do not change the preserved base example or turn its decoder into a generic multi-tool envelope. The new example needs real native browser/client calls; a caller-supplied fake driver alone cannot satisfy the release.

Proposed invocation: `python examples/continuity_starter.py --selection /absolute/owned/run/selection.json inspect|produce|continue`, with `--yield-receipt /absolute/owned/run/yield.json` required only for continue. The mode argument is one literal choice, not shell syntax. Generate unique attempt/holder IDs internally; do not accept a prior holder as a shortcut. Inspect writes only its bounded JSON stdout result, never a receipt file. Explicit setup remains a separate walkthrough step using public component commands.

The selection has the following exact top-level shape; placeholders are explanatory, not runnable defaults:

```json
{
  "selection_version": 1,
  "run_id": "<UUID>",
  "workspace": "/absolute/owned/run",
  "pm": {
    "executable": "/absolute/environment/bin/orion-pm",
    "home": "/absolute/owned/run/pm",
    "store_id": "<observed PM store identity>",
    "task_id": "continuity-demo",
    "task_definition_sha256": "<64 lowercase hex>"
  },
  "handoff": {
    "executable": "/absolute/environment/bin/orion-handoff",
    "store": "/absolute/owned/run/handoff"
  },
  "browser": {
    "executable": "/absolute/environment/bin/orion-browser",
    "config": "/absolute/owned/run/browser.toml",
    "config_sha256": "<64 lowercase hex>",
    "name": "contdemo"
  },
  "client": {
    "executable": "/absolute/driver/node_modules/.bin/agent-browser",
    "config": "/absolute/owned/run/agent.json",
    "config_sha256": "<64 lowercase hex>"
  }
}
```

Reject unknown keys and invalid types. All owned runtime/configuration/receipt paths must stay under the selected private workspace; executable paths stay in the selected environments and are version-checked. Bind configuration hashes and validate that browser state/profiles point to owned children, restore-session is disabled, and client configuration contains no inherited connection/session. Setup fails if paths already hold unrelated state. Match the literal spec target; no target URL or executable command comes from Handoff text.

Yield receipts contain receipt version, run/producer-attempt IDs, PM store/task/definition digest, historical producer generation, derived Handoff key and selected store role, exact record ID/digest, observation digest/time, and explicit client/resource/PM read-back outcomes. Continue must validate their strict schema, sizes and all identity relations; arbitrary “success” flags are insufficient. Keep receipts in the selected workspace with private permissions. They are correlation data, not authenticated approvals. The envelope's independently observed results distinguish these historical producer fields from current consumer handles.

Add `profiles/continuity/{manifest.json,requirements.in,requirements.lock,README.md}`. Reference the separately pinned root bootstrap and navigation-client lock rather than hiding installation in the example. The profile manifest names all three artifacts, contract versions, relevant file hashes, environment constraints and supported invocation. No generated state, profile, browser data, vendor settings or credentials belongs in source.

Add `tests/test_continuity_profile.py` and bounded fake-executable fixtures under `tests/fixtures/` as needed. Extend `scripts/check_profile.py` for both manifests and all declared paths/hashes, while preserving the current base checks. Extend CI with the deterministic example-interface tests and public-wheel CLI checks; native browser proof remains a separately bound receipt. Do not add a runtime framework or testing dependency when the standard library suffices.

Update root README/version description, RUNBOOK, profile manifests, and scoped validation references only as required for the new distribution. Preserve the old receipt as explicitly historical evidence; do not relabel it as a test of Handoff. The current planning changes create no executable or manifest changes.

## Vertical implementation sequence

Start only after the implementation scope is selected. Refresh main, ownership and pins first; preserve unrelated work. For each row, write the failing scenario test, implement the smallest complete slice, run its relevant checks, and commit that slice locally. Do not prewrite all tests and then all implementation. Keep the living spec synchronized with any reviewed behavior change.

| Slice | Scenario and implementation work | Evidence needed to leave the slice |
|---|---|---|
| 1 | S1: explicit selection, private paths, installed version/capability checks and read-only inspect. Define strict selection/receipt shapes and component-specific decoders. | Example invoked as a subprocess against real installed PM/Handoff and fixture failures. Snapshot shows no inspect mutations or browser calls; missing/empty selections are refused. |
| 2 | S2: producer through PM claim, actual lease/read/cleanup, exact record/read-back and guarded task yield. Write-ahead operation receipts prevent forward work after unknown results. | One synthetic native producer yields todo/claim absent, no browser holder and a verified exact record/digest. Deterministic failures at every stage cannot return `yielded`. |
| 3 | S3: separately invoked consumer checks exact binding, obtains fresh handles, independently reads, releases, attaches current evidence and completes. | Full two-worker native result from fresh installed artifacts, with different PM generations/browser sessions, done/claim absent, and clean resource cleanup. |
| 4 | S4/S5: context refusals, two-process contention, changed ownership/expiry. | Same public example interface proves malformed/stale/ambiguous/wrong identity handling; one winner, losing consumer zero browser calls; generation changes stop new actions. |
| 5 | S6: bounded output/deadlines, command interruption and recovery observations. | Fault evidence before/after each potentially committed command, no blind retry, no false completion, and an explicitly repaired fresh attempt. Interruptions that cannot be proven safe remain blocked/unknown. |
| 6 | S7: locks/manifests, archive construction, install/base-profile regression, removal and dependency audit. | Two byte-identical archive builds, clean extracted install, all pins/notices checked, base and continuity entry paths exercised, owned-resource uninstall/restore documented, RC2 unchanged. |
| 7 | Guide/copy and full-package review. | Final private source/archive/evidence/guide/Works-link packet with blocker matrix and exact actions for approval. No public staging branch while preparation is private. |

S4 and S5 may use separate RED→GREEN cycles within slice 4; likewise each newly learned interruption case in slice 5. Do not hide multiple independent behavior changes behind one nominal cycle. Slice 2/3 native probes use only an explicitly chosen anonymous disposable browser. If that environment is unavailable or collides, finish the safe local tests and report the missing native proof; do not borrow an estate pool browser.

## Native demonstration and evidence

Use fresh component environments and one owned workspace outside source. Verify prerequisites without installing OS packages or modifying services. Select an unused browser name of at most 16 lowercase letters/digits and an available screen 10–99, with unoccupied X/HTTP/VNC ports. The released browser derives unit names from its selected state directory; do not assume a hardcoded service name. Check for inherited overrides and reject contaminated setup. No use of live accounts or pre-existing browser profiles.

The native transcript must show producer claim → public read → clean native release → client close/status → verified record → PM yield, then consumer exact selection → fresh claim/lease → independent read → clean native release → client close/status → current evidence → guarded completion. This preserves the base walkthrough's native-release-before-client-close ordering. Capture a premature/competing consumer refusal and the final owner/resource state. Test repeated native use from the extracted archive and verify the base profile entry path. Synthetic fault tests cover unsafe failure injection that should not be performed on the estate host.

Private receipts include artifact digests, source identity, interpreter/OS/filesystem/systemd/Chrome/client versions, run and operation IDs, selected store identity, task/record/digest, holder generations, browser sessions, relevant exits, observation timestamps and precise cleanup. Each potentially committed command retains intent/result state. Retain normalized relevant outcomes plus raw-output digests/byte counts, rather than copying whole component output or untrusted prose into the log. No hidden command retry or missing evidence may be reported as success. Cap the operation log at 64 operations and 1 MiB per attempt; reaching either bound stops forward work before the next action. Component logs stay separately owned.

Create a separate sanitized public verification receipt with no estate paths, hosts, account labels, tokens, environment dump, live task data or raw page/handoff contents. Replace private path names with declared logical roles, retaining relevant versions/hashes and outcome scope. This sanitation does not turn the receipt into a claim of native harness or cross-host support.

## Reproducibility and dependency gate

Build a deterministic source/profile ZIP from an explicit allowlist of committed public-safe files. Normalize ordering, timestamps and file permissions; exclude `.git`, `.private`, environments, caches, local receipts and generated runtime state. Include MIT notices, walkthroughs, declared examples and both profile manifests/locks. Verify all archive members before extraction; reject traversal, symlinks and unexpected members.

Install the continuity lock with hash enforcement into a new environment. The installer/bootstrap tools are separate from runtime packages. Use the pinned npm lock with `npm ci`; check transitive and build-tool advisories and retain command/version/output evidence. Any unresolved high/critical advisory affecting the delivered path blocks the candidate. Lower-severity or non-applicable findings require a concrete scope/exploitability disposition in the review packet; “build tool” alone is not a disposition. Do not weaken existing dependency review or required-check aggregation.

Build twice and compare ZIP bytes. Bind native verification to the final exact ZIP digest. The external release-verification receipt contains that digest; a ZIP cannot contain its own digest-bearing receipt. Any code, lock, packaged copy or example change produces new bytes and invalidates approval for the prior bytes. Re-run checks appropriate to the change, then bind the final archive again. External SHA256SUMS and release-verification files identify their exact final assets without circular self-hashes.

## Four release blockers and closure criteria

| Blocker | Closure evidence | State now |
|---|---|---|
| B1. Complete native continuation | S1–S6 implemented; full extracted-install producer/consumer proof, wrong-context/ownership refusal and recovery evidence. | Open: specification only. Previous PM/Handoff probe was pairwise feasibility. |
| B2. Reproducible artifacts | S7, reviewed full dependency audit, exact component/example/lock/archive hashes, two equal builds and clean installs. | Open: existing pins observed; no new lock, audit or archive built. |
| B3. Truthful support | Published matrix names only demonstrated environment and CLI recipe. Any harness named supported has its own native proof. | Claims defined; implementation/receipt review pending. Stable onboarding remains separate. |
| B4. Complete launch review | Exact source and assets, MIT/provenance/new-code rights, compatibility receipt, guide/Works copy, verification and rollback reviewed together. | Open: plan prepared, full release packet not built or approved. |

No P0/P1 correctness/security finding, failed required check, unresolved unknown ownership or incomplete cleanup can be waived by a polished demo. Full-package acceptance remains Dan's. Independent-newcomer evidence gates stable onboarding claims; the preview can ship with its explicit limited scope after its own blockers close.

## Guide and Works copy plan

Proposed title: **Continue a local agent task with PM, browser and Handoff**. Opening claim: “A local worker can leave bounded context for another worker, which acquires its own task claim and browser lease before continuing.” Use that claim only after the combined native proof exists.

The guide explains the three ownership roles, prerequisites/explicit setup, producer observation/yield, exact selection, consumer continuation, a refused competing claim, stale/changed context, interruption recovery, and cleanup/uninstall. Include command blocks exercised from the final archive, component/source/license links, exact preview/environment limits and what each receipt proves. Use a small role/sequence figure with synthetic identities; any new assets need source/rights review. Do not invent current harness support or describe arbitrary “agent memory” recovery.

Use the existing hub guide source/compiler and its repository-local workflow when implementation is later authorized. Draft link copy for existing PM/Handoff Works surfaces: **“Try the PM + browser + Handoff starter preview”**, accompanied by its preview/environment qualifier. Site source changes belong to those existing site repos, and guide integration belongs to the hub; do not edit only a rewritten hub route and assume microsite content changed. Use native document links for navigation across rewritten Works routes. No redesign or additional pages are part of this scope.

A guide video is a separately selected deliverable with its own preview/watch/listen acceptance. This plan does not authorize video production, syndication, social posting or account actions.

## Approval, publication and post-release sequence

1. **Current checkpoint:** privately review this spec and plan. This completes planning only.
2. **Implementation checkpoint:** after selection, prepare code, tests, native receipts, archive, guide and Works-link copy locally. No public remote writes during private preparation. Check new-code/asset provenance and all four blockers; bring back one complete package.
3. **Publication checkpoint:** Dan approves exact destinations/actions and artifact hashes for the full package. No present instruction approves source publication, upload, merge or deployment. Authentication and platform-required human approvals remain separate when actually encountered.
4. **Approved execution:** refresh branch/review requirements. Push only reviewed public-safe source, open normal PRs and complete checks/human review. Land source through protection. Verify the reviewed source/asset correspondence; if merge changes candidate bytes or relevant content, revalidate and rebind the package before publishing.
5. Publish a new immutable GitHub prerelease and verify downloads/digests. Do not upload to PyPI or replace RC2. Then publish the combined guide after its package target exists. Finally deploy the reviewed PM/Handoff Works links after the guide is live. Preserve component guide links throughout.
6. Verify from consumer surfaces: public source/tag/assets, fresh artifact installation, canonical guide/rendered commands, Works-to-guide/package navigation, desktop/mobile and JavaScript-disabled link behavior where applicable. Deployment/CI success alone is insufficient. No verification sign-in, account post or estate adoption is implied.
7. Observe release assets and the named routes once; record actual delivery results. Further checks respond to failures or material changes. Runtime migration, stable graduation and later components remain separate decisions.

If code cannot compose through these released interfaces without changing a component contract, stop that slice, describe the observed conflict, and revise the plan before changing the upstream component. Do not silently widen this distribution work into a core release.
