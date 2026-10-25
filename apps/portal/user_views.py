from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from apps.accounts.models import User
from apps.accounts.forms import UserEditForm
from apps.accounts.services import ROLES, update_user, deactivate_user
from apps.accounts.permissions import require_superadmin


@login_required
def user_edit(request,pk):
    require_superadmin(request.user)
    account = get_object_or_404(User,pk=pk)
    roles = list(account.groups.filter(name__in=ROLES).values_list('name',flat=True))
    if account.is_superuser and 'Superadministrator' not in roles: roles.append('Superadministrator')
    catalog = set(account.catalog_grants.values_list('capability',flat=True))
    initial = {'username':account.email,'email':account.email,
               'is_active':account.is_active,'require_password_change':account.require_password_change,'role_names':roles,'catalog_access':'catalog_manage' if 'catalog_manage' in catalog else 'catalog_view' if 'catalog_view' in catalog else ''}
    for cap in ['view','submit','approve','administer']:
        initial[f'{cap}_firewall_groups'] = list(account.group_grants.filter(capability=cap).values_list('firewall_group_id',flat=True))
    form = UserEditForm(request.POST or None,initial=initial,user_id=account.pk,account=account)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data.copy()
        d['external_issuer'],d['external_subject'] = account.external_issuer,account.external_subject
        d['group_grants'] = {cap:[x.pk for x in d.pop(f'{cap}_firewall_groups')] for cap in ['view','submit','approve','administer']}
        try:
            updated = update_user(actor=request.user,user_id=pk,**d)
            if pk == request.user.pk and d.get('password'): update_session_auth_hash(request,updated)
            messages.success(request,'User updated. Explicit group grants were saved.')
            return redirect('users')
        except ValidationError as exc: form.add_error(None,exc)
    return render(request,'portal/form.html',{'title':f'Edit {account.username}','form':form,'submit_label':'Save user','description':'Role labels and explicit group grants are separate. Leave the password blank to preserve it. Superadministrators have catalog access and can request and approve for all enabled groups. Superadministrators may approve their own requests.'})


@login_required
def user_delete(request,pk):
    require_superadmin(request.user)
    account = get_object_or_404(User,pk=pk)
    error = ''
    if request.method == 'POST':
        try:
            deactivate_user(actor=request.user,user_id=pk)
            messages.success(request,'User deactivated and removed from the active list. History is preserved.')
            return redirect('users')
        except ValidationError as exc: error = ' '.join(exc.messages)
    return render(request,'portal/user_delete.html',{'title':'Delete user','account':account,'error':error})


@login_required
def profile(request):
    from django.contrib.auth.forms import PasswordChangeForm
    from django.core.exceptions import PermissionDenied
    from django.db import transaction
    from apps.accounts.forms import ProfileForm, AvatarForm
    from apps.audit.services import record_event

    account = request.user
    action = request.POST.get('action') if request.method == 'POST' else None
    oidc_managed = bool(account.external_subject or account.external_issuer)
    if request.method == 'POST' and oidc_managed and action not in ('avatar','avatar_remove'):
        raise PermissionDenied('Your personal information and password are managed by your identity provider.')
    avatar_form = AvatarForm(request.POST if action == 'avatar' else None, request.FILES if action == 'avatar' else None)
    profile_form = ProfileForm(request.POST if action == 'profile' else None, instance=account)
    password_form = PasswordChangeForm(account, request.POST if action == 'password' else None) if account.has_usable_password() and not oidc_managed else None
    if password_form is not None:
        password_form.fields['old_password'].label = 'Current password'
        password_form.fields['old_password'].widget.attrs.pop('autofocus', None)
    if request.method == 'POST':
        if action == 'avatar':
            if avatar_form.is_valid():
                from apps.accounts.avatars import set_avatar
                set_avatar(account, avatar_form.cleaned_data['avatar'])
                messages.success(request, 'Your profile picture has been updated.')
                return redirect('profile')
        elif action == 'avatar_remove':
            from apps.accounts.avatars import set_avatar
            set_avatar(account)
            messages.success(request, 'Your profile picture now uses Gravatar.')
            return redirect('profile')
        elif action == 'profile' and profile_form.is_valid():
            with transaction.atomic():
                updated = profile_form.save(commit=False)
                updated.save(update_fields=profile_form.Meta.fields)
                record_event(actor=account, event_type='account.profile_updated', metadata={'changed_fields':','.join(profile_form.changed_data)})
            messages.success(request, 'Your profile has been updated.')
            return redirect('profile')
        elif action == 'password':
            if password_form is None:
                raise PermissionDenied('Change your password through your identity provider.')
            if password_form.is_valid():
                with transaction.atomic():
                    updated = password_form.save(commit=False)
                    updated.save(update_fields=['password'])
                    record_event(actor=account, event_type='account.password_changed')
                update_session_auth_hash(request, updated)
                messages.success(request, 'Your password has been updated.')
                return redirect('profile')
        elif action != 'profile':
            raise PermissionDenied('Unknown profile action.')
    return render(request, 'portal/profile.html', {'title':'My profile', 'profile_form':profile_form, 'password_form':password_form,'oidc_managed':oidc_managed,'avatar_form':avatar_form})


@login_required
def profile_picture(request):
    from django.http import FileResponse, Http404
    if not request.user.avatar:
        raise Http404('No uploaded picture.')
    try:
        image = request.user.avatar.open('rb')
    except OSError:
        raise Http404('Picture not found.') from None
    response = FileResponse(image, content_type='image/png')
    response['Cache-Control'] = 'private, max-age=86400'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


class PortalLoginView(LoginView):
    def get_success_url(self):
        if self.request.user.password_change_needed:
            from django.urls import reverse
            return reverse('password_change_required')
        return super().get_success_url()


@login_required
def password_change_required(request):
    from django.db import transaction
    from apps.accounts.forms import RequiredPasswordChangeForm
    from apps.audit.services import record_event
    if not request.user.password_change_needed:
        return redirect('profile')
    form = RequiredPasswordChangeForm(request.user, request.POST if request.method == 'POST' else None)
    form.fields['old_password'].label = 'Current password'
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            account = form.save(commit=False)
            account.require_password_change = False
            account.save(update_fields=['password','require_password_change'])
            record_event(actor=account,event_type='account.password_changed',metadata={'reason_code':'required_change_completed'})
        update_session_auth_hash(request,account)
        messages.success(request,'Your password has been updated.')
        return redirect('dashboard')
    return render(request,'portal/password_change_required.html',{'title':'Change your password','form':form})
