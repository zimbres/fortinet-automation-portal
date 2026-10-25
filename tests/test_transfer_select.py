import pytest
from apps.portal.widgets import TransferSelectMultiple
from tests.test_catalog import manager
from tests.test_installations import installation

pytestmark=pytest.mark.django_db


def test_multi_object_forms_use_transfer_widget(scope):
    from apps.changes.forms import InstallationForm
    from apps.inventory.forms import AddressGroupForm
    from apps.accounts.forms import UserProvisionForm,UserEditForm
    from apps.firewalls.forms import FirewallForm
    from apps.portal.firewall_group_views import FirewallGroupForm
    for form in [InstallationForm(user=scope[0]),AddressGroupForm(),UserProvisionForm(),UserEditForm(),FirewallForm(),FirewallGroupForm()]:
        for field in form.fields.values():
            from django.forms import ModelMultipleChoiceField
            if isinstance(field,ModelMultipleChoiceField):
                assert isinstance(field.widget,TransferSelectMultiple)


def test_transfer_widget_preserves_bound_values_and_escapes_labels():
    from django import forms
    class SelectionForm(forms.Form):
        items=forms.MultipleChoiceField(choices=[('a','<script>unsafe</script>'),('b','Other')],widget=TransferSelectMultiple)
    form=SelectionForm({'items':['a']})
    assert form.is_valid() and form.cleaned_data['items']==['a']
    html=str(form['items'])
    assert 'data-transfer-select' in html
    assert 'value="a" selected' in html
    assert '&lt;script&gt;unsafe&lt;/script&gt;' in html
    assert '<script>unsafe</script>' not in html
    assert 'data-transfer-action="add-all"' in html
    assert 'data-transfer-action="remove-all"' in html


def test_installation_preview_preserves_transferred_choices(client,installation,manager):
    item,obj,group=installation
    client.force_login(manager)
    page=client.post('/requests/new/',{'objects':[obj.pk],'groups':[group.pk],'firewall_group':item.snapshot['firewall_group_id'],'idempotency_key':'transfer-preview','action':'preview'})
    assert page.status_code==200
    assert page.context['form'].is_valid()
    assert page.context['snapshot']['objects'][0]['name']=='portal_host'
    assert b'data-transfer-select' in page.content
    assert b'transfer-select.js' in page.content

def test_transfer_fields_keep_required_validation_and_edit_initial(scope):
    from apps.firewalls.forms import FirewallEditForm
    from tests.group_helpers import group_for
    form=FirewallEditForm(instance=scope[2].firewall)
    assert list(form.initial['firewall_groups'])==[group_for(scope[2]).pk]
    bound=FirewallEditForm({'name':'Edge','hostname':'192.0.2.1','protocol':'https','port':443,'token':'','allowed_namespace':'portal_','enabled':'on','firewall_groups':[]},instance=scope[2].firewall)
    assert not bound.is_valid()
    assert 'firewall_groups' in bound.errors

def test_transfer_boxes_are_native_highlight_lists():
    from django import forms
    class SelectionForm(forms.Form):
        items=forms.MultipleChoiceField(choices=[('a','One')],widget=TransferSelectMultiple)
    html=str(SelectionForm()['items'])
    assert '<select class="transfer-select__list"' in html
    assert 'data-transfer-list="available" multiple' in html
    assert 'data-transfer-list="selected" multiple' in html
