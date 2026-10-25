"""Shared permission guidance without exposing internal exception details."""
from django.shortcuts import render

CATALOG_VIEW = {'objects','groups','import_example'}
CATALOG_MANAGE = {'object_new','object_edit','object_delete','group_new','group_edit','group_delete','import_objects','confirm_objects','delete_selected_objects'}
SUPERADMIN = {'users','user_new','user_edit','user_delete','audit'}


def permission_denied(request, exception):
    route = getattr(request.resolver_match, 'url_name', '')
    if route == 'group_new':
        access = 'Administrator access and permission to manage the local catalog'
    elif route in {'restrictions', 'restriction_new', 'restriction_edit', 'restriction_delete', 'restriction_import'}:
        access = 'Administrator or Superadministrator access'
    elif route in CATALOG_VIEW:
        access = 'local catalog access'
    elif route in CATALOG_MANAGE:
        access = 'permission to manage the local catalog'
    elif route == 'unused':
        access = 'local catalog and firewall-group access'
    elif route in SUPERADMIN:
        access = 'superadministrator access'
    else:
        access = 'the required access to this page or action'
    response = render(request, 'portal/access_denied.html', {'title':'Access required','required_access':access}, status=403)
    response['X-Portal-Access-Denied'] = '1'
    if request.headers.get('HX-Request') == 'true':
        response['HX-Retarget'] = '#main'
        response['HX-Reselect'] = '#main'
        response['HX-Reswap'] = 'outerHTML'
    return response
