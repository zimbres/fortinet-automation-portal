from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from .crypto import encrypt_secret, decrypt_secret


class Firewall(models.Model):
    name = models.CharField(max_length=100, unique=True)
    hostname = models.CharField(max_length=253, validators=[RegexValidator(
        r'^[a-zA-Z0-9][a-zA-Z0-9.:-]*$', 'Enter a management IP address or hostname without a URL scheme.')])
    port = models.PositiveIntegerField(default=443, validators=[MinValueValidator(1), MaxValueValidator(65535)])
    protocol = models.CharField(max_length=5, choices=[('https','HTTPS'),('http','HTTP')], default='https')
    encrypted_token = models.TextField(blank=True, editable=False)
    enabled = models.BooleanField(default=True)
    observed_version = models.CharField(max_length=50, blank=True)
    allowed_namespace = models.CharField('Object name prefix', max_length=40, blank=True, validators=[RegexValidator(r'^[A-Za-z0-9_-]+$')], help_text='Optional portal naming rule, for example portal_. Leave blank to allow names without a required prefix; all is a literal prefix.')
    created_at = models.DateTimeField(auto_now_add=True)

    def set_token(self, token):
        self.encrypted_token = encrypt_secret(token)

    def get_token(self):
        return decrypt_secret(self.encrypted_token)

    def __str__(self):
        return self.name


class VDOM(models.Model):
    removed_at = models.DateTimeField(null=True, blank=True, editable=False)
    firewall = models.ForeignKey(Firewall, on_delete=models.PROTECT, related_name='vdoms')
    name = models.CharField(max_length=79)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['firewall', 'name'], name='unique_firewall_vdom')]

    def __str__(self):
        return f'{self.firewall.name} / {self.name}'


class FirewallGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class FirewallGroupMember(models.Model):
    group = models.ForeignKey(FirewallGroup, on_delete=models.CASCADE, related_name='members')
    firewall = models.ForeignKey(Firewall, on_delete=models.PROTECT)
    vdom = models.ForeignKey(VDOM, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['group', 'firewall'], name='unique_group_firewall'),
                       models.UniqueConstraint(fields=['group', 'vdom'], name='unique_group_vdom')]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.vdom_id and self.firewall_id and self.vdom.firewall_id != self.firewall_id:
            raise ValidationError('The VDOM must belong to the selected firewall.')
