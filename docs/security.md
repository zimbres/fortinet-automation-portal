# Security boundaries

Authorization is based on active identities and explicit VDOM capability grants; ordinary requesters require an independent approver; superadministrators may explicitly approve their own requests. Approval covers a fixed request digest, and the executor revalidates requester and approver permissions before writes. Application role labels alone grant no access; explicit firewall-group grants are authoritative.

Firewall API tokens are encrypted with authenticated Fernet encryption. External keys remain outside the database and Git. Application passwords use Django hashing. Token values are write-only in forms and omitted from logs. Audit metadata is allowlisted; execution snapshots select only address/group configuration fields.

OIDC uses signed ID tokens, nonce checking, PKCE, issuer/audience/expiration validation, and matching UserInfo subjects. Accounts must be provisioned with issuer/subject bindings; email does not establish identity and IdP group claims cannot elevate roles. Validate against the actual IdP before enabling production SSO. Production auth mode must be explicit.

Only superadministrators configure management endpoints. Each firewall selects HTTP or HTTPS and an explicit port. As requested, HTTPS device connections ignore certificate validation errors, including self-signed certificates. This applies only to firewall API connections; browser-facing HTTPS and OIDC settings retain their existing behavior. Restrict outbound network access to intended management networks and IdP endpoints on deployment infrastructure. Use source-IP-restricted API accounts with least privilege.

The app's audit layer prevents normal update/delete paths but is not a tamper-proof store. Local SQLite and key files require host-level access controls, encrypted backups, and operational monitoring. The five-minute executor lease cannot fence arbitrary paused processes or outside administrators at the firewall API; stop old executors during recovery and do not claim distributed mutation atomicity.
