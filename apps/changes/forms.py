from django import forms
from apps.portal.widgets import TransferSelectMultiple
from apps.accounts.permissions import visible_vdoms
from apps.firewalls.models import VDOM


class InstallationForm(forms.Form):
    from apps.inventory.models import AddressObject, AddressGroup
    from apps.firewalls.models import FirewallGroup
    objects = forms.ModelMultipleChoiceField(widget=TransferSelectMultiple,queryset=AddressObject.objects.none(), required=False)
    groups = forms.ModelMultipleChoiceField(widget=TransferSelectMultiple,queryset=AddressGroup.objects.none(), required=False, label='Address groups')
    firewall_group = forms.ModelChoiceField(queryset=FirewallGroup.objects.none(),label='Firewall group')
    idempotency_key = forms.CharField(widget=forms.HiddenInput,max_length=100)

    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        from apps.accounts.permissions import require_catalog_capability
        from apps.firewalls.groups import visible_firewall_groups
        from django.core.exceptions import PermissionDenied
        try:
            require_catalog_capability(user,'catalog_view')
            self.fields['objects'].queryset = self.AddressObject.objects.select_related('entry').order_by('entry__name')
            self.fields['groups'].queryset = self.AddressGroup.objects.select_related('entry').order_by('entry__name')
        except PermissionDenied: pass
        self.fields['firewall_group'].queryset = visible_firewall_groups(user,'submit')

    def intent(self):
        d = self.cleaned_data
        return {'object_ids':[x.pk for x in d['objects']], 'group_ids':[x.pk for x in d['groups']], 'target_kind':'firewall_group',
                'firewall_group_id':d['firewall_group'].pk if d.get('firewall_group') else None}
