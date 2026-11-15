# Approved Threat Feeds Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline, with test-first changes and a final independent review.

**Goal:** Add approval-gated, immutable Threat Feed publication scoped to firewall and address groups.

**Architecture:** Reuse InstallationRequest with a threat_feeds snapshot target and a local atomic executor. Add a stable firewall-group namespace and scoped publication snapshots, retaining disabled legacy records for migration review.

**Tech Stack:** Existing Django, SQLite, templates, shared request/executor infrastructure.

**Spec:** docs/superpowers/specs/2026-11-15-approved-threat-feeds-design.md (approved by user).

## Global constraints

Every initial publication and content replacement requires explicit approval. Preserve current Superadministrator self-approval policy. No FortiGate calls for feed requests. Preserve Basic auth and explicit scoped assignments. Existing unapproved/unscoped publications become disabled and old URLs return 404. APP_PUBLIC_URL retains its localhost default.

## Review focus

Pending requests cannot alter downloads. Stale approvals cannot overwrite a newer revision or administrative revocation. Multi-group publication and successful execution commit atomically. Scope permissions and account assignments never extend across firewall groups. Recovery may safely replay rolled-back local publication but must retain device reconciliation semantics.

### Task 1: Storage and approved publication service

Files: inventory models, inventory/threat_feeds.py, changes/feed_publications.py, changes/installations.py, changes/models.py, migrations, tests/test_feed_approvals.py.

- [x] Add failing tests for immutable snapshots, mandatory initial/update approval, scoped authentication and last-approved content.
- [x] Add ThreatFeedScope(firewall_group, slug) and scoped ThreatFeed fields: scope, approved_request, revision, ip_text and domain_text. Legacy records retain null scope and are disabled by data migration.
- [x] Implement build_feed_snapshot(actor, object_ids, group_ids, firewall_group_id), prepare_feed_scope(actor, firewall_group_id), and execute_feed_request(request_id, owner_id). Submission uses existing immutable request digest and idempotency checks.
- [x] Add stale revision checks, atomic updates and revocation tests; run focused tests.

### Task 2: Request, approval, executor and UI integration

Files: changes/forms.py, installation_executor.py, executor.py, portal request/feed views, URLs, request/snapshot/history/feed templates and feed account forms.

- [x] Add failing request form, queue/history, permissions, executor recovery and legacy migration tests.
- [x] Add Threat Feeds target and request previews, route approved requests to local publication, and preserve firewall execution behavior.
- [x] Serve stored approved content at /threat-feeds/<firewall-group>/<address-group>/<file>. Make direct publication impossible and retain only audited revocation in management.
- [x] Display scoped assignments, approved revisions and migration guidance; adapt obsolete live-feed tests to approved fixtures.

### Task 3: Verify and integrate

- [x] Run focused and full tests, checks, migration drift and frontend build; inspect desktop/mobile UI.
- [x] Independent read-only review; correct reportable defects and verify again.
- [x] Update user/operations documentation and approved design status. Compare original checkout before applying reviewed changes; inspect migration plan before applying runtime data migration.

## Execution ledger

Implement inline in the existing managed worktree. Preserve all previously implemented Threat Feed changes and unrelated original-checkout edits. No commits, merges, pushes, production deployment or firewall writes are authorized by this implementation task.

Task 1: complete. Nine initial approval tests failed before implementation. Added immutable feed snapshots, scoped stored publications, revision checks, atomic publication and account isolation. Source catalog group deletion now returns a validation error for protected feed identities.

Task 2: complete. New Request supports Threat Feeds; previews, approval queue, history and details identify this target. The shared executor dispatches local publication without device calls. Direct publication is blocked; administrative disable/revoke increments the revision to invalidate stale requests. Legacy records remain unscoped and disabled. Recovery resets only interrupted feed requests; historical/device requests retain reconciliation behavior, including snapshots without a target_kind key.

Review correction: the independent reviewer found slug collisions between separate pending requests. A regression reproduced IOC A and IOC_A receiving the same URL. Added ThreatFeedIdentity and migration0012 to reserve scope/group slugs transactionally at submission without exposing content. Both requests now publish successfully at their frozen distinct URLs. The reviewer confirmed the correction, with no remaining blockers.

Verification: focused feed/security/approval/migration tests 66 passed; reviewed full suite 394 passed, 21 skipped in 37.28 seconds using a fast hasher only inside the test process. All 21 approval tests separately passed with default password hashing in 35.74 seconds. Django checks, migration drift and whitespace checks passed. Frontend build passed after linking existing node_modules read-only for dependency resolution. Desktop and 390px mobile configuration/request previews were visually checked using an in-memory fixture database; the fixture server was stopped.

Regression findings resolved: the first full run reported test_locked_running_installation_requires_reconciliation (missing JSON target key), test_superadmin_self_approval_reaches_executor_and_own_queue (existing firewall action label), and the new legacy migration test (historical model state lacked unrelated current account fields). Recovery selection and the conditional label were corrected; migration test state now includes unrelated current migration leaves. All pass in the final full run.

Runtime integration: compared the original checkout and preserved its local development host configuration. Copied and hash-verified 43 feature files to D:/Apps/VSCode-App/python/fortinet-automation-portal. Created database backup .cache/backups/before-feed-approvals-2026-11-15-fc36824e.sqlite3 before migrating. Inspected the plan and applied changes0005, inventory0011 and inventory0012 successfully. Migration/system checks and a read-only configuration-page render passed against the original database; its two legacy feeds are disabled and need approved scoped requests. No feed account assignments, production deployment or firewall writes were performed. Work remains uncommitted.