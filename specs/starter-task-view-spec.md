# Starter task and evidence view

A locally generated HTML snapshot lets a user inspect one explicitly selected
development-evidence run in a browser or an Orca panel. The profile keeps its
published component pins and existing selection format.

## Inspect one task

The user selects a run and generates the snapshot to standard output. It shows
the selected task ID, title, status, revision, claim state and, when reported,
holder, claim branch and expiration. The view records when it was generated. Live and expired
ownership observations are visibly different. A missing or unreadable task
prevents a successful snapshot.

## Follow the evidence

The user may also select the producer's yield receipt. The snapshot identifies
the bound handoff and result, shows the retained scan's time, coverage and
observed overlap paths and branches, and labels it as historical. An unreadable,
mismatched or altered receipt or report appears as unavailable. The latest PM
read displays attached evidence separately with its observed time and reference.
A subsequent snapshot after continuation shows the recorded outcome of the
second worker. A retained observation carries no merge decision.

## Read-only behavior

The view uses the profile's existing component and selection checks. It reads
only the selected task, handoff and artifacts. Output is static HTML with
escaped data, inline styles and no account, network, script or store-write
requirements. View invocations neither claim work nor create attempt journals.
Users can generate a new snapshot when the observed state changes.

## Acceptance

Exercise the public profile CLI against the installed pinned components and a
synthetic workspace. Compare selected-store contents before and after the
view and verify the rendered task, evidence identity, overlap and unavailable
states. Load the same generated HTML in a disposable stock Orca workspace and
confirm that the panel renders it.
