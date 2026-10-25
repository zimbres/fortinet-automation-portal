from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from apps.portal.widgets import TransferSelectMultiple
from django.contrib.auth.password_validation import validate_password
from apps.firewalls.models import FirewallGroup
from .services import ROLES
from .models import User


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'autofocus': True, 'autocomplete': 'username'}))
    error_messages = {**AuthenticationForm.error_messages, 'invalid_login': 'Please enter a correct email and password.'}


class UserProvisionForm(forms.Form):
    username = forms.EmailField(label='Email', max_length=150)
    role_names = forms.MultipleChoiceField(choices=[(x,x) for x in ROLES], widget=forms.CheckboxSelectMultiple, label='Role labels')
    view_firewall_groups = forms.ModelMultipleChoiceField(widget=TransferSelectMultiple,queryset=FirewallGroup.objects.order_by('name'),required=False,label='View firewall groups')
    submit_firewall_groups = forms.ModelMultipleChoiceField(widget=TransferSelectMultiple,queryset=FirewallGroup.objects.order_by('name'),required=False,label='Submit to firewall groups')
    approve_firewall_groups = forms.ModelMultipleChoiceField(widget=TransferSelectMultiple,queryset=FirewallGroup.objects.order_by('name'),required=False,label='Approve for firewall groups')
    administer_firewall_groups = forms.ModelMultipleChoiceField(widget=TransferSelectMultiple,queryset=FirewallGroup.objects.order_by('name'),required=False,label='Administer firewall groups')
    password = forms.CharField(required=False,widget=forms.PasswordInput,help_text='Local login only. Leave blank for OIDC-only accounts.')
    require_password_change = forms.BooleanField(required=False,label='Require password change at next login',help_text='Local accounts only. The user must choose a new password before accessing the portal.')
    catalog_access = forms.ChoiceField(required=False,choices=[('', 'No catalog access'),('catalog_view','View local catalog'),('catalog_manage','Manage local catalog')])

    def __init__(self, *args, user_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = user_id

    def clean_username(self):
        email = self.cleaned_data['username'].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user_id).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean_password(self):
        value = self.cleaned_data.get('password','')
        if value:
            validate_password(value)
        return value

    def clean(self):
        data = super().clean()
        data['email'] = data.get('username', '')
        account = getattr(self, 'account', None)
        if data.get('require_password_change') and not data.get('password') and not (account and account.has_usable_password()):
            self.add_error('require_password_change', 'Set a local password before requiring a password change.')
        return data


class UserEditForm(UserProvisionForm):
    def __init__(self, *args, account=None, **kwargs):
        self.account = account
        super().__init__(*args, **kwargs)
        if account and (account.external_issuer or account.external_subject):
            self.initial.update(username=account.email,password='',require_password_change=False)
            for name in ('username','password','require_password_change'):
                self.fields[name].disabled = True
                self.fields[name].help_text = 'Managed by the identity provider. Read-only for OIDC accounts.'

    def clean(self):
        data = super().clean()
        if data.get('require_password_change') and self.account and (self.account.external_issuer or self.account.external_subject):
            self.add_error('require_password_change', 'OIDC password requirements are managed by the identity provider.')
        return data

    role_names = forms.MultipleChoiceField(required=False,choices=[(x,x) for x in ROLES],widget=forms.CheckboxSelectMultiple,label='Role labels')
    password = forms.CharField(required=False,widget=forms.PasswordInput,help_text='Leave blank to keep the current password.')
    is_active = forms.BooleanField(required=False,label='Active account')


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')

    email = forms.EmailField(required=True)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email


class AvatarForm(forms.Form):
    avatar = forms.FileField(label='Choose picture', help_text='PNG, JPEG or WebP. Maximum 2 MB.', widget=forms.FileInput(attrs={'accept':'image/png,image/jpeg,image/webp'}))

    def clean_avatar(self):
        from io import BytesIO
        import warnings
        from PIL import Image, ImageOps, UnidentifiedImageError
        from django.core.files.base import ContentFile
        from uuid import uuid4
        upload = self.cleaned_data['avatar']
        if upload.size > 2 * 1024 * 1024:
            raise forms.ValidationError('Choose a picture smaller than 2 MB.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(upload) as image:
                    if image.format not in ('PNG','JPEG','WEBP') or max(image.size) > 4096:
                        raise forms.ValidationError('Choose a PNG, JPEG or WebP picture no larger than 4096 pixels per side.')
                    image.verify()
                upload.seek(0)
                with Image.open(upload) as image:
                    avatar = ImageOps.fit(ImageOps.exif_transpose(image).convert('RGBA'), (256,256))
                    avatar.info.clear()
                    output = BytesIO()
                    avatar.save(output, format='PNG')
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise forms.ValidationError('Choose a valid PNG, JPEG or WebP picture.') from None
        return ContentFile(output.getvalue(), name=f'{uuid4().hex}.png')


class RequiredPasswordChangeForm(PasswordChangeForm):
    def clean_new_password1(self):
        password = self.cleaned_data['new_password1']
        if self.user.check_password(password):
            raise forms.ValidationError('Choose a password different from your current password.')
        return password
