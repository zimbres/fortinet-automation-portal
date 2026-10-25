from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from apps.accounts.forms import EmailAuthenticationForm
from apps.portal import views
from apps.portal import user_views
from apps.portal import restriction_views as restrictions
from apps.portal import catalog_views as catalog, installation_views as installations, firewall_group_views as firewall_groups

urlpatterns = [
    path('health/',views.health,name='health'),
    path('',views.dashboard,name='dashboard'),
    path('login/',user_views.PortalLoginView.as_view(template_name='portal/login.html',authentication_form=EmailAuthenticationForm,extra_context={'oidc_enabled':'mozilla_django_oidc' in settings.INSTALLED_APPS}),name='login'),
    path('logout/',auth_views.LogoutView.as_view(),name='logout'),
    path('firewalls/',views.firewalls,name='firewalls'),
    path('firewalls/new/',views.firewall_new,name='firewall_new'),
    path('firewalls/<int:pk>/edit/',views.firewall_edit,name='firewall_edit'),
    path('firewalls/<int:pk>/vdom/',views.vdom_new,name='vdom_new'),
    path('vdom/<int:pk>/delete/',views.vdom_delete,name='vdom_delete'),
    path('vdom/<int:pk>/check/',views.connection_check,name='connection_check'),
    path('objects/',catalog.catalog,name='objects'),
    path('restrictions/', restrictions.restrictions, name='restrictions'),
    path('restrictions/new/', restrictions.restriction_edit, name='restriction_new'),
    path('restrictions/import/', restrictions.restriction_import, name='restriction_import'),
    path('restrictions/<int:pk>/edit/', restrictions.restriction_edit, name='restriction_edit'),
    path('restrictions/<int:pk>/delete/', restrictions.restriction_delete, name='restriction_delete'),
    path('objects/new/',catalog.catalog_edit,name='object_new'),
    path('objects/delete-selected/',catalog.delete_selected_objects,name='delete_selected_objects'),
    path('objects/<int:pk>/edit/',catalog.catalog_edit,name='object_edit'),
    path('objects/<int:pk>/delete/',catalog.catalog_delete,name='object_delete'),
    path('objects/import/',catalog.import_objects,name='import_objects'),
    path('objects/import/example.csv',catalog.import_example,name='import_example'),
    path('objects/import/<uuid:token>/confirm/',catalog.confirm_objects,name='confirm_objects'),
    path('groups/',catalog.catalog,{'kind':'groups'},name='groups'),
    path('groups/new/',catalog.catalog_edit,{'kind':'groups'},name='group_new'),
    path('groups/<int:pk>/edit/',catalog.catalog_edit,{'kind':'groups'},name='group_edit'),
    path('groups/<int:pk>/delete/',catalog.catalog_delete,name='group_delete'),
    path('firewall-groups/',firewall_groups.firewall_groups,name='firewall_groups'),
    path('firewall-groups/new/',firewall_groups.firewall_group_edit,name='firewall_group_new'),
    path('firewall-groups/<int:pk>/edit/',firewall_groups.firewall_group_edit,name='firewall_group_edit'),
    path('device-inventory/',views.inventory,name='device_inventory'),
    path('requests/new/',installations.new_installation,name='new_request'),
    path('installations/<uuid:pk>/',installations.installation_detail,name='installation_detail'),
    path('installations/<uuid:pk>/<str:action>/',installations.installation_decision,name='installation_decision'),
    path('requests/<uuid:pk>/',views.request_detail,name='request_detail'),
    path('requests/<uuid:pk>/<str:action>/',views.decision,name='decision'),
    path('approvals/',views.approvals,name='approvals'),
    path('history/',views.history,name='history'),
    path('usage/',views.unused,name='unused'),
    path('profile/',user_views.profile,name='profile'),
    path('password/change-required/',user_views.password_change_required,name='password_change_required'),
    path('profile/picture/',user_views.profile_picture,name='profile_picture'),
    path('users/',views.users,name='users'),
    path('users/new/',views.user_new,name='user_new'),
    path('users/<int:pk>/edit/',user_views.user_edit,name='user_edit'),
    path('users/<int:pk>/delete/',user_views.user_delete,name='user_delete'),
    path('audit/',views.audit_log,name='audit'),
    path('admin/',admin.site.urls),
]
if 'mozilla_django_oidc' in settings.INSTALLED_APPS:
    urlpatterns += [path('oidc/',include('mozilla_django_oidc.urls'))]

handler403 = 'apps.portal.errors.permission_denied'
