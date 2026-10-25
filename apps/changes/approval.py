"""Approval policy shared by installation and historical executors."""
from django.core.exceptions import PermissionDenied
from apps.accounts.permissions import can_self_approve


def require_valid_approval(item):
    if item.approval_status != 'APPROVED' or not item.approver_id:
        raise PermissionDenied('Approval is required.')
    if item.approver_id == item.requester_id:
        if not item.self_approved or not can_self_approve(item.approver):
            raise PermissionDenied('Self-approval requires an active superadministrator.')
