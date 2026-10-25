from django import forms
from apps.portal.widgets import TransferSelectMultiple
from .models import Firewall, FirewallGroup


class FirewallForm(forms.ModelForm):
    firewall_groups = forms.ModelMultipleChoiceField(widget=TransferSelectMultiple,queryset=FirewallGroup.objects.filter(enabled=True).order_by('name'),label='Firewall groups',help_text='Select at least one group. Create a group first if necessary.')
    token = forms.CharField(label='API Token', widget=forms.PasswordInput(render_value=False), help_text='Encrypted before storage. Never shown again.')
    port = forms.IntegerField(required=False,min_value=1,max_value=65535,help_text='Leave blank for the protocol default: HTTPS 443 or HTTP 80.')
    vdom_name = forms.CharField(max_length=79, initial='root', label='Initial VDOM')

    class Meta:
        model = Firewall
        fields = ['name','hostname','protocol','port','allowed_namespace','enabled']
        labels = {'hostname': 'Hostname / IP'}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['protocol'].help_text = 'HTTPS accepts self-signed certificates; certificate validation errors are ignored.'
        if self.instance.pk:
            self.initial['firewall_groups'] = self.instance.firewallgroupmember_set.values_list('group_id',flat=True)
        if not self.instance.pk:
            self.initial['port'] = None

    def clean(self):
        data = super().clean()
        if 'port' in data and data['port'] is None:
            data['port'] = 80 if data.get('protocol') == 'http' else 443
        return data


class VDOMForm(forms.Form):
    name = forms.CharField(max_length=79, label='VDOM name')


class FirewallEditForm(FirewallForm):
    token = forms.CharField(label='API Token',required=False,widget=forms.PasswordInput(render_value=False),help_text='Leave blank to keep the stored API token.')
    vdom_name = None
