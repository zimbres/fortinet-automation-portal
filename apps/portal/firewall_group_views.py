from django import forms
from django.db.models import Count
from apps.portal.widgets import TransferSelectMultiple
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from apps.accounts.permissions import require_superadmin
from apps.firewalls.models import FirewallGroup, VDOM
from apps.firewalls.groups import save_firewall_group, visible_firewall_groups


class FirewallGroupForm(forms.Form):
    name = forms.CharField(max_length=100)
    vdoms = forms.ModelMultipleChoiceField(widget=TransferSelectMultiple,queryset=VDOM.objects.filter(enabled=True,firewall__enabled=True).select_related('firewall'), required=False,label='Firewall / VDOM destinations', help_text='Select one VDOM per firewall. Empty groups can be populated when registering a firewall.')
    enabled = forms.BooleanField(required=False,initial=True)


@login_required
def firewall_groups(request):
    records = FirewallGroup.objects.all() if request.user.is_superuser else visible_firewall_groups(request.user)
    return render(request,'portal/firewall_groups.html',{'title':'Firewall groups','records':records.annotate(destination_count=Count('members',distinct=True))})


@login_required
def firewall_group_edit(request, pk=None):
    require_superadmin(request.user)
    group = get_object_or_404(FirewallGroup,pk=pk) if pk else None
    initial = {'name':group.name,'enabled':group.enabled,'vdoms':group.members.values_list('vdom_id',flat=True)} if group else {}
    form = FirewallGroupForm(request.POST or None,initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            d = form.cleaned_data
            save_firewall_group(actor=request.user,name=d['name'],vdom_ids=[x.pk for x in d['vdoms']],group_id=pk,enabled=d['enabled'])
            return redirect('firewall_groups')
        except ValidationError as exc: form.add_error(None,exc)
    return render(request,'portal/form.html',{'title':'Edit firewall group' if pk else 'Create firewall group','form':form,'submit_label':'Save group','description':'Membership changes apply to future requests. Submitted destinations remain fixed.'})
