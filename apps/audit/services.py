"""Audit payloads are allowlisted; arbitrary text never belongs in the log."""
import logging
from .models import AuditEvent

logger = logging.getLogger('portal.audit')
SAFE_KEYS = frozenset({
    'safe', 'username', 'user_id', 'firewall_id', 'vdom_id', 'request_id',
    'operation', 'status', 'reason_code', 'changed_fields', 'object_name',
    'self_approved', 'entry_id', 'batch_id', 'count', 'object_ids', 'group_id', 'target_id',
})


def sanitize_metadata(metadata):
    return {
        str(key): value if key in SAFE_KEYS and isinstance(value, (str, int, float, bool, type(None)))
        else '[REDACTED]'
        for key, value in metadata.items()
    }


def record_event(*, actor, event_type: str, request=None, metadata: dict | None = None) -> AuditEvent:
    event = AuditEvent.objects.create(
        actor=actor, event_type=event_type, metadata=sanitize_metadata(metadata or {}),
    )
    logger.info('audit_event', extra={'event_id': event.pk, 'event_type': event_type, 'actor_label': event.actor_display})
    return event
