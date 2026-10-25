# Restricted Addresses Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for native execution or superpowers:subagent-driven-development if the user selects delegated execution. Track the steps below.

**Goal:** Provide an administrator-managed restriction list with server-side enforcement, partial bulk acceptance, and explicit privileged overrides.

**Architecture:** Keep restrictions separate from installable catalog objects. Share normalization and matching between single saves and import preview/confirmation; retain durable refusal results and existing catalog authorization.

**Tech Stack:** Django, Python ipaddress, existing server-rendered templates, pytest.

**Spec:** `docs/superpowers/specs/2026-10-24-restricted-addresses-design.md`

## Global constraints

- Only active SuperAdmins and Administrator role members manage restrictions or override them.
- Existing catalog permissions still govern object creation.
- Inputs are IPv4 hosts/subnets, FQDNs, or leading `*.` wildcard FQDNs; imports allow at most 1 MiB and 1,000 rows.
- Preserve malformed-input and stale-group error behavior. Restriction refusals alone permit partial catalog import success.
- Reuse the current Django UI and audit infrastructure; do not modify firewall policy or existing objects retroactively.

## Review focus

- Broader networks and wildcard parents must not bypass a smaller restriction.
- Restrictions added after preview must be enforced at confirmation.
- Role removal after preview must prevent a saved override from being used.
- Repeated confirmations must preserve original created/refused outcomes without duplicates.
- All-refused batches and domain lookalikes must produce clear, accurate results.

## Task 1: Restriction storage, matching, and single-address enforcement

**Files:** `apps/inventory/models.py`, new `apps/inventory/restrictions.py`, new migration following the latest inventory migration, `apps/inventory/catalog.py`, `apps/accounts/permissions.py`, `tests/test_address_restrictions.py`.

**Interfaces:** `can_manage_restrictions(user) -> bool`; `require_restriction_management(user)`; `normalize_restriction(kind, value) -> str`; `matching_restrictions(kind, value) -> list`; `save_address(..., override_restrictions=False)` retains its existing return type.

- [x] Write tests for host-bit normalization, subnet overlap in both directions, exact/domain descendant/wildcard overlap, whole-label boundaries, and unrelated address types.
- [x] Run `.venv/Scripts/python.exe -m pytest tests/test_address_restrictions.py -q` and confirm failures expose missing behavior.
- [x] Implement a separate restriction model with unique normalized kind/value, actor attribution, and timestamps; add permission helpers and shared matcher.
- [x] Enforce restrictions on creation and edits in `save_address`; authorize explicit overrides and audit each match within the save transaction.
- [x] Test operator refusal, forged override, inactive accounts, Administrator and SuperAdmin opt-in overrides, edits, and rollback on failed saves. Re-run the restriction and catalog tests.

## Task 2: Durable partial import results

**Files:** `apps/inventory/imports.py`, `apps/inventory/models.py`, migration, `apps/portal/catalog_views.py`, `templates/portal/catalog_import.html`, `tests/test_catalog_import.py`, `tests/test_address_restrictions.py`.

**Interfaces:** `preview_import(..., override_restrictions=False)` retains CatalogImport return type; `confirm_import(actor, token)` retains created-object list return type. CatalogImport stores refused rows separately from fatal validation errors and stores the authenticated override choice in digest-protected input.

- [x] Add failing tests for mixed allowed/refused and all-refused lists, restrictions added/removed after preview, override privilege removal, repeat confirmation, and preserved malformed-input behavior.
- [x] Run the new tests and confirm expected failures.
- [x] Separate restriction refusals from fatal import errors. Keep valid normalized rows for rechecks and retain row numbers for result messages. Recheck current restrictions at confirmation and persist final refusal results atomically with created objects.
- [x] Update preview/confirmation messages to show accepted/refused counts and individual values/reasons; allow an all-refused result without creating objects. Preserve group revision guarantees.
- [x] Run catalog import and group selection tests together with restriction tests.

## Task 3: Management page and explicit override controls

**Files:** new `apps/portal/restriction_views.py`, new `templates/portal/restrictions.html` and supporting forms/templates as needed, `apps/inventory/forms.py`, `config/urls.py`, `apps/portal/context.py`, `templates/base.html`, `apps/portal/catalog_views.py`, `tests/test_restriction_views.py`.

**Interfaces:** named routes `restrictions`, `restriction_new`, `restriction_edit`, `restriction_delete`, `restriction_import`; all require active privileged role. Restriction import accepts a text file or pasted values and the existing three-column CSV format.

- [x] Add failing client tests for page visibility, every protected route, create/edit/delete/search, escaped invalid values, bounded imports and deduplication, and operator-supplied override fields.
- [x] Run the client tests and confirm expected failures.
- [x] Implement audited management actions and list search using existing template conventions. Reuse normalization without applying the refusal list to its own configuration.
- [x] Add a conditional navigation link and unchecked override field on single-object and import forms only for privileged roles. Server validation remains authoritative.
- [x] Run client, permission-page, and catalog view tests. Inspect rendered markup for forms, CSRF, error placement, and page consistency.

## Task 4: Documentation and verification

**Files:** `docs/local-catalog.md`, this plan.

- [x] Document matching, subnet normalization, explicit overrides, partial bulk outcomes, and non-retroactive scope.
- [x] Run `.venv/Scripts/python.exe manage.py check` and `.venv/Scripts/python.exe manage.py makemigrations --check --dry-run`.
- [x] Run `.venv/Scripts/python.exe -m pytest -q`; investigate relevant failures and report any external-environment limitations explicitly.
- [x] Review the complete diff for authorization bypasses, stale preview behavior, audit allowlist compatibility, and unintended changes. Mark completed steps and report tested results.
