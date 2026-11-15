# Threat feeds

Status: approved by the user on 2026-11-14.

The live-publication and unscoped-URL behavior below is superseded by the approved 2026-11-15-approved-threat-feeds-design.md. New publications and updates use approved snapshots scoped to firewall and address groups.

## Intent

Let active Administrators and Superadministrators publish local address groups as FortiGate-compatible plain text feeds. Each feed account has explicit assignments to published groups and can only download their feeds using HTTP Basic authentication.

## Approach

Serve live responses from Django using existing catalog membership. This reuses the authoritative local data and makes membership changes visible on the next fetch. Generated static files introduce synchronization and revocation problems; a separate service duplicates catalog and credential infrastructure. The live Django approach is recommended. No firewall connection or installation approval is involved.

## Configuration and URLs

- Add an administrator-only Threat Feeds configuration page with publication management, feed account creation, password replacement, activation/deactivation, and explicit group assignments.
- Publishing a group creates a unique URL slug derived from its name, replacing spaces with underscores: `My Address` becomes `my_address`. Resolve collisions with a suffix. Preserve the slug when the group is renamed so device configurations remain valid.
- Each published group exposes `/threat-feeds/<slug>/ip_list.txt` and `/threat-feeds/<slug>/domain_list.txt`.
- Add `APP_PUBLIC_URL` to environment configuration, example configuration, Docker Compose, and deployment documentation. It is an absolute HTTP/HTTPS base URL, without credentials, query, or fragment. Normalize trailing slashes and preserve an optional deployment path prefix.
- Display complete copyable URLs on the configuration page using this configured base, e.g. `APP_PUBLIC_URL=https://portal.example.com` yields `https://portal.example.com/threat-feeds/my_address/ip_list.txt`. Never include credentials in displayed URLs.
- If the public URL is unset or empty, use `http://127.0.0.1:8000` and display complete feed URLs using that base (user update after initial approval). Reject malformed nonempty values during settings validation.

## Access control

- Use a separate feed-account model with a unique username, Django password hash, active flag, and explicit many-to-many assignments to publications. These credentials cannot establish a portal session, use OIDC, or access Django administration.
- Only active Administrators and Superadministrators can manage publications, credentials, or assignments. Existing portal users and portal sessions do not authorize feed downloads.
- Recheck account status, publication status, and assignment on every fetch. Deactivation, unpublishing, password replacement, and assignment removal take effect immediately.
- Missing, malformed, or incorrect Basic credentials return HTTP 401 and a Basic challenge. Valid credentials without access return HTTP 404, as do absent or disabled publications.
- Support GET and HEAD only. Return private, non-cacheable responses so shared caches cannot retain authenticated group data.
- Use password validation and hashing; never put plaintext passwords or Authorization headers in audit metadata. Audit configuration changes with allowlisted metadata. Production deployment uses HTTPS as already configured.

## Content

- Generate UTF-8 `text/plain` responses with one indicator per line, deterministic ordering, duplicate removal, and a final newline for nonempty lists. Empty lists return HTTP 200 with an empty body.
- IP feeds contain existing subnet/address values; domain feeds contain existing FQDN and wildcard FQDN values, preserving wildcard semantics. Never emit catalog object names or HTML.
- This proposal uses the currently supported catalog types: IPv4 hosts/subnets, FQDNs, and wildcard FQDNs. Fortinet also accepts IP ranges, IPv6, and additional simple wildcard forms; extending catalog validation, restriction matching, and firewall installation for those types is outside this feature. The feed formatter must not invent or resolve addresses.
- Group membership changes are reflected at the next fetch. Deleting a source group removes its publication and assignments. Recreating a group never inherits old feed access automatically.

## Verification

Test role checks on every management operation; feed-only credential isolation; Basic authentication parsing and failures; assignment enforcement across multiple groups/accounts; immediate revocation; publication disabling and group deletion; stable slugs and collision handling; exact content separation, ordering, deduplication, empty feeds and HEAD responses; configured public URLs including path prefixes and invalid settings. Run relevant existing catalog/authentication tests, Django checks, and migration drift checks.

## Proposed implementation choices

Separate credentials, stable slugs, immediate live generation and no-store responses are implementation recommendations. Explicit assignments, configurable final public URLs and the localhost fallback are user requirements. No additional external service or dependency is needed.
