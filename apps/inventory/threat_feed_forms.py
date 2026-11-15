from django import forms
from apps.portal.widgets import TransferSelectMultiple
from .models import ThreatFeed


class FeedAccountForm(forms.Form):
    username = forms.RegexField(regex=r'^[A-Za-z0-9_.@+-]+$', max_length=150, label='Feed username')
    password = forms.CharField(required=False, strip=False, max_length=4096, widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}),
                               help_text='Required for new accounts. Leave blank when editing to keep the current password.')
    is_active = forms.BooleanField(required=False, initial=True, label='Account enabled')
    feeds = forms.ModelMultipleChoiceField(queryset=ThreatFeed.objects.filter(approved_request__isnull=False).select_related('group__entry','scope__firewall_group'),
                                          required=False, widget=TransferSelectMultiple, label='Assigned scoped feeds',
                                          help_text='Each assignment covers one firewall group and address group. No assignments means no access.')
