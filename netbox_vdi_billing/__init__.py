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
        'gpu_tag': 'VDI-GPU',
        'gpu_pool_pattern': r'nvidia|vgpu|gpu|grid',
        # LDAP für E-Mail-Sync (optional, nur nötig wenn kein AUTH_LDAP_* in NetBox)
        # 'ldap_server':      'ldap://dc.example.com',
        # 'ldap_bind_dn':     'CN=svc-netbox,OU=...,DC=example,DC=com',
        # 'ldap_bind_password': 'geheim',
        # 'ldap_search_base': 'DC=example,DC=com',
    }

    def ready(self):
        super().ready()
        # Modelle für Custom-Fields & Event-Rules in NetBox registrieren
        from . import models  # noqa: F401


config = VDIBillingConfig
