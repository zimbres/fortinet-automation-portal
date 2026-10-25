from django.db import transaction
from apps.accounts.permissions import require_superadmin
from apps.accounts.models import GroupGrant
from apps.audit.services import record_event
from .models import Firewall, VDOM


@transaction.atomic
def register_firewall(*, actor, name, hostname, port, token, allowed_namespace, firewall_groups, protocol='https', vdom_name='root', enabled=True):
    require_superadmin(actor)
    fw = Firewall(name=name,hostname=hostname,port=port,allowed_namespace=allowed_namespace,
                  protocol=protocol,enabled=enabled)
    fw.full_clean(exclude=['encrypted_token'])
    fw.set_token(token)
    fw.save()
    vdom = VDOM.objects.create(firewall=fw,name=vdom_name)
    from .groups import set_firewall_groups
    set_firewall_groups(firewall=fw,group_ids=[x.pk for x in firewall_groups],vdom=vdom)
    record_event(actor=actor,event_type='firewall.created',metadata={'firewall_id':fw.pk})
    return fw


@transaction.atomic
def remove_vdom(*, actor, vdom_id):
    from django.core.exceptions import ValidationError
    from django.utils import timezone
    from .models import FirewallGroupMember
    require_superadmin(actor)
    vdom = VDOM.objects.select_for_update().get(pk=vdom_id)
    if vdom.removed_at is not None:
        raise ValidationError('This VDOM has already been removed.')
    if FirewallGroupMember.objects.filter(vdom=vdom).exists():
        raise ValidationError('This VDOM is a firewall group destination. Edit its firewall groups and select another VDOM before deleting it.')
    vdom.enabled = False
    vdom.removed_at = timezone.now()
    vdom.save(update_fields=['enabled','removed_at'])
    record_event(actor=actor,event_type='vdom.removed',metadata={'vdom_id':vdom.pk,'firewall_id':vdom.firewall_id})
    return vdom
