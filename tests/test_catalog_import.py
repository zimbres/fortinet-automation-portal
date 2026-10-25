from datetime import timedelta
import pytest
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from tests.test_catalog import manager

pytestmark = pytest.mark.django_db


def test_valid_batch_creates_all_once(manager):
    from apps.inventory.imports import preview_import, confirm_import
    from apps.inventory.models import AddressObject
    preview = preview_import(actor=manager, content=b'name,kind,value\na,subnet,192.0.2.1\nb,fqdn,host.example.com\n')
    assert preview.errors == []
    assert AddressObject.objects.count() == 0
    result = confirm_import(actor=manager, token=preview.pk)
    assert len(result) == 2
    assert [x.pk for x in confirm_import(actor=manager, token=preview.pk)] == [x.pk for x in result]
    assert AddressObject.objects.count() == 2


@pytest.mark.parametrize('content', [b'name,kind,value\na,subnet,bad\n', b'name,kind,value\na,subnet,192.0.2.1\na,subnet,192.0.2.2\n'])
def test_invalid_batch_creates_zero(manager, content):
    from apps.inventory.imports import preview_import, confirm_import
    from apps.inventory.models import AddressObject
    preview = preview_import(actor=manager, content=content)
    assert preview.errors
    with pytest.raises(ValidationError): confirm_import(actor=manager, token=preview.pk)
    assert AddressObject.objects.count() == 0


def test_limit_1000_rows_and_1_mib(manager):
    from apps.inventory.imports import preview_import
    rows = b'name,kind,value\n' + b''.join(f'a{i},subnet,192.0.2.1\n'.encode() for i in range(1000))
    assert not preview_import(actor=manager, content=rows).errors
    assert preview_import(actor=manager, content=rows+b'extra,subnet,192.0.2.1\n').errors
    prefix = b'name,kind,value\na,fqdn,'
    exact = prefix + b'x' * (1048576-len(prefix))
    assert len(exact) == 1048576
    assert preview_import(actor=manager, content=exact).errors
    with pytest.raises(ValidationError): preview_import(actor=manager, content=exact+b'x')


def test_preview_expiry_actor_binding_and_tampering(manager, scope):
    from apps.inventory.imports import preview_import, confirm_import
    from apps.inventory.models import CatalogImport
    preview = preview_import(actor=manager, content=b'name,kind,value\na,subnet,192.0.2.1\n')
    with pytest.raises(PermissionDenied): confirm_import(actor=scope[1], token=preview.pk)
    CatalogImport.objects.filter(pk=preview.pk).update(rows=[{'name':'other','kind':'subnet','value':'192.0.2.2'}])
    with pytest.raises(ValidationError): confirm_import(actor=manager, token=preview.pk)
    CatalogImport.objects.filter(pk=preview.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
    with pytest.raises(ValidationError): confirm_import(actor=manager, token=preview.pk)


def test_confirm_revalidates_collision_and_revoked_grant(manager):
    from apps.inventory.imports import preview_import, confirm_import
    from apps.inventory.catalog import save_address
    from apps.accounts.models import CatalogGrant
    preview = preview_import(actor=manager, content=b'name,kind,value\na,subnet,192.0.2.1\nb,subnet,192.0.2.2\n')
    save_address(actor=manager, name='b', kind='subnet', value='192.0.2.3')
    with pytest.raises(ValidationError): confirm_import(actor=manager, token=preview.pk)
    from apps.inventory.models import AddressObject
    assert AddressObject.objects.count() == 1
    CatalogGrant.objects.filter(user=manager).delete()
    with pytest.raises(PermissionDenied): confirm_import(actor=manager, token=preview.pk)


@pytest.mark.parametrize('content,valid', [(b'\xef\xbb\xbfname,kind,value\na,subnet,192.0.2.1\n',True), (b'name,kind,value\n"a\nb",subnet,192.0.2.1\n',False), (b'name,kind,value\n\xff,subnet,192.0.2.1\n',False), (b'name,kind,value\na,subnet,192.0.2.1,extra\n',False)])
def test_bom_quoted_newlines_bad_utf8_and_extra_cells(manager, content, valid):
    from apps.inventory.imports import preview_import
    assert bool(preview_import(actor=manager, content=content).errors) is not valid


def test_raw_list_detection_prefix_and_confirmation(manager):
    from apps.inventory.imports import preview_import,confirm_import
    lines='xdr.trendmicro.com\nxlogr-ec1.xdr.trendmicro.com\n*.fbs25.trendmicro.com\n*.gfrbridge.trendmicro.com\n*.url.trendmicro.com\n3.26.127.96/27\n3.99.65.64/27\n192.0.2.1\n'
    batch=preview_import(actor=manager,content=lines.encode(),prefix='trend_')
    assert batch.errors==[]
    assert [row['kind'] for row in batch.rows]==['fqdn','fqdn','wildcard_fqdn','wildcard_fqdn','wildcard_fqdn','subnet','subnet','subnet']
    assert batch.rows[0]['name']=='trend_xdr.trendmicro.com'
    assert batch.rows[2]['name']=='trend_*.fbs25.trendmicro.com'
    assert batch.rows[5]['name']=='trend_3.26.127.96/27'
    assert batch.rows[-1]=={'name':'trend_192.0.2.1','kind':'subnet','value':'192.0.2.1/32'}
    assert len(confirm_import(actor=manager,token=batch.pk))==8


@pytest.mark.parametrize('line',['999.1.1.1','192.0.2.1.','https://host.example.com','host.example.com:443','bad*example.com','2001:db8::1'])
def test_raw_list_rejects_invalid_values_atomically(manager,line):
    from apps.inventory.imports import preview_import,confirm_import
    batch=preview_import(actor=manager,content=('valid.example.com\n'+line).encode())
    assert batch.errors and 'Line 2:' in batch.errors[0]
    with pytest.raises(ValidationError): confirm_import(actor=manager,token=batch.pk)


def test_raw_names_preserve_input_and_reject_overlength(manager):
    from apps.inventory.imports import preview_import,confirm_import
    lines=['HOST.EXAMPLE.COM.','*.example.com','192.0.2.1/32','192.0.2.0/24']
    for prefix in ('','p_'):
        batch=preview_import(actor=manager,content=('\n'.join(lines)).encode(),prefix=prefix)
        assert not batch.errors
        assert [row['name'] for row in batch.rows]==[prefix+line for line in lines]
        assert batch.rows[0]['value']=='host.example.com'
    long_domain='a'*60+'.example.com'
    rejected=preview_import(actor=manager,content=long_domain.encode(),prefix='p_'*20)
    assert rejected.errors and not rejected.rows
    with pytest.raises(ValidationError): confirm_import(actor=manager,token=rejected.pk)
    duplicate=preview_import(actor=manager,content=b'*.example.com\n*.example.com')
    assert duplicate.errors and 'Line 2:' in duplicate.errors[0]


def test_raw_limits_csv_prefix_and_invalid_prefix(manager):
    from apps.inventory.imports import preview_import
    assert not preview_import(actor=manager,content=b'\n'.join(f'host{i}.example.com'.encode() for i in range(1000))).errors
    assert preview_import(actor=manager,content=b'\n'.join(f'host{i}.example.com'.encode() for i in range(1001))).errors
    csv=preview_import(actor=manager,content=b'name,kind,value\nweb,fqdn,host.example.com\n',prefix='p_')
    assert csv.rows[0]['name']=='p_web' and not csv.errors
    with pytest.raises(ValidationError): preview_import(actor=manager,content=b'host.example.com',prefix='bad/')


def test_raw_import_view_and_text_upload(client,manager):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from apps.inventory.models import CatalogImport
    client.force_login(manager)
    for data in ({'content':'*.example.com\n192.0.2.0/24','prefix':'list_'},
                 {'file':SimpleUploadedFile('objects.txt',b'\xef\xbb\xbfhost.example.com\n'),'prefix':'file_'}):
        page=client.post('/objects/import/',data)
        assert page.status_code==200
        batch=page.context['batch']; assert batch is not None and not batch.errors
        assert batch.rows[0]['name'].startswith(data['prefix'])
        assert b'Object name prefix' in page.content


@pytest.mark.parametrize('header,valid', [('"name","kind","value"',True),('name,kind,value ',False)])
def test_csv_header_detection_uses_csv_fields(manager,header,valid):
    from apps.inventory.imports import preview_import
    batch=preview_import(actor=manager,content=(header+'\na,fqdn,host.example.com\n').encode())
    assert bool(batch.errors) is not valid
