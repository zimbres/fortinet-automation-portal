# Approved Threat Feeds scoped to firewall groups

Status: approved by the user on 2026-11-15. Supersedes live publication in the 2026-11-14 Threat Feeds design.

## Intent and confirmed requirements

Add **Threat Feeds** as a target on the existing New Request page. Requests select a firewall group and one or more local address groups. Every initial publication and every content update must pass approval. Each URL identifies both the firewall group and address group. Pending, rejected and cancelled requests do not change served data; the last approved and successfully published version remains available.

Existing Basic authentication, separate feed-only accounts, explicit publication assignments, plain text formats, and APP_PUBLIC_URL behavior remain. APP_PUBLIC_URL defaults to http://127.0.0.1:8000 when unset or empty.

## Approaches

1. **Approved immutable snapshots within the current request workflow (recommended).** Capture the exact content at submission and publish it only after approval. Reuse the request's lifecycle, audit, history and executor. This implements the user's confirmation that every update requires approval.
2. **Approve initial publication and continue serving live catalog data.** Smaller change, but later catalog edits bypass approval. Rejected because it contradicts the confirmed requirement.
3. **Separate feed request/approval system.** Can freeze content, but duplicates the New Request, Approvals and History flows. Not recommended given the existing request infrastructure and requested target option.

The user's confirmation selected approval of every update and the snapshot behavior proposed in conversation. Internal implementation details below are recommendations for review.

## Request and authorization flow

- Add a target selector to New Request: the existing firewall installation target and **Threat Feeds**. Keep firewall group selection for both.
- Feed requests require one or more address groups. Standalone objects are not a feed destination and must not be silently ignored; reject them for this target or make their field unavailable.
- Preserve existing firewall installation behavior. Threat Feed publication submission additionally requires an active Administrator or Superadministrator, consistent with current feed management, plus catalog view and view/submit rights for the selected firewall group.
- Approvers require the existing view/approve permissions for that firewall group. Use the current explicit approval policy, including its separately audited Superadministrator self-approval permission. No requester, including a Superadministrator, receives automatic approval or immediate publication.
- Feed scopes use firewall-group permissions. They do not contact FortiGate or require per-device execution permissions, API connectivity or supported device write capabilities. An enabled firewall group may scope feeds even when it has no physical destinations.
- Request preview and details show target type, firewall group, each address group, exact IP/domain content and counts, current published revision and proposed URLs. Submission captures immutable content and identity; approval must refer to that submitted snapshot.
- Include feed requests in the existing Approvals queue, history, dashboard counts and request detail/status views. Cancellation and rejection preserve the current published version.

## Publication and execution

- Extend the current immutable installation-request snapshot with a distinct `threat_feeds` target kind. Feed requests have no device InstallationTarget rows. Explicitly dispatch them through the existing approved-request executor to a local publication handler, bypassing firewall installation/status aggregation.
- Persist each publication as a firewall-group/address-group pair, with approved IP and domain text, a publication revision and the originating approved request. Downloads read this stored text, never live catalog members.
- Capture selected address-group definitions, member values, catalog revisions and the base publication revision at submission. Validate the snapshot digest again before approval and execution. Catalog edits after submission do not silently rewrite the submitted intent.
- Publish all address groups in one request atomically. Recheck approval and current requester/approver permissions before publication. Verify that each base publication revision still matches; if another request published first, fail the stale request with a useful message and retain current contents. A new request is required instead of an implicit rollback.
- A repeat execution cannot publish the same request twice. Publication and successful request completion commit together. Interrupted local transactions roll back and can safely resume through the executor; do not classify local publication as an uncertain device mutation.
- A never-published group returns 404 until its first approved request succeeds. Empty approved groups return 200 with an empty text file. Existing deterministic sorting, deduplication, UTF-8 text, trailing newlines and GET/HEAD behavior remain.
- Local catalog edits do not alter served text. Protect source identities needed by active publications from deletion; administrative feed removal/disable remains an audited revocation operation. No direct management action may publish, replace or re-enable content without a new approved request.

## URL scope and account assignments

- URLs become `/threat-feeds/<firewall-group-slug>/<address-group-slug>/ip_list.txt` and `/threat-feeds/<firewall-group-slug>/<address-group-slug>/domain_list.txt`.
- Derive readable slugs from names, replacing spaces with underscores and resolving collisions. Persist both namespace identifiers so renames do not break URLs. The same address group can have independent approved versions in different firewall groups.
- Reserve address-group URL identities at submission, separately from downloadable publications, so colliding names in separate pending requests receive distinct stable URLs. Previewing does not reserve or publish anything.
- Account assignments are to the exact scoped publication. An assignment to one firewall group never grants access to the same address group in another firewall group.
- Recheck account status, scoped assignment, publication state and firewall-group enabled state on each download. Preserve 401/challenge for missing or invalid Basic credentials and 404 for unavailable or unauthorized publications. No shared caching.
- Show complete URLs on the Threat Feeds configuration page and request preview/details, using the configured public base URL. Label each publication with both group names, last successful publication/request and current revision/status.
- The configuration page manages feed accounts, assignments and revocation. Replace direct publication controls with links into New Request using the Threat Feeds target. There is no alternate direct-publish path.

## Existing feeds and migration

Existing publications have neither a firewall-group scope nor an approved snapshot. They cannot be automatically approved or assigned a firewall group. Migrate them into an explicitly disabled legacy state, preserving their identities/account records for review but excluding them from downloads and new scoped assignments. Show a clear migration notice.

An Administrator selects the intended firewall group in a new Threat Feeds request, obtains approval, and explicitly assigns accounts to the resulting scoped publications. Legacy unscoped URLs stop serving and return 404; do not redirect them to an arbitrary scope. Users must update their FortiGate connector URLs. No approval history or account access is fabricated during migration.

## Verification and handoff

Test initial publication blocking, immutable approved content, subsequent catalog edits, pending/rejected/cancelled updates, explicit Superadministrator approval, unauthorized submission/decisions/execution, cross-firewall-group isolation, disabled groups/accounts/publications, account assignment isolation, stable slugs and collisions, stale concurrent requests, atomic multi-group updates, executor retry/recovery, legacy migration and old URLs, configured/default public URLs, and request/approval/history UI integration. Retain firewall-installation regression coverage and run the full suite, Django checks, migration drift and frontend build checks where needed.

Implement in the current managed worktree and verify there. Before updating the user's original runtime checkout, compare the relevant files and apply only the reviewed feature changes, preserving unrelated user edits. Document and inspect the additive/data migration before applying it to that runtime database. No production deployment or FortiGate configuration changes are included.
