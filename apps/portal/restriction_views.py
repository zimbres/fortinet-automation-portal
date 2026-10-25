from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from apps.accounts.permissions import require_restriction_management
from apps.inventory.forms import RestrictionForm, RestrictionImportForm
from apps.inventory.models import AddressRestriction
from apps.inventory.restrictions import save_restriction, delete_restriction
from apps.inventory.restriction_imports import import_restrictions


@login_required
def restrictions(request):
    require_restriction_management(request.user)
    query = request.GET.get('q', '').strip()
    records = AddressRestriction.objects.filter(value__icontains=query).select_related('updated_by')
    return render(request, 'portal/restrictions.html', {
        'title':'Restricted addresses', 'records':records, 'query':query,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def restriction_edit(request, pk=None):
    require_restriction_management(request.user)
    rule = get_object_or_404(AddressRestriction, pk=pk) if pk else None
    initial = {'kind':rule.kind, 'value':rule.value} if rule else {}
    form = RestrictionForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            save_restriction(actor=request.user, restriction_id=pk, **form.cleaned_data)
            messages.success(request, 'Restricted address saved.')
            return redirect('restrictions')
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'portal/form.html', {
        'title':('Edit' if pk else 'Add') + ' restricted address', 'form':form,
        'submit_label':'Save restriction', 'cancel_url':reverse('restrictions'),
        'description':'Matching operator submissions will be refused. Existing objects and installations are unchanged.',
    })


@login_required
@require_http_methods(['GET', 'POST'])
def restriction_delete(request, pk):
    require_restriction_management(request.user)
    rule = get_object_or_404(AddressRestriction, pk=pk)
    if request.method == 'POST':
        delete_restriction(actor=request.user, restriction_id=rule.pk)
        messages.success(request, 'Restricted address deleted.')
        return redirect('restrictions')
    return render(request, 'portal/restriction_delete.html', {'title':'Delete restriction', 'rule':rule})


@login_required
@require_http_methods(['GET', 'POST'])
def restriction_import(request):
    require_restriction_management(request.user)
    form = RestrictionImportForm(request.POST or None, request.FILES or None)
    result = None
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        content = data['file'].read(1048577) if data.get('file') else data['content'].encode('utf-8')
        try:
            result = import_restrictions(actor=request.user, content=content)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'portal/restriction_import.html', {
        'title':'Import restricted addresses', 'form':form, 'result':result,
    })
