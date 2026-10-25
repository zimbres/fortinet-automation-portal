import uuid
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied, ImproperlyConfigured
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Prefetch
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from apps.accounts.permissions import visible_vdoms, require_capability, require_superadmin, can_self_approve
from apps.accounts.models import User, GroupGrant
from apps.accounts.forms import UserProvisionForm
from apps.accounts.services import provision_user
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.firewalls.models import Firewall, VDOM
from apps.firewalls.forms import FirewallForm, FirewallEditForm, VDOMForm
from apps.firewalls.services import register_firewall
from apps.changes.models import ChangeRequest
from apps.changes.services import approve_change, reject_change, cancel_change
from apps.changes.reconciliation import reconcile_change
from apps.fortinet.client import FortinetClient
from apps.fortinet.exceptions import FortinetError
from apps.inventory.models import InventoryScan
from django.http import JsonResponse
from django.db import connection, DatabaseError


def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except DatabaseError:
        return JsonResponse({'status':'unavailable'},status=503)
    return JsonResponse({'status':'ok'})


def requests_for(user):
    return ChangeRequest.objects.filter(vdom__in=visible_vdoms(user)).select_related('requester','approver','vdom__firewall')


@login_required
def dashboard(request):
    items = requests_for(request.user)
    from apps.changes.installations import installations_for
    installations = installations_for(request.user)
    from apps.accounts.permissions import require_catalog_capability
    from apps.inventory.models import AddressObject, AddressGroup
    catalog_counts = None
    try:
        require_catalog_capability(request.user,'catalog_view')
        catalog_counts = {'objects':AddressObject.objects.count(),'groups':AddressGroup.objects.count()}
    except PermissionDenied:
        pass
    return render(request,'portal/dashboard.html',{'title':'Overview','items':items[:8],
        'catalog_counts':catalog_counts,
        'installations':installations.select_related('requester').prefetch_related('targets')[:8],
        'pending':items.filter(approval_status='PENDING').count()+installations.filter(approval_status='PENDING').count(),
        'completed':items.filter(execution_status='SUCCEEDED').count()+installations.filter(execution_status='SUCCEEDED').count(),
        'uncertain':items.filter(execution_status='RECONCILIATION_REQUIRED').count()+installations.filter(execution_status='RECONCILIATION_REQUIRED').count(),
        'firewall_count':visible_vdoms(request.user).values('firewall').distinct().count()})


@login_required
def history(request):
    query = request.GET.get('q','').strip()
    from apps.changes.installations import installations_for
    installations = installations_for(request.user).select_related('requester').prefetch_related('targets')
    if query:
        installations = installations.filter(Q(approval_status__icontains=query)|Q(execution_status__icontains=query)|Q(requester__username__icontains=query))
    paginator = Paginator(installations.order_by('-created_at', '-pk'), 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request,'portal/history.html',{
        'title':'Operation history', 'installations':page.object_list, 'query':query,
        'page_obj':page, 'page_numbers':paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1),
    })


@login_required
def approvals(request):
    items = ChangeRequest.objects.filter(vdom__in=visible_vdoms(request.user,'approve'),approval_status='PENDING').select_related('requester','vdom__firewall')
    from apps.changes.installations import installations_for
    installations = installations_for(request.user,'approve').filter(approval_status='PENDING')
    if not can_self_approve(request.user):
        items=items.exclude(requester=request.user)
        installations=installations.exclude(requester=request.user)
    return render(request,'portal/history.html',{'title':'Approvals','items':items[:100],'installations':installations.select_related('requester').prefetch_related('targets')[:100],'approval_queue':True})


@login_required
def request_detail(request,pk):
    item = get_object_or_404(requests_for(request.user),pk=pk)
    can_approve = (item.requester_id != request.user.pk or can_self_approve(request.user)) and visible_vdoms(request.user,'approve').filter(pk=item.vdom_id).exists()
    can_reconcile = item.execution_status == 'RECONCILIATION_REQUIRED' and visible_vdoms(request.user,'administer').filter(pk=item.vdom_id).exists()
    return render(request,'portal/request_detail.html',{'title':'Request details','item':item,'can_approve':can_approve,'can_reconcile':can_reconcile})


@login_required
@require_POST
def decision(request,pk,action):
    item = get_object_or_404(requests_for(request.user),pk=pk)
    actions = {'approve':approve_change,'reject':reject_change,'cancel':cancel_change,'reconcile':reconcile_change}
    if action not in actions:
        raise PermissionDenied
    try:
        actions[action](actor=request.user,request_id=item.pk)
        messages.success(request,'Request updated.')
    except (ValidationError,FortinetError) as exc:
        messages.error(request,' '.join(exc.messages) if isinstance(exc,ValidationError) else str(exc))
    return redirect('request_detail',pk=pk)


@login_required
def firewalls(request):
    items = Firewall.objects.all() if request.user.is_superuser else Firewall.objects.filter(vdoms__in=visible_vdoms(request.user)).distinct()
    vdoms = VDOM.objects.filter(removed_at__isnull=True) if request.user.is_superuser else visible_vdoms(request.user)
    from apps.firewalls.models import FirewallGroupMember
    from apps.firewalls.groups import visible_firewall_groups
    memberships=FirewallGroupMember.objects.select_related('group')
    if not request.user.is_superuser: memberships=memberships.filter(group__in=visible_firewall_groups(request.user))
    return render(request,'portal/firewalls.html',{'title':'Firewalls','firewalls':items.prefetch_related(Prefetch('vdoms',queryset=vdoms),Prefetch('firewallgroupmember_set',queryset=memberships)),'keys_ready':bool(settings.PORTAL_ENCRYPTION_KEYS)})


@login_required
def firewall_edit(request,pk):
    require_superadmin(request.user)
    fw = get_object_or_404(Firewall,pk=pk)
    form = FirewallEditForm(request.POST or None,instance=fw)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                updated = form.save(commit=False)
                if form.cleaned_data['token']: updated.set_token(form.cleaned_data['token'])
                updated.save()
                from apps.firewalls.groups import set_firewall_groups
                set_firewall_groups(firewall=updated,group_ids=[x.pk for x in form.cleaned_data['firewall_groups']])
                record_event(actor=request.user,event_type='firewall.updated',metadata={'firewall_id':fw.pk})
            messages.success(request,'Firewall configuration updated.')
            return redirect('firewalls')
        except ValidationError as exc:
            form.add_error(None,exc)
        except (ValueError,ImproperlyConfigured):
            form.add_error(None,'Credential encryption failed. Check the external key configuration.')
    return render(request,'portal/form.html',{'title':f'Edit {fw.name}','form':form,'submit_label':'Save firewall','description':'Changing connection or scope configuration does not execute pending requests.'})


@login_required
def firewall_new(request):
    require_superadmin(request.user)
    form = FirewallForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data.copy()
        try:
            register_firewall(actor=request.user,**data)
            messages.success(request,'Firewall registered. No remote changes were made.')
            return redirect('firewalls')
        except (ImproperlyConfigured,ValidationError) as exc:
            form.add_error(None,str(exc) if isinstance(exc,ImproperlyConfigured) else exc)
    return render(request,'portal/form.html',{'title':'Register firewall','form':form,'submit_label':'Register firewall','description':'Credentials are encrypted with the externally configured key ring.'})


@login_required
def vdom_new(request,pk):
    require_superadmin(request.user)
    fw = get_object_or_404(Firewall,pk=pk)
    form = VDOMForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            vdom,created = VDOM.objects.get_or_create(firewall=fw,name=form.cleaned_data['name'])
            if created:
                record_event(actor=request.user,event_type='vdom.created',metadata={'vdom_id':vdom.pk})
            elif vdom.removed_at is not None:
                vdom.removed_at, vdom.enabled = None, True
                vdom.save(update_fields=['removed_at','enabled'])
                record_event(actor=request.user,event_type='vdom.restored',metadata={'vdom_id':vdom.pk})
        return redirect('firewalls')
    return render(request,'portal/form.html',{'title':f'Add VDOM to {fw.name}','form':form,'submit_label':'Add VDOM'})


@login_required
@require_POST
def connection_check(request,pk):
    if request.user.is_superuser:
        require_superadmin(request.user)
        vdom = VDOM.objects.select_related('firewall').filter(pk=pk,enabled=True,removed_at__isnull=True,firewall__enabled=True).first()
        if vdom is None:
            messages.error(request,'This VDOM is unavailable or disabled. Refresh the firewall configuration before checking its connection.')
            return redirect('firewalls')
    else:
        vdom = get_object_or_404(visible_vdoms(request.user,'administer'),pk=pk)
    try:
        with FortinetClient(vdom.firewall,vdom) as client:
            result = client.request('GET','/api/v2/cmdb/firewall/address',extra={'count':1})
        if not result:
            raise FortinetError('Inventory endpoint is unavailable.')
        version = result.get('version','')
        if isinstance(version,str):
            Firewall.objects.filter(pk=vdom.firewall_id).update(observed_version=version[:50])
        messages.success(request,'Connection verified. Write compatibility still requires separate validation.')
        record_event(actor=request.user,event_type='firewall.connection_verified',metadata={'firewall_id':vdom.firewall_id})
    except (FortinetError,ValueError,ImproperlyConfigured):
        messages.error(request,'Connection could not be verified. Check credentials, TLS certificates, and connectivity.')
        record_event(actor=request.user,event_type='firewall.connection_failed',metadata={'firewall_id':vdom.firewall_id})
    return redirect('firewalls')


@login_required
def inventory(request,kind='addresses'):
    scopes = visible_vdoms(request.user)
    selected = scopes.filter(pk=request.GET.get('vdom')).first() if request.GET.get('vdom','').isdigit() else None
    records, error = [], ''
    if selected:
        try:
            with FortinetClient(selected.firewall,selected) as client:
                records = client.list_groups() if kind == 'groups' else client.list_addresses()
        except (FortinetError,ValueError,ImproperlyConfigured):
            error = 'Inventory could not be loaded. Check firewall connectivity and credentials.'
    return render(request,'portal/inventory.html',{'title':'Address groups' if kind == 'groups' else 'Address objects','kind':kind,'scopes':scopes,'selected':selected,'records':records,'error':error})


@login_required
def unused(request):
    from apps.accounts.permissions import require_catalog_capability
    from apps.firewalls.groups import visible_firewall_groups
    from apps.inventory.forms import GroupUsageForm
    from apps.inventory import services
    from django.urls import reverse
    require_catalog_capability(request.user,'catalog_view')
    selected=None
    if request.method == 'GET' and not request.GET.get('firewall_group'):
        selected=visible_firewall_groups(request.user).order_by('name').first()
    data=request.POST if request.method=='POST' else request.GET if request.GET.get('firewall_group') else None
    form=GroupUsageForm(data,user=request.user,initial={'firewall_group':selected.pk if selected else None})
    if form.is_bound and form.is_valid(): selected=form.cleaned_data['firewall_group']
    if request.method=='POST' and form.is_valid():
        if request.POST.get('action') == 'view':
            return redirect(reverse('unused')+f'?firewall_group={selected.pk}')
        try:
            scans=services.scan_group_usage(actor=request.user,firewall_group_id=selected.pk)
            complete=sum(scan.complete for scan in scans)
            messages.success(request,f'Scanned {len(scans)} destinations: {complete} complete, {len(scans)-complete} incomplete.')
            return redirect(reverse('unused')+f'?firewall_group={selected.pk}')
        except ValidationError as exc: form.add_error(None,exc)
    scans=services.latest_group_usage_scans(actor=request.user,firewall_group_id=selected.pk) if selected else []
    return render(request,'portal/unused.html',{'title':'Object and group usage','form':form,'selected_group':selected,'scans':scans})


@login_required
def users(request):
    require_superadmin(request.user)
    show_inactive = request.GET.get('inactive') == '1'
    accounts = User.objects.all() if show_inactive else User.objects.filter(is_active=True)
    return render(request,'portal/users.html',{'title':'Users & access','users':accounts.prefetch_related('groups','group_grants__firewall_group').order_by('username'),'show_inactive':show_inactive})


@login_required
def user_new(request):
    require_superadmin(request.user)
    form = UserProvisionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                d = form.cleaned_data
                user = provision_user(actor=request.user,username=d['username'],role_names=d['role_names'])
                user.email = d['email']
                user.require_password_change = d['require_password_change']
                if d['password']: user.set_password(d['password'])
                user.full_clean()
                user.save()
                if d.get('catalog_access'):
                    from apps.accounts.models import CatalogGrant
                    CatalogGrant.objects.create(user=user,capability=d['catalog_access'])
                for cap in ['view','submit','approve','administer']:
                    for group in d[f'{cap}_firewall_groups']:
                        GroupGrant.objects.create(user=user,firewall_group=group,capability=cap)
            return redirect('users')
        except ValidationError as exc:
            form.add_error(None,exc)
    return render(request,'portal/form.html',{'title':'Register user','form':form,'submit_label':'Register user','description':'Select View, Submit, Approve and Administer access separately for each firewall group. Role labels and group permissions are separate.'})


@login_required
def audit_log(request):
    require_superadmin(request.user)
    return render(request,'portal/audit.html',{'title':'Audit log','events':AuditEvent.objects.select_related('actor')[:200]})


@login_required
def vdom_delete(request,pk):
    from apps.firewalls.services import remove_vdom
    require_superadmin(request.user)
    vdom = get_object_or_404(VDOM.objects.select_related('firewall'),pk=pk,removed_at__isnull=True)
    error = ''
    memberships = vdom.firewallgroupmember_set.select_related('group')
    if request.method == 'POST':
        try:
            remove_vdom(actor=request.user,vdom_id=pk)
            messages.success(request,'VDOM removed from the active configuration. History is preserved. No firewall changes were made.')
            return redirect('firewalls')
        except ValidationError as exc:
            error = ' '.join(exc.messages)
    return render(request,'portal/vdom_delete.html',{'title':'Delete VDOM','vdom':vdom,'memberships':memberships,'error':error})
