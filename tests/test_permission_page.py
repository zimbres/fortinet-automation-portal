import pytest

pytestmark=pytest.mark.django_db


@pytest.mark.parametrize('debug',[True,False])
def test_shared_permission_page_for_catalog_usage_and_admin_pages(client,scope,settings,debug):
    settings.DEBUG=debug
    client.force_login(scope[0])
    for url in ['/objects/','/groups/','/usage/','/users/','/audit/']:
        response=client.get(url)
        assert response.status_code==403
        assert b'Ask your superadministrator for' in response.content
        assert b'data-access-denied' in response.content
        assert b'Traceback' not in response.content
        assert b'href="/"' in response.content


def test_ajax_permission_failure_has_shared_page_retarget_headers(client,scope):
    client.force_login(scope[0])
    response=client.get('/objects/',HTTP_HX_REQUEST='true')
    assert response.status_code==403
    assert response['X-Portal-Access-Denied']=='1'
    assert response['HX-Retarget']=='#main'
    assert response['HX-Reselect']=='#main'
    assert b'local catalog access' in response.content
