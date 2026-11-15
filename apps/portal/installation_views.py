import uuid
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from apps.changes.forms import InstallationForm
from apps.accounts.permissions import can_self_approve
from apps.changes.installations import build_snapshot, submit_installation, decide_installation, installations_for
from apps.changes.installation_reconciliation import reconcile_installation
from apps.fortinet.exceptions import FortinetError


@login_required
def new_installation(request, feed_id=None):
    feed = None
    if feed_id is not None:
        from apps.inventory.models import ThreatFeed
        from apps.changes.feed_publications import require_feed_request_permission
        feed = get_object_or_404(ThreatFeed.objects.select_related('scope__firewall_group','group__entry'), pk=feed_id)
        require_feed_request_permission(request.user, feed.scope.firewall_group_id, 'submit')
    form = InstallationForm(request.POST if request.method == 'POST' else None,user=request.user,feed=feed,initial={
        'idempotency_key':str(uuid.uuid4()), 'target_kind':request.GET.get('target_kind','firewall_group')})
    snapshot = None
    change_notice = None
    if feed is not None and request.method == 'GET':
        try:
            snapshot = build_snapshot(actor=request.user, object_ids=[], group_ids=[feed.group_id],
                                      target_kind='threat_feeds', firewall_group_id=feed.scope.firewall_group_id)
        except ValidationError as exc:
            change_notice = ' '.join(exc.messages)
    if request.method == 'POST' and form.is_valid():
        try:
            intent = form.intent()
            if request.POST.get('action') == 'submit':
                item = submit_installation(actor=request.user,**intent,idempotency_key=form.cleaned_data['idempotency_key'])
                messages.success(request,'Request submitted for approval.')
                return redirect('installation_detail',pk=item.pk)
            snapshot = build_snapshot(actor=request.user,**intent)
        except ValidationError as exc: form.add_error(None,exc)
    from apps.changes.feed_publications import feed_snapshot_urls
    return render(request,'portal/installation_form.html',{'title':'Update Threat Feed' if feed else 'New request',
        'form':form,'snapshot':snapshot,'update_feed':feed,'change_notice':change_notice,
        'feed_previews':feed_snapshot_urls(snapshot) if snapshot and snapshot.get('target_kind') == 'threat_feeds' else None})


@login_required
def installation_detail(request, pk):
    item = get_object_or_404(installations_for(request.user).select_related('requester','approver').prefetch_related('targets__steps'),pk=pk)
    from apps.changes.feed_publications import feed_snapshot_urls
    return render(request,'portal/installation_detail.html',{'title':'Request details','item':item,
        'feed_previews':feed_snapshot_urls(item.snapshot) if item.snapshot.get('target_kind') == 'threat_feeds' else None,
        'auto_refresh':item.approval_status in ('PENDING','APPROVED') and item.execution_status in ('PENDING','RUNNING','RECONCILIATION_REQUIRED'),
        'can_approve':(item.requester_id != request.user.pk or can_self_approve(request.user)) and installations_for(request.user,'approve').filter(pk=pk).exists(),
        'can_reconcile':installations_for(request.user,'administer').filter(pk=pk).exists()})


@login_required
@require_POST
def installation_decision(request, pk, action):
    get_object_or_404(installations_for(request.user),pk=pk)
    try:
        if action == 'reconcile': reconcile_installation(actor=request.user,request_id=pk)
        elif action in ('approve','reject','cancel'):
            decide_installation(actor=request.user,request_id=pk,status={'approve':'APPROVED','reject':'REJECTED','cancel':'CANCELLED'}[action])
        else: raise PermissionDenied('Unknown action.')
    except (ValidationError,FortinetError) as exc:
        messages.error(request,' '.join(exc.messages) if isinstance(exc,ValidationError) else str(exc))
    return redirect('installation_detail',pk=pk)
