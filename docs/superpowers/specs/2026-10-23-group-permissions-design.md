# Group permissions and cancellation

The user requires every firewall to belong to at least one group, user access to be granted to groups, and new requests to target a group name. The user permits removing existing permissions and incompatible database data. Implementation remains in this checkout and conversation.

Use explicit view/submit/approve/administer grants on FirewallGroup, replacing individual VDOM grants. Local catalog permissions remain separate. Group permission covers its configured firewall/VDOM members. A request records its group ID/name and immutable destinations; approval and execution must recheck the exact selected group's permissions, never borrow permission from an overlapping group. Membership changes must not add destinations to an existing request; removed destinations fail closed.

Approaches: preserving individual grants would contradict the new authorization model; expanding them into shared groups could broaden access. Chosen: discard old scope grants, backfill groups for ungrouped devices, grant initial group capabilities only to active superadministrators so configuration remains possible. Other users receive no device access until configured. Existing snapshots remain historical; legacy direct-target submissions are disabled.

Firewall registration and editing require groups. Group membership edits and deletion cannot orphan existing firewalls. Empty groups are permitted so the first group can be created before the first firewall. Group names appear in forms, history and request details.

Cancellation atomically marks request execution and pending targets CANCELLED and records finish time, for both installation and historical request workflows. Cancellation is allowed before execution begins, including an approved request still pending execution. Already running or completed writes cannot be represented as cancelled. Existing cancelled/pending records are repaired by migration. No live firewall writes are required.
