from django.db import models
from django.conf import settings
import uuid


class InventoryScan(models.Model):
    vdom = models.ForeignKey('firewalls.VDOM', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    complete = models.BooleanField(default=False)
    findings = models.JSONField(default=dict)
    group_findings = models.JSONField(null=True,blank=True,default=None)
    coverage = models.CharField(max_length=300, default='IPv4 firewall policies and address groups only; other CMDB consumers are not assessed.')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['vdom'],name='unique_current_usage_scan')]


class CatalogEntry(models.Model):
    name = models.CharField(max_length=79, unique=True)
    entry_type = models.CharField(max_length=10, choices=[('address', 'Address'), ('group', 'Group')])
    revision = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class AddressObject(models.Model):
    entry = models.OneToOneField(CatalogEntry, on_delete=models.CASCADE, related_name='address')
    kind = models.CharField(max_length=20, choices=[('subnet', 'IPv4 host / subnet'), ('fqdn', 'FQDN'), ('wildcard_fqdn', 'Wildcard FQDN')])
    value = models.CharField(max_length=253)

    def __str__(self):
        return self.entry.name


class AddressGroup(models.Model):
    description = models.CharField(max_length=500, blank=True, default='')
    entry = models.OneToOneField(CatalogEntry, on_delete=models.CASCADE, related_name='address_group')
    members = models.ManyToManyField(AddressObject, related_name='address_groups', blank=True)

    def __str__(self):
        return self.entry.name


class AddressRestriction(models.Model):
    kind = models.CharField(max_length=20, choices=AddressObject._meta.get_field('kind').choices)
    value = models.CharField(max_length=253)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['value', 'kind']
        constraints = [models.UniqueConstraint(fields=['kind', 'value'], name='unique_address_restriction')]

    def __str__(self):
        return self.value


class CatalogImport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    group_snapshot = models.JSONField(null=True, blank=True, default=None)
    rows = models.JSONField(default=list)
    errors = models.JSONField(default=list)
    refused_rows = models.JSONField(default=list)
    override_restrictions = models.BooleanField(default=False)
    digest = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True)
    created_objects = models.ManyToManyField(AddressObject, blank=True)

    @property
    def allowed_rows(self):
        refused_names = {row['name'] for row in self.refused_rows}
        return [row for row in self.rows if row['name'] not in refused_names]
