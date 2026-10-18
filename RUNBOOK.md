# Repository operations

Changes use pull requests with successful CI, secret scanning, resolved conversations,
and an approving human review after the final push. Do not force-push or bypass
protection. The first reviewed source snapshot is tagged separately from repository
bootstrap checks. Release downloads retain their approved bytes and checksums.

Validate the repository commands in its README before opening a PR. Dependency
updates use Dependabot and the PR dependency-review check. A failed or missing
required check blocks merge; it is not permission to retry an outward action.

Publications require the owner's explicit authorization. For a correction, prepare
and review a new version. Do not overwrite an approved release asset. No repository
operation installs or updates an existing user's runtime automatically.

The native walkthrough needs a disposable anonymous browser on a supported host; CI checks only the versioned profile and examples.

The optional continuity profile uses its own full lock and the [continuity runbook](docs/runbooks/starter-continuity.md).
Run `python scripts/check_profile.py`, install the continuity dependencies into an isolated environment,
then run `python -m unittest discover -s tests -v` and `python -m compileall -q examples`.
CI exercises installed PM/Handoff commands and deterministic native-driver fixtures; it does not run a browser.
Native verification must use the exact extracted candidate archive and retain a separate receipt.

Build from the reviewed committed source with
`python scripts/build_candidate.py --source HEAD --output /absolute/private/artifacts/candidate.zip`.
The builder exports an exact regular-file allowlist, verifies profile hashes, normalizes ZIP metadata
and refuses existing output files, unexpected tracked members and symlinks. Build twice and compare bytes.
The external release-verification receipt carries the archive hash; it is not embedded in the archive.
Keep final source/archive/guide/link approval separate from local preparation.
