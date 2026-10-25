# Restricted addresses

## Intent and scope

Protect addresses that operators must not add to the local address-object catalog. Add a Restricted Addresses page following the existing Address Objects conventions, with search, individual add/edit/delete, and file or pasted-list import. Only active SuperAdmins and members of the existing Administrator role may access or manage this configuration.

## Approach

Use a separate database-backed restriction model and a shared matcher called by the existing catalog mutation service. This is the single suitable approach for the current application: browser-only checks are bypassable, and mixing restrictions into AddressObject would make them selectable for installation. Reuse existing Django forms, templates, import limits, and audit services. No new API platform or external service is needed.

## Matching rules

- Accept the current catalog types: IPv4 hosts/subnets, FQDNs, and wildcard FQDNs (`*.example.com`). Arbitrary glob syntax and IPv6 are outside this change.
- Normalize restriction subnet input with host bits, so `10.1.1.0/8` becomes `10.0.0.0/8`. Apply the same normalization to submitted subnet values before matching and saving, so `10.1.1.2/24` is checked as `10.1.1.0/24`.
- Refuse any submitted IP network that overlaps a restricted network, including broader networks that contain a restricted address. This closes the bypass of submitting a larger subnet.
- Compare domains case-insensitively with trailing dots removed and whole-label boundaries. A restriction for `domain.com` blocks itself, its subdomains, and wildcard submissions covering it. A wildcard restriction protects its descendant domain space; overlapping wildcard submissions are refused. Unrelated suffixes such as `otherdomain.com` remain allowed. No DNS resolution is performed.

## Override and authorization

The user confirmed that Admins and SuperAdmins may override. Provide an explicit, unchecked override option on single-address and catalog-import forms, visible only to those roles. Validate override authorization again in the service; operator-supplied override flags must never bypass restrictions. Existing catalog grants still govern address creation. Record each successful override and the matched restriction in the audit trail using allowlisted metadata.

## Bulk behavior

Retain preview and confirmation. Show refused rows with their submitted value and matched restriction, while permitting confirmation of the allowed rows. Recheck restrictions and override authorization at confirmation so configuration changes after preview cannot bypass enforcement. Store the outcome so repeat confirmation does not create duplicates or lose refusal details. Preserve existing error behavior for malformed input and stale group revisions; only restriction refusals permit partial success. Report created and refused counts and individual refusal reasons, including when every row is refused.

Restriction imports accept one value per line or the existing `name,kind,value` CSV format, using type/value for restrictions. Keep the existing 1 MiB and 1,000-row bounds. Normalize and deduplicate restrictions; show invalid rows and import valid configuration rows with an explicit result.

## Existing data and boundaries

Restrictions apply to new catalog additions and edits. Adding a restriction does not delete existing objects or alter installations, firewall policy, or group membership. All enforcement belongs on the server. Configuration changes and overrides are audited. Keep domain values escaped in HTML.

## Verification

Test subnet normalization and overlap, domain boundaries and wildcard overlap, allowed values, role checks on every configuration action, forged overrides, single saves/edits, mixed and all-refused imports, rechecks after preview, and repeat confirmations. Run relevant existing catalog and permission tests, Django system checks, and migration drift checks. Document the matching and override behavior in the catalog guide.

## Implementation choices

The overlap rule, explicit override checkbox, non-retroactive scope, and preserved malformed-input behavior are proposed implementation choices. Page layout and internal helper names follow existing project conventions.
