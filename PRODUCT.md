# Fortigate Automation Portal

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Modular Python 3.14 monolith using Django 6.1, Django Templates, HTMX, and Tailwind CSS. SQLite with Django ORM; HTTPX for REST integration; Python's `ipaddress` for IPv4 and network validation. Deployment uses Docker Compose, Gunicorn, and Nginx with HTTPS.

OIDC authentication through mozilla-django-oidc or an equivalent integration; SAML through a Keycloak broker when needed. Production runs one mandatory executor alongside Gunicorn in the same non-root container, with shared lifecycle supervision and stdout logs. Development can run the executor in a separate terminal. React, Redis, and Celery are excluded from the MVP.

## Language

Write the application and all project documentation in English, including interface copy, validation messages, and developer documentation. Collaboration with the user remains in Portuguese.

## Users

Internal users, especially security teams, with explicit View, Submit, Approve, and Administer grants scoped to firewall groups. A superadministrator provisions users. Role labels do not grant access by themselves.

## Product Purpose

The portal lets authorized people without direct firewall access add IP addresses and FQDNs to an existing address group already used by firewall rules. For example, a security team can submit malicious indicators quickly to a preconfigured block group without receiving firewall credentials. Each indicator is an address object; the address group collects those objects for the existing policy. Firewall administrators must configure and verify that policy first: adding group members does not create a deny rule or change policy order.

Provide a secure, auditable, maintainable internal portal for registering firewalls and managing address objects and address group membership through approved changes. Support IP addresses, subnets, FQDNs, and wildcard FQDNs by creating address objects and adding them to existing address groups.

## Operating Context

The application validates requests, checks permissions, reads the current FortiGate state, executes changes, and records the outcome. SQLite is the source of truth for the reusable local address-object and address-group catalog. FortiGate is authoritative for observed device configuration. Catalog changes require catalog permissions and audit but no approval; only installation on a firewall or firewall group requires an independently approved immutable request.

The environment uses mixed or other FortiOS versions. The exact versions must still be provided to define and validate the compatibility matrix.

## Capabilities and Constraints

- Register firewalls with an IP address, name, HTTP/HTTPS protocol, port, and encrypted API Token. No separate Login field is used.
- Allow a superadministrator to register users and assign roles. How provisioning integrates with OIDC remains to be defined.
- Register address objects for IP addresses, subnets, FQDNs, and wildcard FQDNs, and add those objects to existing address groups. Adding an entry means creating an address object and adding it to a group, rather than appending multiple values to an existing address object. Preserve the explicit option to select an existing address object instead of creating one.
- Require approval by another authorized user before starting a firewall execution workflow. Approval gates the start of the requested execution flow rather than individual steps within that flow. The requesting user must never approve their own request, including users with elevated roles. Exact approval roles, rejection behavior, and whether read-only inventory and connection checks also require approval remain to be defined.
- Execute changes in the backend and validate their actual outcome on the firewall.
- Check references before deleting an address.
- Alert on objects unused by firewall policies. Reference analysis must account for group membership, including nested groups, before classifying an object as unused. Scanning frequency and supported reference types remain to be defined; alerts do not authorize automatic deletion.
- List objects, groups, and members; add or remove only the requested member while preserving all other members.
- When adding to a group, offer an explicit choice between using an existing object and creating an object when needed. Group members are object names, not IP addresses directly.
- Allow users to select only authorized firewalls and VDOMs. Protect special objects and groups, externally managed resources, and resources outside the portal's namespace.
- Record idempotent change requests and distinguish approval status from execution status. Execution states include PENDING, RUNNING, SUCCEEDED, FAILED, and RECONCILIATION_REQUIRED; the approval state model remains to be specified. Never assume success after a timeout; reconcile against the firewall state.
- Serialize changes by firewall, VDOM, and group; account for concurrent changes made by external administrators.
- Log application events including logins, edits, approvals, and execution results. Audit the user, operation, timestamp, intent, before and after states, and outcome. Audit records are append-only at the application level, with structured logging; export to a protected external destination when required. Exclude credentials and other secrets from logs and state snapshots.
- Encrypt sensitive data stored in the database, including recoverable firewall credentials. Keep encryption keys outside the database and source control; define key provisioning and rotation before implementation. Application passwords, if local authentication is adopted, use Django password hashing rather than reversible encryption. This requirement supersedes the earlier token-storage-only-outside-SQLite restriction; external secret references remain an available option.
- Firewall API connections support HTTP or HTTPS. HTTPS ignores device certificate validation errors, including self-signed certificates, as explicitly requested. Use Fortinet REST accounts with minimum required permissions.
- Validate OIDC issuer, audience, signature, and expiration; use CSRF protection and secure session cookies in production.
- Protect backups of the database, configuration, and secrets, and test restoration.
- Planned pages: Dashboard, Address Objects, Address Groups, New Request, Operation History, and Firewall Administration. Counters must reflect real data; the supplied sample numbers are illustrative.
- Planned entities: Django user with an external identifier, firewall, VDOM unique within its firewall, change request, audit event, object reference, and firewall/VDOM permission.
- Approvals and unused-object alerts are part of the requested scope. Queues, additional notifications, and reports remain future additions.
- Open decisions: exact FortiOS versions, permitted namespace, role matrix, approval handling for read-only queries and connection checks, firewall authentication mechanism, encryption key management, identity provider configuration and user provisioning, unused-object scanning, and deployment destination.

## Product Principles

- Confirm the actual FortiGate state before declaring a change complete.
- Restrict every operation to its authorized scope and preserve shared objects.
- Maintain traceability from intent to outcome, including failures and uncertain results.
- Keep the architecture modular and simple; add queued processing when a demonstrated need arises.

## Evidence on Hand

The user supplied the requirements and architecture during initialization, including explicit support for both group inclusion modes and mixed FortiOS versions. The project directory was initially empty. Proposed endpoints require validation against the target versions; no integration has yet been executed against firewalls.

## Local catalog and installation update (2026-10-23)

The approved specification `docs/superpowers/specs/2026-10-23-local-catalog-installation-design.md` supersedes earlier approval and inventory wording above. Local objects/groups can be created, edited and deleted without an installation request. CSV upload or pasted CSV creates many objects after preview. Global catalog access is independent from firewall/VDOM grants. Requests target one firewall/VDOM or a configured firewall group, capturing definitions, dependencies and all destinations at submission. Existing group members on devices are preserved during installation. Remote deletion/member removal is not offered in the new workflow.

## Address-group creation authorization

Only active Administrators with Catalog Manage access, and active Superadministrators, may create local address groups. Catalog Manage alone allows address-object management and membership in existing groups, but does not authorize new address groups. This additional role check applies to creation; existing group editing and deletion retain their catalog permissions.
