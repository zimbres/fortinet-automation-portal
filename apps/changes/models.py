import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, F

OPERATIONS = ['create_address', 'edit_address', 'delete_address', 'add_group_member', 'remove_group_member']


class ChangeRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='submitted_changes')
    vdom = models.ForeignKey('firewalls.VDOM', on_delete=models.PROTECT)
    operation = models.CharField(max_length=30, choices=[(x, x.replace('_', ' ').title()) for x in OPERATIONS])
    payload = models.JSONField()
    payload_digest = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=100)
    self_approved = models.BooleanField(default=False,editable=False)
    approval_status = models.CharField(max_length=12, default='PENDING', choices=[(x,x.title()) for x in ['PENDING','APPROVED','REJECTED','CANCELLED']])
    execution_status = models.CharField(max_length=30, default='PENDING', choices=[(x,x.replace('_',' ').title()) for x in ['PENDING','RUNNING','SUCCEEDED','FAILED','RECONCILIATION_REQUIRED','CANCELLED']])
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='approved_changes')
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['requester','idempotency_key'], name='request_idempotency'),
            models.CheckConstraint(condition=(Q(approver__isnull=True) | ~Q(approver=F('requester')) | Q(self_approved=True)) & (Q(self_approved=False) | Q(approver=F('requester'),approver__isnull=False)), name='independent_approver'),
            models.CheckConstraint(condition=~Q(approval_status='APPROVED') | Q(approver__isnull=False), name='approved_has_approver'),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = type(self).objects.get(pk=self.pk)
            if any(getattr(self, field) != getattr(original, field) for field in
                   ['requester_id','vdom_id','operation','payload','payload_digest','idempotency_key']):
                raise ValidationError('Submitted intent is immutable. Submit a new request.')
        super().save(*args, **kwargs)


class ExecutionStep(models.Model):
    request = models.ForeignKey(ChangeRequest, on_delete=models.PROTECT, related_name='steps')
    step_type = models.CharField(max_length=50)
    before_state = models.JSONField(default=dict)
    after_state = models.JSONField(default=dict)
    result = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)


class ExecutorLease(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    owner = models.CharField(max_length=100)
    expires_at = models.DateTimeField()


class ObjectReference(models.Model):
    vdom = models.ForeignKey('firewalls.VDOM', on_delete=models.PROTECT)
    name = models.CharField(max_length=79)
    originating_request = models.ForeignKey(ChangeRequest, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['vdom','name'], name='unique_owned_object')]


class InstallationRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='installations')
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name='+')
    snapshot = models.JSONField()
    payload_digest = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=100)
    self_approved = models.BooleanField(default=False,editable=False)
    approval_status = models.CharField(max_length=12, default='PENDING')
    execution_status = models.CharField(max_length=30, default='PENDING')
    recovery_required = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['requester', 'idempotency_key'], name='installation_idempotency'),
                       models.CheckConstraint(condition=(Q(approver__isnull=True) | ~Q(approver=F('requester')) | Q(self_approved=True)) & (Q(self_approved=False) | Q(approver=F('requester'),approver__isnull=False)), name='installation_independent_approver'),
                       models.CheckConstraint(condition=~Q(approval_status='APPROVED') | Q(approver__isnull=False), name='installation_approved_has_approver')]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            old = type(self).objects.get(pk=self.pk)
            if any(getattr(self, key) != getattr(old, key) for key in ['requester_id', 'snapshot', 'payload_digest', 'idempotency_key']):
                raise ValidationError('Submitted installation intent is immutable.')
        super().save(*args, **kwargs)


class InstallationTarget(models.Model):
    request = models.ForeignKey(InstallationRequest, on_delete=models.PROTECT, related_name='targets')
    vdom = models.ForeignKey('firewalls.VDOM', on_delete=models.PROTECT)
    destination = models.JSONField()
    execution_status = models.CharField(max_length=30, default='PENDING')
    error_message = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['request', 'vdom'], name='installation_unique_target')]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            old = type(self).objects.get(pk=self.pk)
            if any(getattr(self, key) != getattr(old, key) for key in ['request_id', 'vdom_id', 'destination']):
                raise ValidationError('Submitted destination is immutable.')
        super().save(*args, **kwargs)


class InstallationStep(models.Model):
    target = models.ForeignKey(InstallationTarget, on_delete=models.PROTECT, related_name='steps')
    step_type = models.CharField(max_length=40)
    resource_type = models.CharField(max_length=10)
    name = models.CharField(max_length=79)
    before_state = models.JSONField(default=dict)
    after_state = models.JSONField(default=dict)
    result = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)


class InstalledResource(models.Model):
    vdom = models.ForeignKey('firewalls.VDOM', on_delete=models.PROTECT)
    resource_type = models.CharField(max_length=10)
    name = models.CharField(max_length=79)
    originating_target = models.ForeignKey(InstallationTarget, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['vdom', 'resource_type', 'name'], name='unique_installed_resource')]
