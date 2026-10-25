# Local catalog and firewall installation

## Rapid indicator blocking workflow

The portal lets authorized people without direct firewall access add IP addresses and FQDNs to an existing address group already used by firewall rules. For example, a security team can submit malicious indicators quickly to a preconfigured block group without receiving firewall credentials. Each indicator is an address object; the address group collects those objects for the existing policy. Firewall administrators must configure and verify that policy first: adding group members does not create a deny rule or change policy order.

1. A firewall administrator prepares the policy and target address group and grants portal access to the appropriate firewall group. Confirm the device and operation have a validated write profile.
2. The security team creates IP/FQDN objects locally, or imports a CSV, selecting the existing address group. Catalog changes alone do not alter the firewall.
3. Submit an installation request for the target firewall group. An authorized approver reviews the immutable request; ordinary requesters cannot approve their own changes. Superadministrators may self-approve.
4. The runner rechecks permissions and observed configuration, executes the approved changes, and reads back the result. Watch approval and execution status in the portal. Investigate failures or reconciliation-required results before treating an indicator as blocked; do not blindly replay uncertain writes.

No firewall UI account or API token is given to the requesting user. Firewall credentials remain encrypted in the portal. Blocking effectiveness depends on the existing policy, its order, and FortiGate address/FQDN behavior.


Address Objects and Address Groups use the local database. Saving, editing, changing local memberships, and deleting local entries never contact a firewall or create an approval request. Deleting a local object requires removing it from local groups first. Existing submitted snapshots and installed device configuration survive local deletion.

## Access

Superadministrators manage the catalog by default. For other users, grant `catalog_view` or `catalog_manage` through Django administration under Catalog grants; manage includes view. User registration also offers an explicit catalog-access selection. Firewall group grants do not automatically grant catalog access.

View, submit, approve and administer permissions are granted to named firewall groups. Device visibility derives from those memberships. A request requires view and the relevant capability on its exact selected group; permission from another overlapping group cannot authorize it. Active superadministrators automatically have view, submit and approve access to all enabled firewall groups, without explicit grants. Administer permission remains explicit. Ordinary users need a different authorized approver. Active superadministrators may approve their own requests; this is explicitly recorded and their active superadministrator status is rechecked before execution.

## Import lists

Choose **Address objects → Import list**. Upload UTF-8 CSV (optional BOM) or paste CSV with exactly these columns:

```csv
name,kind,value
portal_office,subnet,192.0.2.0/24
portal_host,subnet,192.0.2.1
portal_web,fqdn,host.example.com
portal_wildcard,wildcard_fqdn,*.example.com
```

Raw lists are also supported: paste or upload one IPv4 address/subnet, FQDN or wildcard FQDN (`*.example.com`) per line. Blank lines are ignored. The importer detects types automatically and validates each value. Subnet host bits are normalized to the network address (`192.0.2.9/24` becomes `192.0.2.0/24`); host IPs are stored as /32. URLs, ports, malformed IPs and IPv6 are rejected. Use **Object name prefix** to prepend up to 40 letters, digits, dots, underscores or hyphens, including your preferred separator (for example `trend_`). Names are exactly the supplied address (after surrounding whitespace is removed), optionally preceded by the prefix. Wildcards, subnet slashes, letter case and an explicitly supplied /32 are preserved in names. Stored address values are normalized separately. Names over 79 characters are rejected in the preview and are never shortened or hashed. CSV imports retain explicit names and also accept the prefix. Review names, types and values before confirming. Duplicate generated names or existing catalog names are reported as errors.

Maximum: 1,000 data rows and 1 MiB. Preview reports invalid rows, duplicate names, and names already used by local objects or groups. These validation errors must be corrected before confirmation. Restricted addresses are reported separately: confirmation skips refused rows and creates the allowed objects in one transaction. Other errors, including a changed target group or a newly conflicting catalog name, roll back the import. It never overwrites existing definitions. Previews expire in 30 minutes and belong to their creator; repeating a completed confirmation does not create duplicates and retains its original refusal results.

## Restricted addresses

Active Superadministrators and users in the **Administrator** role can manage **Configuration → Restricted addresses**, independently of catalog grants. Operators, approvers, and viewers cannot access or change this configuration, including through direct URLs. Add, edit, delete, search, or import protected IPv4 hosts/subnets, FQDNs, and wildcard FQDNs. File and paste imports accept one value per line or the same `name,kind,value` CSV header; CSV names are ignored. Configuration imports immediately add valid rows, skip normalized duplicates, and report invalid rows. The limits are 1,000 data rows and 1 MiB; exceeding either limit imports nothing. Configuration changes are audited.

IPv4 restrictions reject any overlapping submitted network, including a larger subnet containing a protected host. Restriction `10.1.1.0/8` is stored as `10.0.0.0/8` and refuses both `10.1.1.2` and `10.1.1.2/24`. This also prevents submitting `0.0.0.0/0` to include protected ranges.

A plain domain restriction protects that domain and all its descendants: `domain.com` refuses `domain.com`, `site.domain.com`, and `*.domain.com`. Wildcard restrictions protect descendants: `*.domain.com` refuses `site.domain.com` and overlapping wildcard submissions, but permits the bare `domain.com`. A wildcard covering a protected domain is also refused: restriction `site.domain.com` blocks submission `*.domain.com`. Comparisons ignore case and trailing dots, use whole domain labels, and allow unrelated domains such as `otherdomain.com`. There are no DNS lookups, arbitrary glob patterns, or IPv6 restrictions.

Single additions and edits are checked in the catalog service. Bulk preview lists allowed and refused addresses; confirmation checks the current restriction list again and displays each final refused value and its reason. If every address is refused, no objects are created. Adding restrictions leaves existing catalog objects, memberships, submitted requests, and installed firewall configuration unchanged.

Administrators and Superadministrators have an unchecked **Override restricted addresses** option on object and import forms. It applies only to that submission; every successful matching save records an override audit event identifying the object and restriction. Catalog creation still requires existing catalog permissions. Operators cannot use the override. Privilege is checked again at import confirmation, and the override choice is bound to the stored preview.

## Targets and installation

Superadministrators configure **Firewall groups** with one explicit VDOM per firewall. Empty groups are permitted so a group can be created before registering the first firewall. Firewall registration/editing requires at least one enabled group. Membership edits cannot remove the last enabled group of an existing firewall. Duplicate firewalls and disabled destinations are rejected. New groups grant their creating superadministrator the four explicit capabilities.

Choose **New request**, select local objects and/or address groups, and choose a firewall group by name. Preview shows object dependencies and destinations. Submit captures current definitions, revisions, address-group memberships and destinations. Later catalog/group edits do not alter submitted intent. A newly added member does not become a destination of an existing request; removing a submitted member prevents approval/execution until a new request is submitted. An authorized approver approves the complete request. Superadministrators can approve their own requests. The separate executor installs address dependencies before groups and verifies the resulting device state.

Matching existing addresses need no write and do not become portal-owned. Conflicting existing addresses can be changed only when portal-owned and matching the configured object name prefix. Address-group installation adds requested members and preserves other device members; removing a local member does not remove it remotely. Missing groups require a validated create-group capability. There is no per-firewall group allowlist; the approved installation snapshot determines which address groups to install.

### Firewall connection configuration

Select HTTP or HTTPS for each firewall. A blank port uses 80 for HTTP or 443 for HTTPS; custom ports are supported. Existing registrations retain HTTPS and their current ports. HTTPS accepts self-signed certificates by ignoring certificate validation errors. API Token is the only firewall authentication field; leave it blank when editing to retain the stored encrypted token. Login and Allowed groups have been removed.

Object name prefix is a portal naming rule, not a FortiGate feature. For example, `portal_` permits address writes to names beginning with `portal_`. An empty prefix allows names without a required prefix. The value `all` is a literal prefix, not a wildcard. It does not select a VDOM or an address group.

Version-wide write profiles remain empty. A device-scoped profile is validated for HTTP 192.168.100.38:80, root VDOM, FortiOS v7.0.13 (observed build 566): IPv4, FQDN and wildcard FQDN address installation and group creation/member updates. Exact names containing wildcard markers and subnet slashes were also validated. It does not authorize deletion, another endpoint or VDOM, or another version. Request approval and the applicable group permissions are still required. Other device profiles require separate validation; local simulation alone does not enable writes.

## Outcomes and recovery

Request Details shows approval separately from execution, immutable definitions, resolved destinations, and per-target steps. All successful destinations yield SUCCEEDED. A terminal mixture of success/failure yields PARTIALLY_SUCCEEDED. Ambiguous writes or interrupted execution require RECONCILIATION_REQUIRED. No cross-device rollback is attempted.

An administrator with administer permission on all destinations can run read-only reconciliation in the UI or use:

```powershell
.venv/Scripts/python.exe manage.py reconcile_requests REQUEST_UUID --installation --actor ADMIN_USERNAME
```

Reconciliation never writes. Interrupted outcomes must be established before untouched destinations resume; completed targets are never replayed. Failed targets require a new approved request. Review the snapshot of a retry because the catalog may have changed.

Device inventory and usage scans remain separate read-only observations. A changed catalog revision does not prove device drift. Legacy requests retain their historical records and reconciliation path; new direct-target submissions are disabled. The upgrade cancels untouched pending direct-target requests. The new form offers group installation only.

Object and group usage targets a firewall group by name and scans each member firewall / VDOM. View results opens saved observations without scanning. Separate tables show address objects and address groups whose name and resource type also exist in the local catalog. Classification uses the complete firewall policy/group graph before filtering, including nested group references. Catalog view and view permission on the selected firewall group are required. A failed device produces an incomplete result while other members continue. Each scan replaces its VDOM's previous result, including incomplete results; audit events remain. Older results explicitly indicate that address groups were not assessed until scanned again.

## Upgrade

The group-permission upgrade discards old individual VDOM grants with explicit user authorization. Firewalls without an enabled group receive a named initial group. Active superadministrators receive explicit capabilities on existing enabled groups; configure other users through Users & access before they can access devices. The local catalog and historical records remain.

Cancellation atomically marks request execution and pending destinations CANCELLED, with finish times. Requesters can cancel before execution begins, including after approval. Running/completed operations retain their real outcome. Existing cancelled records with pending execution are repaired.

Back up SQLite and protect encryption keys before applying migrations. Migrations add tables without rewriting historical requests or digests. The local catalog starts empty: existing ownership records and device scans do not contain sufficient definitions for automatic conversion. Create or import desired definitions locally.


## Add objects to an existing address group

Create address object and Import address objects offer an optional Add to address group selection. Choosing No group keeps new objects standalone. Choosing an existing local group adds the saved objects without replacing its members, advances the group revision and records an audit event. No firewall installation is triggered.

An import preview records the selected group's ID, name and revision alongside the rows. Confirmation creates all objects and adds their memberships in one transaction. A missing or changed group invalidates the preview and rolls back object creation; preview again to use the updated group. Changing posted group fields at confirmation does not change the stored selection. Repeated confirmation does not duplicate membership or advance the revision again.


## Delete selected address objects

Catalog managers can select individual rows or Select all shown on Address objects, then choose Delete selected. Up to 500 objects can be deleted in one operation. A separate confirmation lists the selected names and values; its signed selection expires after 15 minutes and is bound to the requesting user.

Deletion applies only to local objects. Existing device configuration and immutable request history remain unchanged. Objects belonging to local address groups must be removed from those groups first. Missing or changed objects, protected memberships, or invalid confirmations prevent deletion of the entire selection. Every deleted object receives the normal catalog deletion audit event.
