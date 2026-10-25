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
def new_installation(request):
    form = InstallationForm(request.POST or None,user=request.user,initial={'idempotency_key':str(uuid.uuid4())})
    snapshot = None
    if request.method == 'POST' and form.is_valid():
        try:
            intent = form.intent()
            if request.POST.get('action') == 'submit':
                item = submit_installation(actor=request.user,**intent,idempotency_key=form.cleaned_data['idempotency_key'])
                messages.success(request,'Installation submitted for approval.')
                return redirect('installation_detail',pk=item.pk)
            snapshot = build_snapshot(actor=request.user,**intent)
        except ValidationError as exc: form.add_error(None,exc)
    return render(request,'portal/installation_form.html',{'title':'New installation request','form':form,'snapshot':snapshot})


@login_required
def installation_detail(request, pk):
    item = get_object_or_404(installations_for(request.user).select_related('requester','approver').prefetch_related('targets__steps'),pk=pk)
    return render(request,'portal/installation_detail.html',{'title':'Installation details','item':item,
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
