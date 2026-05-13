from netbox.plugins import PluginConfig


class VDIBillingConfig(PluginConfig):
    name = 'netbox_vdi_billing'
    verbose_name = 'VDI Abrechnung'
    description = 'Kostenstellen-basierte VDI-Abrechnung mit Preisprofilen und Chargeback-Reports'
    version = '1.0.0'
    author = 'IT'
    base_url = 'vdi-billing'
    min_version = '4.5.0'
    default_settings = {
        # Horizon API Verbindungen (Liste, unterstützt mehrere Instanzen)
        # Eintragen in configuration.py unter PLUGINS_CONFIG['netbox_vdi_billing']
        # Beispiel:
        #   'horizon_instances': [
        #       {
        #           'host': 'horizon.example.com',
        #           'domain': 'EXAMPLE',
        #           'username': 'svc-netbox',
        #           'password': 'geheim',
        #       },
        #   ],
        #   'persistent_tag': 'VDI-Persistent',
        'horizon_instances': [],
        'persistent_tag': 'VDI-Persistent',
    }

    def ready(self):
        super().ready()
        # Modelle für Custom-Fields & Event-Rules in NetBox registrieren
        from . import models  # noqa: F401


config = VDIBillingConfig
