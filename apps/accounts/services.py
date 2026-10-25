from django.contrib.auth.models import Group
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.audit.services import record_event
from .models import User, GroupGrant, CatalogGrant
from .permissions import require_superadmin

ROLES = ('Viewer', 'Operator', 'Approver', 'Administrator', 'Superadministrator')


@transaction.atomic
def provision_user(*, actor, username: str, role_names: list[str]) -> User:
    require_superadmin(actor)
    if not set(role_names).issubset(ROLES):
        raise ValidationError('Unknown role.')
    user = User(username=username, is_superuser='Superadministrator' in role_names,
                is_staff='Superadministrator' in role_names)
    user.set_unusable_password()
    user.full_clean()
    user.save()
    user.groups.set([Group.objects.get_or_create(name=name)[0] for name in role_names])
    record_event(actor=actor, event_type='user.created', metadata={'user_id': user.pk})
    return user


@transaction.atomic
def update_user(*, actor, user_id, username, email, role_names, group_grants,
                catalog_access, password='', external_issuer='', external_subject='', is_active=True, require_password_change=None):
    require_superadmin(actor)
    user = User.objects.get(pk=user_id)
    if user.external_issuer or user.external_subject:
        if require_password_change:
            raise ValidationError('OIDC password requirements are managed by the identity provider.')
        if password:
            raise ValidationError('OIDC account passwords are managed by the identity provider.')
        username,email = user.username,user.email
        external_issuer,external_subject = user.external_issuer,user.external_subject
    capabilities = {'view','submit','approve','administer'}
    if not set(role_names).issubset(ROLES) or not set(group_grants).issubset(capabilities):
        raise ValidationError('Unknown role or scope capability.')
    if catalog_access not in ('','catalog_view','catalog_manage'):
        raise ValidationError('Unknown catalog access.')
    superadmin = 'Superadministrator' in role_names
    if user.pk == actor.pk and (not superadmin or not is_active):
        raise ValidationError('You cannot deactivate or remove superadministrator access from your current account.')
    if user.is_superuser and user.is_active and (not superadmin or not is_active) and not User.objects.filter(is_active=True,is_superuser=True).exclude(pk=user.pk).exists():
        raise ValidationError('At least one active superadministrator is required.')
    from apps.firewalls.models import FirewallGroup
    normalized = {cap:set(ids) for cap,ids in group_grants.items()}
    ids = set().union(*normalized.values()) if normalized else set()
    if FirewallGroup.objects.filter(pk__in=ids).count() != len(ids):
        raise ValidationError('One or more selected firewall groups no longer exist.')
    user.username,user.email = username,email
    user.external_issuer,user.external_subject = external_issuer,external_subject
    user.is_active,user.is_superuser,user.is_staff = is_active,superadmin,superadmin
    if password:
        from django.contrib.auth.password_validation import validate_password
        validate_password(password,user=user)
        user.set_password(password)
    if require_password_change is not None:
        if require_password_change and (external_issuer or external_subject or not user.has_usable_password()):
            raise ValidationError('A password change can only be required for a local account with a password.')
        user.require_password_change = require_password_change
    user.full_clean()
    user.save()
    custom_groups = list(user.groups.exclude(name__in=ROLES))
    user.groups.set(custom_groups+[Group.objects.get_or_create(name=name)[0] for name in role_names])
    GroupGrant.objects.filter(user=user).delete()
    GroupGrant.objects.bulk_create([GroupGrant(user=user,firewall_group_id=vd,capability=cap) for cap,vd_ids in normalized.items() for vd in vd_ids])
    CatalogGrant.objects.filter(user=user).delete()
    if catalog_access: CatalogGrant.objects.create(user=user,capability=catalog_access)
    record_event(actor=actor,event_type='user.updated',metadata={'user_id':user.pk})
    return user


@transaction.atomic
def deactivate_user(*, actor, user_id):
    require_superadmin(actor)
    user = User.objects.get(pk=user_id)
    if user.pk == actor.pk:
        raise ValidationError('You cannot delete your current account.')
    if user.is_superuser and user.is_active and not User.objects.filter(is_active=True,is_superuser=True).exclude(pk=user.pk).exists():
        raise ValidationError('At least one active superadministrator is required.')
    if user.is_active:
        user.is_active = False
        user.save(update_fields=['is_active'])
        record_event(actor=actor,event_type='user.deactivated',metadata={'user_id':user.pk})
    return user
