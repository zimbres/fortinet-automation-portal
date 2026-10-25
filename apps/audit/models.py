from django.conf import settings
from django.db import models


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError('Audit events are append-only.')

    def delete(self):
        raise ValueError('Audit events are append-only.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValueError('Audit events are append-only.')


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    event_type = models.CharField(max_length=100, db_index=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at', '-pk']

    @property
    def actor_display(self):
        if self.actor_id:
            return self.actor.username
        # Derive historical labels without rewriting append-only audit records.
        return {
            'change.execution_finished': 'Executor (background runner)',
            'installation.target_finished': 'Executor (background runner)',
            'login.failed': 'Unauthenticated login attempt',
            'credentials.rotated': 'Credential rotation command',
        }.get(self.event_type, 'System')

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError('Audit events are append-only.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Audit events are append-only.')
