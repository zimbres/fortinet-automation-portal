# Threat Feeds Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish live address-group feeds with explicitly assigned Basic-auth accounts and configured public URLs.

**Architecture:** Add publication and credential models to inventory, a focused service and forms module, and portal management/download views. Keep feed credentials separate from portal users.

**Tech Stack:** Existing Django, templates, SQLite and password hashing; no dependencies.

**Spec:** docs/superpowers/specs/2026-11-14-threat-feeds-design.md (approved).

## Global constraints

Administrator/Superadministrator management only; explicit assignments; no portal access for feed accounts; no credentials in URLs or audit; stable slugs; live text responses; existing catalog types only.

## Review focus

Malformed Basic headers must not cause 500s. Session authentication must not bypass Basic auth. Deletion/recreation must not inherit assignments. Invalid public URLs must fail settings loading. Disabled accounts and publications must revoke access immediately.

### Task 1: Feed storage, credentials and downloads

Files: apps/inventory/models.py, apps/inventory/threat_feeds.py, inventory migration, apps/portal/threat_feed_views.py, config/urls.py, tests/test_threat_feeds.py.

- [x] Write and run failing tests for content separation, authentication, assignment checks, revocation, deletion, stable/colliding slugs, HEAD and credential isolation.
- [x] Implement ThreatFeed(group, slug, enabled), FeedAccount(username, password, is_active, feeds), publish_group(actor, group, enabled), save_feed_account(actor, username, password, feeds, is_active, account_id), and feed download view.
- [x] Generate migration and run focused tests.

### Task 2: Management and public URLs

Files: apps/inventory/threat_feed_forms.py, apps/portal/threat_feed_views.py, templates/portal/threat_feeds.html, templates/base.html, config/settings/base.py, compose.yaml, .env.example, README.md.

- [x] Add failing management authorization, form/password validation and public URL tests.
- [x] Implement list, publish/update, account create/edit and unpublish/delete actions with CSRF and audit. Reuse shared form and selection widgets.
- [x] Add APP_PUBLIC_URL validation and deployment wiring; show absolute URLs, defaulting to http://127.0.0.1:8000 when unset or empty (user follow-up).
- [x] Run focused tests, full pytest suite, Django checks and migration drift checks.

## Execution ledger

Ruling: Execute inline following the user's implementation approval; no additional approval needed. The managed worktree was unwritable, so use codex/threat-feeds in the authorized checkout. Do not commit or deploy. Inspect the local migration plan before applying the additive feature migration.

Task 1: complete. Initial tests failed because the feed service was absent; implementation subsequently passed authentication, content, assignment and lifecycle tests. Corrected the test's host expectation to the catalog's existing normalized `/32` format.

Task 2: complete. Added and reproduced a middleware regression: sessions requiring a password change redirected independent Basic-auth downloads. The middleware now exempts only the resolved feed download route. Management routes retain the password-change gate.

Review: a separate read-only reviewer found that accepted passwords could exceed the Basic header decoder's limit. Added four failing boundary tests, capped saved passwords at 4096 UTF-8 bytes, and raised the encoded header limit to 8192 characters. The reviewer verified that the maximum accepted credential encodes to 5664 characters and confirmed the finding resolved. No remaining review findings.

Verification: final full suite 370 passed, 21 skipped (simulation tests require FORTINET_SIMULATION_URL), in 32.59 seconds using a fast password hasher set only inside that test process. All 42 feed tests separately passed with the default production password hasher in 63.96 seconds. Frontend build, Django system checks, migration drift and diff whitespace checks passed. Desktop and 390px mobile fixture previews and account assignment form were visually inspected; the fixture used an in-memory database and its server was stopped.

Baseline note: an early full-suite process overlapped implementation and retained the old URL resolver while loading the edited base template. It reported 33 NoReverseMatch failures across existing view tests; both fresh full-suite runs passed after all routes were present. There are no outstanding test failures.

UI tooling: Impeccable's engine could not run due to unavailable installation/cache permissions. The new page inherits DESIGN.md and existing shared forms, transfer selectors, themes and tables; no generated visual verdict is claimed.

Local database: inspected the migration plan (only inventory.0010 pending), applied the additive ThreatFeed/FeedAccount migration successfully, and confirmed `manage.py migrate --check` passes. No production deployment, feed credentials, or firewall configuration was created.

User follow-up: unset or empty APP_PUBLIC_URL now defaults to http://127.0.0.1:8000. Updated normalization, the configuration page, documentation and environment example; added settings-loading tests for both unset and empty environment variables. Focused suite: 44 passed.

Follow-up verification: full suite 372 passed, 21 simulation tests skipped in 31.71 seconds (test-process fast hasher). Django checks and whitespace checks passed. The first run in the new managed worktree had 10 tmp_path setup errors because the ignored .cache parent did not exist; creating that directory resolved all errors without product code changes.
