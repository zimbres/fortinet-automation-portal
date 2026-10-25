from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction, IntegrityError
from apps.accounts.permissions import require_superadmin, require_capability, visible_vdoms, require_group_capability
from apps.audit.services import record_event
from .models import FirewallGroup, FirewallGroupMember, VDOM


def save_firewall_group(*, actor, name, vdom_ids, group_id=None, enabled=True):
    require_superadmin(actor)
    name = name.strip()
    if not name or len(name) > 100:
        raise ValidationError('Enter a firewall group name of up to 100 characters.')
    try:
        with transaction.atomic():
            scopes = list(VDOM.objects.select_for_update().filter(pk__in=set(vdom_ids)).select_related('firewall').order_by('pk'))
            if len(scopes) != len(set(vdom_ids)) or len({x.firewall_id for x in scopes}) != len(scopes):
                raise ValidationError('Select at most one VDOM per firewall.')
            if any(not x.enabled or x.removed_at is not None or not x.firewall.enabled for x in scopes):
                raise ValidationError('Select enabled firewall scopes only.')
            group = FirewallGroup.objects.get(pk=group_id) if group_id else FirewallGroup()
            is_new=not group.pk
            group.name, group.enabled = name, enabled
            group.save()
            old_ids = set(group.members.values_list('firewall_id',flat=True))
            retained = {x.firewall_id for x in scopes} if enabled else set()
            for fw_id in old_ids - retained:
                if not FirewallGroupMember.objects.filter(firewall_id=fw_id,group__enabled=True).exclude(group=group).exists():
                    raise ValidationError('Every firewall must remain in at least one enabled group.')
            group.members.exclude(vdom_id__in=[x.pk for x in scopes]).delete()
            for scope in scopes:
                FirewallGroupMember.objects.update_or_create(group=group,firewall=scope.firewall,defaults={'vdom':scope})
            if is_new:
                from apps.accounts.models import GroupGrant
                for cap in ('view','submit','approve','administer'):
                    GroupGrant.objects.create(user=actor,firewall_group=group,capability=cap)
            record_event(actor=actor, event_type='firewall_group.updated', metadata={'group_id': group.pk})
            return group
    except IntegrityError:
        raise ValidationError('A firewall group already uses this name.') from None


def visible_firewall_groups(user, capability='view'):
    from apps.accounts.models import User
    from apps.accounts.permissions import SUPERADMIN_CAPABILITIES, CAPABILITIES
    active=User.objects.filter(pk=user.pk,is_active=True).first() if user.pk else None
    if not active or capability not in CAPABILITIES:
        return FirewallGroup.objects.none()
    groups=FirewallGroup.objects.filter(enabled=True)
    if active.is_superuser and capability in SUPERADMIN_CAPABILITIES:
        return groups
    if active.is_superuser:
        return groups.filter(grants__user=user,grants__capability=capability).distinct()
    return groups.filter(grants__user=user,grants__capability=capability).filter(
        grants__user=user,grants__capability='view').distinct()


def resolve_destinations(*, actor, target_kind, vdom_id=None, firewall_group_id=None):
    if target_kind != 'firewall_group' or not firewall_group_id or vdom_id:
        raise ValidationError('Select a firewall group as the request destination.')
    group = FirewallGroup.objects.filter(pk=firewall_group_id, enabled=True).first()
    if not group:
        raise ValidationError('Select an enabled firewall group.')
    require_group_capability(actor,group.pk,'view')
    require_group_capability(actor,group.pk,'submit')
    scopes = [x.vdom for x in group.members.select_related('vdom__firewall').order_by('vdom_id')]
    if not scopes:
        raise ValidationError('The target group has no destinations.')
    for vdom in scopes:
        require_capability(actor,vdom,'view')
        require_capability(actor,vdom,'submit')
    return scopes


@transaction.atomic
def set_firewall_groups(*, firewall, group_ids, vdom=None):
    ids=set(group_ids)
    groups=list(FirewallGroup.objects.filter(pk__in=ids,enabled=True))
    if not groups or len(groups)!=len(ids):
        raise ValidationError('Select at least one enabled firewall group.')
    candidates=VDOM.objects.select_for_update().filter(firewall=firewall,enabled=True,removed_at__isnull=True)
    if vdom is not None: candidates=candidates.filter(pk=vdom.pk)
    default_vdom=candidates.order_by('pk').first()
    if not default_vdom:
        raise ValidationError('An enabled VDOM is required for group membership.')
    for group in groups:
        FirewallGroupMember.objects.get_or_create(group=group,firewall=firewall,defaults={'vdom':default_vdom})
    FirewallGroupMember.objects.filter(firewall=firewall).exclude(group_id__in=ids).delete()
