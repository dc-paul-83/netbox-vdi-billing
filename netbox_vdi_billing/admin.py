from django.contrib import admin
from .models import PluginSettings


@admin.register(PluginSettings)
class PluginSettingsAdmin(admin.ModelAdmin):
    """Admin-Interface für Plugin-Einstellungen (Singleton)."""

    def has_add_permission(self, request):
        """Verhindert neue Einträge (Singleton)."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Verhindert Löschen (Singleton)."""
        return False

    def changelist_view(self, request, extra_context=None):
        """Redirect zur Edit-View wenn es nur einen Eintrag gibt."""
        if self.get_queryset(request).count() == 1:
            obj = self.get_queryset(request).first()
            from django.shortcuts import redirect
            return redirect(f'/admin/netbox_vdi_billing/pluginsettings/{obj.pk}/change/')
        return super().changelist_view(request, extra_context)
