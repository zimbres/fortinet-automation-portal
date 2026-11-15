import base64
import binascii

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.views.decorators.debug import sensitive_post_parameters
from config.public_url import normalize_public_url

from apps.inventory.models import FeedAccount, ThreatFeed
from apps.inventory.threat_feed_forms import FeedAccountForm
from apps.inventory.threat_feeds import delete_feed_configuration, disable_feed, require_feed_management, save_feed_account

# Match the cost of a normal credential check for unknown usernames.
_DUMMY_PASSWORD = make_password('unused-feed-password')


@never_cache
@require_http_methods(['GET', 'HEAD'])
def download(request, scope_slug, slug, filename):
    account = None
    try:
        scheme, encoded = request.headers.get('Authorization', '').split(' ', 1)
        if scheme.lower() != 'basic' or len(encoded) > 8192:
            raise ValueError
        username, password = base64.b64decode(encoded, validate=True).decode('utf-8').split(':', 1)
        account = FeedAccount.objects.filter(username=username).first()
        valid = check_password(password, account.password if account else _DUMMY_PASSWORD)
        if not valid or not account or not account.is_active:
            account = None
    except (ValueError, UnicodeError, binascii.Error):
        account = None
    if account is None:
        response = HttpResponse('Feed credentials required.\n', status=401, content_type='text/plain; charset=utf-8')
        response['WWW-Authenticate'] = 'Basic realm="Threat feeds", charset="UTF-8"'
        return response
    if filename not in ('ip_list.txt', 'domain_list.txt'):
        return HttpResponse(status=404)
    feed = account.feeds.filter(scope__slug=scope_slug, scope__firewall_group__enabled=True,
                               slug=slug, enabled=True, revision__gt=0,
                               approved_request__approval_status='APPROVED',
                               approved_request__execution_status='SUCCEEDED').first()
    if feed is None:
        return HttpResponse(status=404)
    body = feed.ip_text if filename == 'ip_list.txt' else feed.domain_text
    response = HttpResponse(body if request.method == 'GET' else '', content_type='text/plain; charset=utf-8')
    response['Content-Length'] = len(body.encode('utf-8'))
    return response


@login_required
@require_http_methods(['GET'])
def configuration(request):
    require_feed_management(request.user)
    feeds = list(ThreatFeed.objects.select_related('group__entry','scope__firewall_group','approved_request'))
    base = normalize_public_url(settings.APP_PUBLIC_URL)
    for feed in feeds:
        # The configured base already includes any deployment prefix.
        feed.ip_url = f'{base}/threat-feeds/{feed.scope.slug}/{feed.slug}/ip_list.txt'
        feed.domain_url = f'{base}/threat-feeds/{feed.scope.slug}/{feed.slug}/domain_list.txt'
    return render(request, 'portal/threat_feeds.html', {
        'title':'Threat feeds', 'feeds':feeds, 'public_url':base,
        'accounts':FeedAccount.objects.prefetch_related('feeds__group__entry','feeds__scope__firewall_group'),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def publication_edit(request, pk=None):
    require_feed_management(request.user)
    if pk is None:
        return redirect(reverse('new_request') + '?target_kind=threat_feeds')
    feed = get_object_or_404(ThreatFeed, pk=pk)
    if request.method == 'POST':
        if request.POST.get('action') == 'disable':
            disable_feed(actor=request.user, pk=pk)
            messages.success(request, 'Publication disabled. Re-enable through a new approved request.')
        else:
            messages.error(request, 'Publication requires a new Threat Feeds request and approval.')
        return redirect('threat_feeds')
    return render(request, 'portal/threat_feed_disable.html', {'title':'Disable publication', 'feed':feed})


@login_required
@require_http_methods(['GET', 'POST'])
@sensitive_post_parameters('password')
def account_edit(request, pk=None):
    require_feed_management(request.user)
    account = get_object_or_404(FeedAccount, pk=pk) if pk else None
    initial = {'username':account.username, 'is_active':account.is_active, 'feeds':account.feeds.all()} if account else None
    form = FeedAccountForm(request.POST if request.method == 'POST' else None, initial=initial)
    if not account:
        form.fields['password'].required = True
    if request.method == 'POST' and form.is_valid():
        try:
            save_feed_account(actor=request.user, account_id=pk, **form.cleaned_data)
            messages.success(request, 'Feed account saved.')
            return redirect('threat_feeds')
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'portal/form.html', {
        'title':'Edit feed account' if account else 'Create feed account', 'form':form,
        'description':'Use these credentials for FortiGate HTTP Basic authentication. Feed accounts cannot sign in to the portal.',
        'submit_label':'Save feed account', 'cancel_url':reverse('threat_feeds'),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def configuration_delete(request, pk, account=False):
    require_feed_management(request.user)
    record = get_object_or_404(FeedAccount if account else ThreatFeed, pk=pk)
    if request.method == 'POST':
        delete_feed_configuration(actor=request.user, pk=pk, account=account)
        messages.success(request, 'Feed account deleted.' if account else 'Publication removed.')
        return redirect('threat_feeds')
    return render(request, 'portal/threat_feed_delete.html', {
        'title':'Delete feed account' if account else 'Remove publication', 'record':record,
    })
