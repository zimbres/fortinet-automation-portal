from tests.group_helpers import group_for
import pytest
from tests.test_catalog import manager
from tests.test_installations import installation

pytestmark = pytest.mark.django_db


def test_new_request_preview_and_submission(client, installation, manager, scope):
    from apps.changes.models import InstallationRequest
    client.force_login(manager)
    data = {'objects':[installation[1].pk], 'groups':[], 'firewall_group':group_for(scope[2]).pk, 'idempotency_key':'web'}
    response = client.post('/requests/new/', {**data,'action':'preview'})
    assert response.status_code == 200
    assert b'portal_host' in response.content
    assert InstallationRequest.objects.count() == 1
    response = client.post('/requests/new/', {**data,'action':'submit'})
    assert response.status_code == 302
    assert InstallationRequest.objects.count() == 2


def test_installation_details_and_independent_approval(client, installation, scope):
    item = installation[0]
    client.force_login(scope[1])
    detail = client.get(f'/installations/{item.pk}/')
    assert detail.status_code == 200
    assert b'portal_host' in detail.content and b'Edge' in detail.content
    assert client.get(f'/installations/{item.pk}/approve/').status_code == 405
    assert client.post(f'/installations/{item.pk}/approve/').status_code == 302
    item.refresh_from_db()
    assert item.approval_status == 'APPROVED'


def test_partial_scope_user_cannot_discover_installation_via_detail_queue_or_dashboard(client, installation, scope):
    from apps.changes.models import InstallationTarget
    from apps.firewalls.models import Firewall, VDOM
    vd = VDOM.objects.create(firewall=Firewall.objects.create(name='Hidden device',hostname='192.0.2.2'),name='root')
    item = installation[0]
    InstallationTarget.objects.create(request=item,vdom=vd,destination={'firewall':'Hidden device'})
    client.force_login(scope[1])
    assert client.get(f'/installations/{item.pk}/').status_code == 404
    for url in ['/', '/history/','/approvals/']:
        assert str(item.pk).encode() not in client.get(url).content


def test_history_paginates_filtered_authorized_installations(client, installation, scope):
    from apps.changes.models import InstallationRequest, InstallationTarget
    from django.utils import timezone
    from urllib.parse import parse_qs, urlsplit
    from html.parser import HTMLParser
    original = installation[0]
    target = original.targets.get()
    rows = InstallationRequest.objects.bulk_create([
        InstallationRequest(requester=original.requester, snapshot=original.snapshot,
                            payload_digest=original.payload_digest, idempotency_key=f'page-{i}')
        for i in range(26)
    ])
    InstallationTarget.objects.bulk_create([
        InstallationTarget(request=item, vdom=target.vdom, destination=target.destination) for item in rows
    ])
    # Equal timestamps still need stable pagination with no repeated or missing rows.
    InstallationRequest.objects.all().update(created_at=timezone.now())
    client.force_login(scope[1])
    first = client.get('/history/', {'q': 'PENDING'})
    assert first.status_code == 200
    assert len(first.context['installations']) == 25
    assert first.context['page_obj'].paginator.count == 27
    assert b'Showing 1' in first.content and b'27 requests' in first.content
    assert b'Showing up to 100' not in first.content
    second = client.get('/history/', {'q': 'PENDING', 'page': 2})
    ids = {item.pk for item in first.context['installations']}
    assert len(second.context['installations']) == 2
    assert not ids.intersection(item.pk for item in second.context['installations'])
    class Links(HTMLParser):
        links = []
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'a' and 'page=' in attrs.get('href', ''): self.links.append(attrs['href'])
    links = Links(); links.feed(first.content.decode())
    assert links.links
    assert all(parse_qs(urlsplit(link).query)['q'] == ['PENDING'] for link in links.links)
    assert first.content.count(b'id="request-results"') == 1
    assert b'aria-label="Operation history pages"' in first.content
    assert client.get('/history/', {'page': 'invalid'}).context['page_obj'].number == 1
    assert client.get('/history/', {'page': 999}).context['page_obj'].number == 2
    empty = client.get('/history/', {'q': 'no-matching-status'})
    assert empty.context['page_obj'].paginator.count == 0
    assert b'Showing 0' in empty.content


def test_status_polling_keeps_current_history_filter_and_page(client, installation, scope):
    client.force_login(scope[1])
    response = client.get('/history/', {'q': 'PENDING & review', 'page': 2})
    from html.parser import HTMLParser
    class Region(HTMLParser):
        attrs = None
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if attrs.get('id') == 'request-results': self.attrs = attrs
    region = Region(); region.feed(response.content.decode())
    assert region.attrs.get('hx-trigger') == 'every 5s'
    assert region.attrs['hx-get'] == '/history/?q=PENDING+%26+review&page=2'
    assert region.attrs['hx-select'] == '#request-results'
    for path, region_id in [('/', 'overview-live'), ('/approvals/', 'request-results')]:
        response = client.get(path)
        assert f'id="{region_id}"'.encode() in response.content
        assert b'hx-trigger="every 5s"' in response.content


@pytest.mark.parametrize('approval,execution,polling', [
    ('PENDING','PENDING',True), ('APPROVED','PENDING',True),
    ('APPROVED','RUNNING',True), ('APPROVED','RECONCILIATION_REQUIRED',True),
    ('APPROVED','SUCCEEDED',False), ('APPROVED','FAILED',False),
    ('APPROVED','PARTIALLY_SUCCEEDED',False), ('CANCELLED','CANCELLED',False),
    ('REJECTED','PENDING',False),
])
def test_installation_polling_stops_after_final_state(client, installation, scope, approval, execution, polling):
    from apps.changes.models import InstallationRequest
    item = installation[0]
    InstallationRequest.objects.filter(pk=item.pk).update(
        approval_status=approval, execution_status=execution,
        approver=scope[1] if approval == 'APPROVED' else None,
    )
    client.force_login(scope[1])
    response = client.get(f'/installations/{item.pk}/', HTTP_HX_REQUEST='true')
    assert response.status_code == 200
    assert b'id="installation-live"' in response.content
    assert (b'hx-trigger="every 5s"' in response.content) == polling
    assert execution.replace('_', ' ').capitalize().encode() in response.content
