from django import forms
from apps.portal.widgets import TransferSelectMultiple
from apps.accounts.permissions import visible_vdoms
from apps.firewalls.models import VDOM


class InstallationForm(forms.Form):
    from apps.inventory.models import AddressObject, AddressGroup
    from apps.firewalls.models import FirewallGroup
    target_kind = forms.ChoiceField(label='Target', choices=[('firewall_group','Firewall installation'), ('threat_feeds','Threat Feeds')],
                                   required=False, initial='firewall_group',
                                   help_text='Threat Feeds publishes approved address-group snapshots; select address groups only.')
    objects = forms.ModelMultipleChoiceField(widget=TransferSelectMultiple,queryset=AddressObject.objects.none(), required=False)
    groups = forms.ModelMultipleChoiceField(widget=TransferSelectMultiple,queryset=AddressGroup.objects.none(), required=False, label='Address groups')
    firewall_group = forms.ModelChoiceField(queryset=FirewallGroup.objects.none(),label='Firewall group')
    idempotency_key = forms.CharField(widget=forms.HiddenInput,max_length=100)

    def __init__(self,*args,user,feed=None,**kwargs):
        initial = kwargs.setdefault('initial', {})
        if feed is not None:
            initial.update(target_kind='threat_feeds', firewall_group=feed.scope.firewall_group_id, groups=[feed.group_id])
        super().__init__(*args,**kwargs)
        self.feed = feed
        from apps.accounts.permissions import require_catalog_capability
        from apps.firewalls.groups import visible_firewall_groups
        from django.core.exceptions import PermissionDenied
        try:
            require_catalog_capability(user,'catalog_view')
            self.fields['objects'].queryset = self.AddressObject.objects.select_related('entry').order_by('entry__name')
            self.fields['groups'].queryset = self.AddressGroup.objects.select_related('entry').order_by('entry__name')
        except PermissionDenied: pass
        self.fields['firewall_group'].queryset = visible_firewall_groups(user,'submit')
        from apps.accounts.permissions import can_manage_restrictions
        if not can_manage_restrictions(user):
            self.fields['target_kind'].choices = [('firewall_group','Firewall installation')]
        self.is_feed_target = feed is not None or (self.data.get('target_kind') if self.is_bound else initial.get('target_kind')) == 'threat_feeds'
        if self.is_feed_target:
            self.fields['objects'].disabled = True
        if feed is not None:
            for name in ('target_kind', 'firewall_group', 'groups'):
                self.fields[name].disabled = True
                self.fields[name].widget = forms.MultipleHiddenInput() if name == 'groups' else forms.HiddenInput()
            self.fields['expected_revision'] = forms.IntegerField(min_value=0, widget=forms.HiddenInput(), initial=feed.revision)

    def clean(self):
        data = super().clean()
        if data.get('target_kind') == 'threat_feeds' and self.fields['objects'].widget.value_from_datadict(self.data, self.files, 'objects'):
            self.add_error(None, 'Standalone objects cannot be used for Threat Feeds. Select address groups only.')
        if self.feed is not None and data.get('expected_revision') != self.feed.revision:
            self.add_error(None, 'This publication changed. Reload the update screen before submitting.')
        return data

    def intent(self):
        d = self.cleaned_data
        return {'object_ids':[x.pk for x in d['objects']], 'group_ids':[x.pk for x in d['groups']], 'target_kind':d.get('target_kind') or 'firewall_group',
                'firewall_group_id':d['firewall_group'].pk if d.get('firewall_group') else None}
