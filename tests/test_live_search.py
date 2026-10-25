import pytest
from tests.test_catalog import manager

pytestmark=pytest.mark.django_db


def test_address_search_matches_name_or_value_case_insensitively(client,manager):
    from apps.inventory.catalog import save_address
    first=save_address(actor=manager,name='office_host',kind='subnet',value='192.0.2.44')
    second=save_address(actor=manager,name='service',kind='fqdn',value='Host.Example.com')
    client.force_login(manager)
    for query,expected in [('OFFICE',[first.pk]),('192.0.2.44',[first.pk]),('HOST.EXAMPLE',[second.pk]),('not-found',[])]:
        response=client.get('/objects/',{'q':query},HTTP_HX_REQUEST='true')
        assert [obj.pk for obj in response.context['records']]==expected
        assert b'id="catalog-results"' in response.content
    for url in ['/objects/','/groups/','/history/']:
        page=client.get(url)
        assert b'input delay:300ms' in page.content
        assert b'>Search</button>' not in page.content and b'>Filter</button>' not in page.content


def test_inventory_retains_all_loaded_rows_for_instant_local_filter(client,scope):
    from unittest.mock import patch
    client.force_login(scope[0])
    rows=[{'name':'alpha','subnet':'192.0.2.1 255.255.255.255'},{'name':'beta','fqdn':'example.test'}]
    with patch('apps.portal.views.FortinetClient') as remote:
        remote.return_value.__enter__.return_value.list_addresses.return_value=rows
        page=client.get('/device-inventory/',{'vdom':scope[2].pk,'q':'alpha'})
    assert page.context['records']==rows
    assert b'data-local-search' in page.content and b'data-filter-row' in page.content
    remote.return_value.__enter__.return_value.list_addresses.assert_called_once()
