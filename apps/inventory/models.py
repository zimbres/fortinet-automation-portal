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


class ThreatFeedScope(models.Model):
    firewall_group = models.OneToOneField('firewalls.FirewallGroup', on_delete=models.PROTECT, related_name='feed_scope')
    slug = models.SlugField(max_length=120, unique=True)

    def __str__(self):
        return self.firewall_group.name


class ThreatFeed(models.Model):
    group = models.ForeignKey(AddressGroup, on_delete=models.PROTECT, related_name='threat_feeds')
    scope = models.ForeignKey(ThreatFeedScope, on_delete=models.PROTECT, related_name='feeds')
    slug = models.SlugField(max_length=120)
    enabled = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=0)
    ip_text = models.TextField(blank=True, default='')
    domain_text = models.TextField(blank=True, default='')
    approved_request = models.ForeignKey('changes.InstallationRequest', null=True, blank=True,
                                         on_delete=models.PROTECT, related_name='published_feeds')

    class Meta:
        ordering = ['scope__firewall_group__name', 'group__entry__name']
        constraints = [
            models.UniqueConstraint(fields=['scope', 'group'], name='unique_scoped_feed_group'),
            models.UniqueConstraint(fields=['scope', 'slug'], name='unique_scoped_feed_slug'),
        ]

    def __str__(self):
        return f'{self.scope} / {self.group.entry.name}'


class ThreatFeedIdentity(models.Model):
    """Reserve approved URL identities without making content downloadable."""
    scope = models.ForeignKey(ThreatFeedScope, on_delete=models.CASCADE)
    group = models.ForeignKey(AddressGroup, on_delete=models.CASCADE)
    slug = models.SlugField(max_length=120)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['scope','group'], name='unique_reserved_feed_group'),
            models.UniqueConstraint(fields=['scope','slug'], name='unique_reserved_feed_slug'),
        ]


class FeedAccount(models.Model):
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    feeds = models.ManyToManyField(ThreatFeed, related_name='accounts', blank=True)

    class Meta:
        ordering = ['username']

    def __str__(self):
        return self.username


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
