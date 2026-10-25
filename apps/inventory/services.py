from apps.accounts.permissions import require_capability, require_catalog_capability, visible_vdoms, require_group_capability
from apps.audit.services import record_event
from apps.fortinet.client import FortinetClient
from apps.fortinet.exceptions import FortinetError
from django.db import transaction
from django.utils import timezone
from .usage import classify_usage
from .models import InventoryScan, AddressObject, AddressGroup
from django.core.exceptions import ValidationError, ImproperlyConfigured


def scan_usage(*, actor, vdom):
    require_capability(actor,vdom,'view')
    require_catalog_capability(actor,'catalog_view')
    try:
        with FortinetClient(vdom.firewall,vdom) as client:
            addresses, groups, policies = client.list_addresses(), client.list_groups(), client.list_policies()
        assessments = classify_usage(addresses,groups,policies,complete=True,include_groups=True)
        local_names = set(AddressObject.objects.values_list('entry__name',flat=True)) & {row['name'] for row in addresses}
        findings = {name:state for name,state in assessments.items() if name in local_names}
        local_groups = set(AddressGroup.objects.values_list('entry__name',flat=True)) & {row['name'] for row in groups}
        group_findings = {name:state for name,state in assessments.items() if name in local_groups}
        complete = True
    except (FortinetError,ValueError,ImproperlyConfigured,KeyError,TypeError,AttributeError):
        findings, group_findings, complete = {}, {}, False
    with transaction.atomic():
        scan, _ = InventoryScan.objects.update_or_create(vdom=vdom,defaults={'findings':findings,'group_findings':group_findings,'complete':complete,'created_at':timezone.now()})
        record_event(actor=actor,event_type='inventory.scanned',metadata={'vdom_id':vdom.pk,'status':'complete' if complete else 'incomplete'})
    return scan


def latest_usage_scans(*, actor, scopes):
    from django.db.models import OuterRef, Subquery
    require_catalog_capability(actor,'catalog_view')
    latest = InventoryScan.objects.filter(vdom_id=OuterRef('vdom_id')).order_by('-created_at','-pk').values('pk')[:1]
    scans = list(InventoryScan.objects.filter(vdom__in=scopes,vdom_id__in=visible_vdoms(actor),pk=Subquery(latest)).select_related('vdom__firewall').order_by('vdom__firewall__name','vdom__name'))
    local_names = set(AddressObject.objects.values_list('entry__name',flat=True))
    local_groups = set(AddressGroup.objects.values_list('entry__name',flat=True))
    for scan in scans:
        # Also filter historical scans and entries removed from the local catalog.
        scan.findings = {name:state for name,state in scan.findings.items() if name in local_names}
        if scan.group_findings is not None:
            scan.group_findings = {name:state for name,state in scan.group_findings.items() if name in local_groups}
    return scans


def _group_scopes(*, actor, firewall_group_id):
    from apps.firewalls.models import FirewallGroup
    require_catalog_capability(actor,'catalog_view')
    require_group_capability(actor,firewall_group_id,'view')
    group=FirewallGroup.objects.filter(pk=firewall_group_id,enabled=True).first()
    if not group: raise ValidationError('The firewall group is unavailable.')
    scopes=[member.vdom for member in group.members.select_related('vdom__firewall').order_by('vdom_id')]
    return group,scopes


def scan_group_usage(*, actor, firewall_group_id):
    from apps.firewalls.models import FirewallGroupMember
    group,scopes=_group_scopes(actor=actor,firewall_group_id=firewall_group_id)
    if not scopes: raise ValidationError('This firewall group has no destinations.')
    if any(not vd.enabled or not vd.firewall.enabled for vd in scopes):
        raise ValidationError('This group contains disabled destinations. Enable them or update its membership before scanning.')
    scans=[]
    for vdom in scopes:
        require_group_capability(actor,group.pk,'view')
        if not FirewallGroupMember.objects.filter(group=group,vdom=vdom,firewall_id=vdom.firewall_id).exists():
            raise ValidationError('Group membership changed. Run the scan again.')
        scans.append(scan_usage(actor=actor,vdom=vdom))
    record_event(actor=actor,event_type='inventory.group_scanned',metadata={'group_id':group.pk,'count':len(scans),'status':'complete' if all(scan.complete for scan in scans) else 'incomplete'})
    return scans


def latest_group_usage_scans(*, actor, firewall_group_id):
    group,scopes=_group_scopes(actor=actor,firewall_group_id=firewall_group_id)
    return latest_usage_scans(actor=actor,scopes=scopes)
