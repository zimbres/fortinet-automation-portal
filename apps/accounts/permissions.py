from django.core.exceptions import PermissionDenied
from django.db.models import Q
from .models import GroupGrant, User

SUPERADMIN_CAPABILITIES = frozenset({'view', 'submit', 'approve'})
CAPABILITIES = SUPERADMIN_CAPABILITIES | {'administer'}


def require_catalog_capability(user, capability):
    from .models import CatalogGrant
    if capability not in ('catalog_view', 'catalog_manage'):
        raise PermissionDenied('Unknown catalog permission.')
    active = User.objects.filter(pk=user.pk, is_active=True).first() if user.pk else None
    if not active:
        raise PermissionDenied('This account is not active.')
    allowed = ['catalog_manage'] if capability == 'catalog_manage' else ['catalog_view', 'catalog_manage']
    if not active.is_superuser and not CatalogGrant.objects.filter(user=user, capability__in=allowed).exists():
        raise PermissionDenied('You do not have permission for the local catalog.')


def require_capability(user, vdom, capability: str) -> None:
    # Re-read active state to avoid stale session objects authorizing execution.
    active = User.objects.filter(pk=user.pk,is_active=True).first() if user.pk else None
    if not active:
        raise PermissionDenied('This account is not active.')
    if capability not in CAPABILITIES:
        raise PermissionDenied('Unknown firewall permission.')
    if not vdom.enabled or vdom.removed_at is not None or not vdom.firewall.enabled:
        raise PermissionDenied('This firewall scope is disabled.')
    if active.is_superuser and capability in SUPERADMIN_CAPABILITIES:
        from apps.firewalls.models import FirewallGroupMember
        if FirewallGroupMember.objects.filter(vdom=vdom,group__enabled=True).exists():
            return
    if not GroupGrant.objects.filter(user_id=user.pk, firewall_group__enabled=True,
            firewall_group__members__vdom=vdom, capability=capability).exists():
        raise PermissionDenied('You do not have permission through a firewall group.')


def require_group_capability(user, group_id, capability):
    active = User.objects.filter(pk=user.pk,is_active=True).first() if user.pk else None
    if not active:
        raise PermissionDenied('This account is not active.')
    if capability not in CAPABILITIES:
        raise PermissionDenied('Unknown firewall group permission.')
    from apps.firewalls.models import FirewallGroup
    if not FirewallGroup.objects.filter(pk=group_id,enabled=True).exists():
        raise PermissionDenied('This firewall group is disabled or unavailable.')
    if active.is_superuser and capability in SUPERADMIN_CAPABILITIES:
        return
    if not GroupGrant.objects.filter(user_id=user.pk,firewall_group_id=group_id,capability=capability).exists():
        raise PermissionDenied('You do not have permission for this firewall group.')


def require_superadmin(user):
    if not user.pk or not User.objects.filter(pk=user.pk, is_active=True, is_superuser=True).exists():
        raise PermissionDenied('Only a superadministrator can perform this action.')


def can_manage_restrictions(user):
    if not user.pk:
        return False
    return User.objects.filter(pk=user.pk, is_active=True).filter(
        Q(is_superuser=True) | Q(groups__name='Administrator')
    ).exists()


def require_restriction_management(user):
    if not can_manage_restrictions(user):
        raise PermissionDenied('Restricted addresses require Administrator or Superadministrator access.')


def visible_vdoms(user, capability='view'):
    from apps.firewalls.models import VDOM
    active = User.objects.filter(pk=user.pk,is_active=True).first() if user.is_authenticated else None
    if not active or capability not in CAPABILITIES:
        return VDOM.objects.none()
    scopes=VDOM.objects.filter(enabled=True,removed_at__isnull=True,firewall__enabled=True)
    if active.is_superuser and capability in SUPERADMIN_CAPABILITIES:
        scopes=scopes.filter(firewallgroupmember__group__enabled=True)
    else:
        scopes=scopes.filter(firewallgroupmember__group__enabled=True,
            firewallgroupmember__group__grants__user=user,
            firewallgroupmember__group__grants__capability=capability)
    return scopes.select_related('firewall').distinct()


def can_self_approve(user):
    return bool(user.pk and User.objects.filter(pk=user.pk,is_active=True,is_superuser=True).exists())


def require_address_group_creation(user):
    require_catalog_capability(user, 'catalog_manage')
    active = User.objects.get(pk=user.pk, is_active=True)
    if not active.is_superuser and not active.groups.filter(name='Administrator').exists():
        raise PermissionDenied('Address group creation requires Administrator access.')
