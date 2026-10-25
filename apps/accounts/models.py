from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class User(AbstractUser):
    require_password_change = models.BooleanField(default=False)

    @property
    def password_change_needed(self):
        return self.require_password_change and self.has_usable_password() and not (self.external_issuer or self.external_subject)

    avatar = models.FileField(upload_to='avatars/', blank=True)

    @property
    def avatar_url(self):
        if self.avatar:
            from django.urls import reverse
            from urllib.parse import urlencode
            return reverse('profile_picture') + '?' + urlencode({'v':self.avatar.name.rsplit('/',1)[-1]})
        if not self.email.strip():
            return ''
        import hashlib
        digest = hashlib.sha256(self.email.strip().lower().encode('utf-8')).hexdigest()
        return f'https://www.gravatar.com/avatar/{digest}?s=96&d=404&r=g'

    external_issuer = models.URLField(max_length=512, blank=True)
    external_subject = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower('email'), condition=~Q(email=''), name='unique_login_email'),
            models.UniqueConstraint(
                fields=['external_issuer', 'external_subject'],
                condition=~Q(external_subject=''), name='unique_external_identity',
            ),
            models.CheckConstraint(
                condition=(Q(external_issuer='', external_subject='') |
                           (~Q(external_issuer='') & ~Q(external_subject=''))),
                name='complete_external_identity',
            ),
        ]


class GroupGrant(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_grants')
    firewall_group = models.ForeignKey('firewalls.FirewallGroup', on_delete=models.CASCADE, related_name='grants')
    capability = models.CharField(max_length=20, choices=[(x, x.title()) for x in ['view', 'submit', 'approve', 'administer']])

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'firewall_group', 'capability'], name='unique_group_capability')]


class CatalogGrant(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='catalog_grants')
    capability = models.CharField(max_length=20, choices=[('catalog_view', 'View catalog'), ('catalog_manage', 'Manage catalog')])

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'capability'], name='unique_catalog_grant')]
