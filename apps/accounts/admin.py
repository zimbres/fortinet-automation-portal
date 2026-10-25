from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User
from .models import GroupGrant
from .models import CatalogGrant
from apps.audit.services import record_event


@admin.register(User)
class PortalUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('External identity', {'fields': ('external_issuer', 'external_subject')}),
    )

    def has_add_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def save_model(self, request, obj, form, change):
        super().save_model(request,obj,form,change)
        record_event(actor=request.user,event_type='user.updated' if change else 'user.created',metadata={'user_id':obj.pk})

    def delete_model(self, request, obj):
        record_event(actor=request.user,event_type='user.deleted',metadata={'user_id':obj.pk})
        super().delete_model(request,obj)


@admin.register(GroupGrant)
class GroupGrantAdmin(admin.ModelAdmin):
    list_display = ['user','firewall_group','capability']

    def has_module_permission(self, request): return request.user.is_active and request.user.is_superuser
    def has_view_permission(self, request, obj=None): return self.has_module_permission(request)
    def has_add_permission(self, request): return self.has_module_permission(request)
    def has_change_permission(self, request, obj=None): return self.has_module_permission(request)
    def has_delete_permission(self, request, obj=None): return self.has_module_permission(request)

    def save_model(self, request, obj, form, change):
        super().save_model(request,obj,form,change)
        record_event(actor=request.user,event_type='access.updated',metadata={'user_id':obj.user_id,'group_id':obj.firewall_group_id})

    def delete_model(self, request, obj):
        record_event(actor=request.user,event_type='access.revoked',metadata={'user_id':obj.user_id,'group_id':obj.firewall_group_id})
        super().delete_model(request,obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request,obj)


@admin.register(CatalogGrant)
class CatalogGrantAdmin(GroupGrantAdmin):
    list_display = ['user', 'capability']

    def save_model(self, request, obj, form, change):
        admin.ModelAdmin.save_model(self, request, obj, form, change)
        record_event(actor=request.user, event_type='catalog.access_updated', metadata={'user_id': obj.user_id})

    def delete_model(self, request, obj):
        record_event(actor=request.user, event_type='catalog.access_revoked', metadata={'user_id': obj.user_id})
        admin.ModelAdmin.delete_model(self, request, obj)
