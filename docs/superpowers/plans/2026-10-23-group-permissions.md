# Group Permissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Group-only authorization/requests, mandatory firewall membership, consistent cancellation.

**Architecture:** Replace ScopeGrant's VDOM foreign key with group grants after clearing old permissions. Resolve VDOM visibility through enabled group membership and bind installation authorization to the snapshot group. Validate membership edits transactionally.

**Tech Stack:** Existing Django, SQLite, templates and pytest.

**Spec:** docs/superpowers/specs/2026-10-23-group-permissions-design.md

## Global Constraints
- Current checkout, no remote publication or firewall mutations.
- Preserve local catalog and independent approval.
- User explicitly permits dropping existing permissions.

## Review Focus
- Overlapping groups cannot lend authorization to the selected request group.
- Revocation and membership removal take effect before device writes.
- Group edits cannot remove a firewall's final membership.
- Cancellation/claim races leave one terminal decision.
- First group and first firewall can be registered without a circular dependency.

### Task 1: Authorization and membership
- [x] Add failing group access, overlap, orphan and registration tests.
- [x] Add group grant schema/migration; update permission helpers and user forms/services/admin.
- [x] Require firewall groups on registration/edit; guard final membership removal and permit empty groups.
- [x] Update existing fixtures to group grants; run focused tests.

### Task 2: Group requests and cancellation
- [x] Add failing group-only submission, exact-group execution, cancellation and claim race tests.
- [x] Update request forms, authorization/visibility and group names; disable legacy new submissions.
- [x] Cancel pending executions/targets atomically; migration repairs prior cancelled records.
- [x] Run request/executor/reconciliation regressions and HTTP simulation.

### Task 3: Verify and apply
- [x] Run full suite, Django checks, migration consistency and CSS build.
- [x] Inspect user/firewall/request interfaces in an isolated local database.
- [x] Fresh read-only review, fix actionable regressions.
- [x] Back up actual SQLite, stop verified local helpers, migrate, restart and verify health.
- [x] Update docs and commit verified changes locally.
