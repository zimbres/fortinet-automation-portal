# Execution ledger: 2026-10-24-restricted-addresses

Approved spec and native execution. Tasks 1–4 complete.

Ruling: Work in the supplied checkout on develop, without creating a separate worktree — the user approved implementation in this chat and the workspace has no unrelated changes; preserve their configured workspace and avoid another approval round. No commits, merges, pushes, or live firewall calls are part of this task.

Ruling: Normalize catalog subnet host bits as approved, replacing the old rejection behavior. Update the preexisting host-bit rejection test to reflect the explicitly approved behavior.

Task 1: complete — 22 initial tests failed on missing functionality; core restriction and existing catalog tests then passed (28 tests).

Task 2: complete — four new bulk behavior tests failed before implementation; restriction, catalog, import, and group-selection tests passed (61 tests). Refusals retain the submitted object name and normalized value instead of a new source-line database field; raw names preserve the original input.

Task 3: complete — 12 view tests initially failed on missing routes/results; all 39 new feature tests now pass. A test mistakenly included the login audit event in restriction CRUD assertions; scoped it to restriction events after confirming emitted records.

Task 4: in progress — Django system check and migration drift check pass; complete suite and independent review running. Documentation updated. Impeccable launcher unavailable due to missing engine/cache permission; existing PRODUCT.md, DESIGN.md, templates, and craft guidance used directly.

Review corrections: reviewer identified that all-refused batches skipped group revision checks and could mask newly conflicting catalog names. Added failing regression tests, then prevalidated both fatal conditions before row refusals. Independently reproduced numeric IP input mislabeled as FQDN bypassing subnet rules; numeric dotted domain roots now require the subnet type. Targeted verification: 50 passed. Reviewer rechecked corrections and found no new important regressions.

UI verification: rendered seven pages against an isolated in-memory database. Inspected restriction listing, mixed preview, and results in the in-app browser; checked listing and results at 390px iframe widths. Existing themes and responsive styles used without changing the design system.

Verification finding: initial full suite finished with 319 passed, 21 skipped, 3 failures. The feature failure used a test assertion compiled before its singular/plural wording edit; the current test already passes in the fresh 87-test focused run. The other two failures were preexisting OIDC test cases computing future timestamps during collection: after the 499-second run those tokens were no longer future-dated. Ruling: compute those test dates at execution so long regression runs retain their intended assertions; no OIDC production behavior changes. A fresh complete run will use fast password hashing only inside the test process to avoid spending minutes on unrelated fixture password setup.


Task 4: complete — final full suite: 328 passed, 21 skipped in 30.49 seconds, using an in-process test-only MD5 password hasher. Skipped tests require FORTINET_SIMULATION_URL. Fresh default-hasher verification of OIDC regression cases and the mixed-result view: 9 passed. Final focused catalog/restriction/permission suite: 87 passed with default hashing. Frontend build passed; Django check, migration drift check, and diff whitespace check passed. Both additive inventory migrations applied to the local development database. Temporary browser tab and fixture server closed. Work remains uncommitted in the requested checkout; no push, merge, deployment, or firewall operations performed.
