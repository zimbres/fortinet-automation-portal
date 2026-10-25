from django import forms
from apps.portal.widgets import TransferSelectMultiple
from .models import AddressObject, AddressGroup
from apps.accounts.permissions import can_manage_restrictions


class RestrictionOverrideForm(forms.Form):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and can_manage_restrictions(user):
            self.fields['override_restrictions'] = forms.BooleanField(
                required=False, label='Override restricted addresses',
                help_text='Allow matching addresses for this submission. Each override is audited.'
            )


class AddressForm(RestrictionOverrideForm):
    name = forms.CharField(max_length=79)
    kind = forms.ChoiceField(choices=AddressObject._meta.get_field('kind').choices)
    value = forms.CharField(max_length=253, help_text='IPv4 host/subnet, FQDN, or wildcard FQDN. Subnet host bits are normalized to the network address.')
    group = forms.ModelChoiceField(queryset=AddressGroup.objects.select_related('entry').order_by('entry__name'), required=False, label='Add to address group', empty_label='No group', help_text='Optional. Existing members are kept; these changes affect only the local catalog.')
    revision = forms.IntegerField(required=False, widget=forms.HiddenInput)


class AddressGroupForm(forms.Form):
    name = forms.CharField(max_length=79)
    description = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={'rows':3}), help_text='Optional. Describe the purpose of this local address group.')
    members = forms.ModelMultipleChoiceField(widget=TransferSelectMultiple,queryset=AddressObject.objects.select_related('entry').order_by('entry__name'), required=False)
    revision = forms.IntegerField(required=False, widget=forms.HiddenInput)


class ImportForm(RestrictionOverrideForm):
    group = forms.ModelChoiceField(queryset=AddressGroup.objects.select_related('entry').order_by('entry__name'), required=False, label='Add to address group', empty_label='No group', help_text='Optional. Existing members are kept; these changes affect only the local catalog.')
    prefix = forms.RegexField(regex=r'^[A-Za-z0-9_.-]*$',max_length=40,required=False,label='Object name prefix',help_text='Optional. Added to the exact address to form its name, for example trend_*.example.com. Include your preferred separator.')
    file = forms.FileField(required=False, label='Text or CSV file')
    content = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows':8}), label='Or paste a list', help_text='One IPv4 address/subnet, FQDN or *.wildcard FQDN per line. Types and names are detected automatically. CSV with header name,kind,value is also supported. Maximum 1,000 entries and 1 MiB.')

    def clean(self):
        data = super().clean()
        if bool(data.get('file')) == bool(data.get('content')):
            raise forms.ValidationError('Upload a file or paste a list, using one option.')
        if data.get('file') and data['file'].size > 1048576:
            raise forms.ValidationError('The file exceeds 1 MiB.')
        return data


class RestrictionForm(forms.Form):
    kind = forms.ChoiceField(choices=AddressObject._meta.get_field('kind').choices)
    value = forms.CharField(max_length=253, help_text='IPv4 host/subnet, FQDN, or *.wildcard FQDN. Subnets are normalized; overlapping submissions are refused.')


class RestrictionImportForm(ImportForm):
    group = None
    prefix = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['content'].help_text = 'One IPv4 host/subnet, FQDN or *.wildcard FQDN per line, or CSV with header name,kind,value. CSV names are ignored. Maximum 1,000 entries and 1 MiB. Valid rows are imported; invalid rows are reported.'


class GroupUsageForm(forms.Form):
    from apps.firewalls.models import FirewallGroup
    firewall_group=forms.ModelChoiceField(queryset=FirewallGroup.objects.none(),label='Firewall group',empty_label='Select a firewall group')

    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        from apps.firewalls.groups import visible_firewall_groups
        self.fields['firewall_group'].queryset=visible_firewall_groups(user).order_by('name')
