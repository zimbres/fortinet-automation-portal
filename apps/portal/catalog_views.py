from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.http import HttpResponse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from apps.accounts.permissions import require_catalog_capability, require_address_group_creation
from apps.inventory.models import CatalogEntry, AddressObject, AddressGroup, CatalogImport
from apps.inventory.catalog import save_address, save_address_group, delete_catalog_entry
from apps.inventory.imports import preview_import, confirm_import
from apps.inventory.forms import AddressForm, AddressGroupForm, ImportForm


@login_required
def catalog(request, kind='addresses'):
    require_catalog_capability(request.user, 'catalog_view')
    query = request.GET.get('q','').strip()
    records = AddressObject.objects.select_related('entry') if kind == 'addresses' else AddressGroup.objects.select_related('entry').annotate(member_count=Count('members'))
    matches = Q(entry__name__icontains=query)
    if kind == 'addresses':
        matches |= Q(value__icontains=query)
    else:
        matches |= Q(description__icontains=query)
    records = records.filter(matches).order_by('entry__name')
    can_create_group = False
    if kind == 'groups':
        try:
            require_address_group_creation(request.user)
            can_create_group = True
        except PermissionDenied:
            pass
    can_bulk_delete = False
    if kind == 'addresses':
        try:
            require_catalog_capability(request.user,'catalog_manage')
            can_bulk_delete = True
        except PermissionDenied:
            pass
    return render(request,'portal/catalog_list.html',{'title':'Address objects' if kind == 'addresses' else 'Address groups', 'kind':kind, 'records':records, 'query':query,'can_bulk_delete':can_bulk_delete,'can_create_group':can_create_group})


@login_required
def catalog_edit(request, kind='addresses', pk=None):
    require_catalog_capability(request.user, 'catalog_manage')
    is_address = kind == 'addresses'
    if not is_address and pk is None:
        require_address_group_creation(request.user)
    entry = get_object_or_404(CatalogEntry, pk=pk, entry_type='address' if is_address else 'group') if pk else None
    initial = {}
    if entry:
        initial = {'name':entry.name, 'revision':entry.revision}
        if is_address: initial.update(kind=entry.address.kind, value=entry.address.value)
        else: initial.update(members=entry.address_group.members.all(),description=entry.address_group.description)
    form_kwargs = {'initial':initial}
    if is_address:
        form_kwargs['user'] = request.user
    form = (AddressForm if is_address else AddressGroupForm)(request.POST or None, **form_kwargs)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        kwargs = {'actor':request.user, 'name':d['name'], 'entry_id':pk, 'expected_revision':d.get('revision')}
        try:
            if is_address: save_address(**kwargs, kind=d['kind'], value=d['value'], group_id=d['group'].pk if d.get('group') else None, override_restrictions=d.get('override_restrictions', False))
            else: save_address_group(**kwargs, member_ids=[x.pk for x in d['members']], description=d['description'])
            messages.success(request,'Saved in the local catalog. No installation was requested.')
            return redirect('objects' if is_address else 'groups')
        except ValidationError as exc: form.add_error(None,exc)
    return render(request,'portal/form.html',{'title':('Edit ' if pk else 'Create ')+('address object' if is_address else 'address group'), 'form':form, 'submit_label':'Save locally', 'description':'Catalog changes are local and audited. Install through a separate approved request.'})


@login_required
def catalog_delete(request, pk):
    require_catalog_capability(request.user,'catalog_manage')
    entry = get_object_or_404(CatalogEntry,pk=pk)
    error = ''
    if request.method == 'POST':
        try:
            delete_catalog_entry(actor=request.user,entry_id=pk,expected_revision=int(request.POST.get('revision','0')))
            return redirect('objects' if entry.entry_type == 'address' else 'groups')
        except (ValidationError, ValueError) as exc: error = ' '.join(exc.messages) if isinstance(exc,ValidationError) else 'Invalid revision. Reload the page.'
    return render(request,'portal/catalog_delete.html',{'title':'Delete local entry','entry':entry,'error':error})


@login_required
def import_objects(request):
    require_catalog_capability(request.user,'catalog_manage')
    form = ImportForm(request.POST or None,request.FILES or None,user=request.user)
    batch = None
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        content = data['file'].read(1048577) if data.get('file') else data['content'].encode('utf-8')
        try: batch = preview_import(actor=request.user,content=content,prefix=data.get('prefix',''),group_id=data['group'].pk if data.get('group') else None,override_restrictions=data.get('override_restrictions',False))
        except ValidationError as exc: form.add_error(None,exc)
    return render(request,'portal/catalog_import.html',{'title':'Import address objects','form':form,'batch':batch})


@login_required
@require_POST
def confirm_objects(request, token):
    require_catalog_capability(request.user,'catalog_manage')
    get_object_or_404(CatalogImport,pk=token,actor=request.user)
    try:
        created = confirm_import(actor=request.user,token=token)
        batch = CatalogImport.objects.get(pk=token)
        if batch.refused_rows:
            return render(request,'portal/catalog_import_result.html',{'title':'Address import results','created':created,'batch':batch})
        messages.success(request,f'{len(created)} objects stored locally. No firewall changes were made.')
        return redirect('objects')
    except ValidationError as exc:
        messages.error(request,' '.join(exc.messages))
        return redirect('import_objects')


@login_required
def import_example(request):
    require_catalog_capability(request.user,'catalog_view')
    response = HttpResponse('name,kind,value\nportal_host,subnet,192.0.2.1\nportal_web,fqdn,host.example.com\n',content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="address-objects.csv"'
    return response


@login_required
@require_POST
def delete_selected_objects(request):
    from django.core import signing
    from apps.inventory.catalog import validate_address_selection, bulk_delete_addresses
    require_catalog_capability(request.user,'catalog_manage')
    query = request.POST.get('q','').strip()
    try:
        token = request.POST.get('confirmation')
        if token:
            payload = signing.loads(token,salt='catalog-bulk-delete',max_age=900)
            if payload['actor'] != request.user.pk:
                raise PermissionDenied('This confirmation belongs to another user.')
            selections = {entry['id']:entry['revision'] for entry in payload['entries']}
            count = bulk_delete_addresses(actor=request.user,selections=selections)
            messages.success(request,f'{count} objects deleted from the local catalog.')
        else:
            selected = request.POST.getlist('selected')
            if len(selected) > 500:
                raise ValidationError('Select at most 500 objects.')
            selections = {}
            for value in selected:
                pk,revision = value.split(':')
                pk,revision = int(pk),int(revision)
                if pk in selections:
                    raise ValidationError('Invalid duplicate selection. Reload the list.')
                selections[pk] = revision
            entries = validate_address_selection(actor=request.user,selections=selections)
            payload = {'actor':request.user.pk,'entries':[{'id':e.pk,'revision':e.revision} for e in entries]}
            confirmation = signing.dumps(payload,salt='catalog-bulk-delete',compress=True)
            return render(request,'portal/catalog_bulk_delete.html',{'title':'Delete selected objects','entries':entries,'confirmation':confirmation,'query':query})
    except (ValidationError,signing.BadSignature,ValueError,TypeError,KeyError) as exc:
        messages.error(request,' '.join(exc.messages) if isinstance(exc,ValidationError) else 'The selection or confirmation is invalid or expired. Select the objects again.')
    from django.urls import reverse
    from urllib.parse import urlencode
    return redirect(reverse('objects') + ('?' + urlencode({'q':query}) if query else ''))
