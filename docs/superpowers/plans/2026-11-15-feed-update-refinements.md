# Threat Feed update refinements

User request: lock an existing feed update to its current scope, display only changes to be applied, disable unusable standalone objects for Threat Feeds, and remove unscoped feeds and user-facing compatibility messaging.

Implement inline in the managed worktree, preserving approval and immutable execution. Existing update links use a dedicated feed-bound request route. A disabled/hidden form scope is validated server-side; feed previews capture immutable additions/removals and publication-state changes in submitted intent. Unchanged publications are excluded and no-op requests are refused. Standalone object controls are disabled for the Threat Feeds target in both browser and server validation. A data migration deletes only unscoped publications and their account links, then makes scope mandatory. Retain accounts, catalog groups, approved publications and request/audit history. Remove the old download route and compatibility notices. Compare and synchronize only changed files to the original runtime checkout; back up its database before migrating.

- [x] Write and run failing update-scope, delta/no-op, object-control and cleanup tests.
- [x] Implement captured deltas, locked updates and disabled object selection.
- [x] Remove unscoped feeds, route and notices with a cleanup migration.
- [x] Run focused/full tests, review and browser checks, build assets and apply reviewed runtime changes/migration.

Verification: eight new update/UI tests initially produced seven expected failures before implementation. Final focused feed/approval/update/migration suite passed 75 tests; full suite passed 403 tests with 21 simulation-dependent skips in 40.89 seconds, using a test-process-only fast password hasher. All eight new update tests separately passed with the default password hasher in 12.33 seconds. Django checks, migration drift, frontend build and whitespace checks passed.

Review: a separate read-only reviewer found that switching from a server-rendered Threat Feeds form back to Firewall installation left the native objects select and transfer widget disabled. Reproduced in the browser; the target handler now updates the native select and emits change, and the transfer widget refreshes its disabled state during render. Verified selection of two objects after switching to Firewall installation, then verified disabling/hiding after switching back to Threat Feeds. The reviewer confirmed the correction with no further findings.

Browser QA: desktop and 390px mobile update pages show fixed scope and only added/removed values, with unchanged domains omitted. The preview used an in-memory fixture database; its server was stopped. Prior request snapshots lacking recorded deltas retain their original requested-content view rather than fabricating historical diffs.

Runtime: copied and hash-verified 24 changed/new files to the original checkout while preserving development host settings. Created .cache/backups/before-feed-update-cleanup-483888a9.sqlite3 before migration. Inspected and applied inventory0013 successfully. Removed two unscoped feeds and their account links; verified the existing scoped publication, accounts, catalog groups and request history were preserved. Runtime configuration and fixed-update pages render successfully. Work remains uncommitted; no production deployment or firewall writes.