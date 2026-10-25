"""Seed historical direct requests, whose submission is no longer supported."""
from apps.changes.models import ChangeRequest
from apps.changes.services import normalize_payload, digest_intent


def legacy_request(*,actor,vdom,operation,payload,idempotency_key):
    payload=normalize_payload(operation,payload)
    return ChangeRequest.objects.create(requester=actor,vdom=vdom,operation=operation,payload=payload,
        payload_digest=digest_intent(vdom.pk,operation,payload),idempotency_key=idempotency_key)
