from netbox.plugins.navigation import PluginMenu, PluginMenuButton, PluginMenuItem
from netbox.choices import ButtonColorChoices

menu = PluginMenu(
    label='VDI Abrechnung',
    groups=(
        (
            'Auswertung',
            (
                PluginMenuItem(
                    link='plugins:netbox_vdi_billing:chargeback_overview',
                    link_text='Kostenstellen-Übersicht',
                    permissions=['netbox_vdi_billing.view_vdiassignment'],
                    buttons=(
                        PluginMenuButton(
                            link='plugins:netbox_vdi_billing:vdiassignment_add',
                            title='VM zuordnen',
                            icon_class='mdi mdi-plus-thick',
                            color=ButtonColorChoices.GREEN,
                            permissions=['netbox_vdi_billing.add_vdiassignment'],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link='plugins:netbox_vdi_billing:vdiassignment_list',
                    link_text='Alle Zuordnungen',
                    permissions=['netbox_vdi_billing.view_vdiassignment'],
                ),
            ),
        ),
        (
            'Konfiguration',
            (
                PluginMenuItem(
                    link='plugins:netbox_vdi_billing:vdibillingprofile_list',
                    link_text='Preisprofile',
                    permissions=['netbox_vdi_billing.view_vdibillingprofile'],
                    buttons=(
                        PluginMenuButton(
                            link='plugins:netbox_vdi_billing:vdibillingprofile_add',
                            title='Profil hinzufügen',
                            icon_class='mdi mdi-plus-thick',
                            color=ButtonColorChoices.GREEN,
                            permissions=['netbox_vdi_billing.add_vdibillingprofile'],
                        ),
                    ),
                ),
            ),
        ),
    ),
    icon_class='mdi mdi-currency-eur',
)
