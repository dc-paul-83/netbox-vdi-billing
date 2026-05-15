from netbox.plugins.navigation import PluginMenu, PluginMenuButton, PluginMenuItem
from netbox.choices import ButtonColorChoices

menu = PluginMenu(
    label='VDI Billing',
    groups=(
        (
            'Reports',
            (
                PluginMenuItem(
                    link='plugins:netbox_vdi_billing:chargeback_overview',
                    link_text='Chargeback Overview',
                    permissions=['netbox_vdi_billing.view_vdiassignment'],
                ),
                PluginMenuItem(
                    link='plugins:netbox_vdi_billing:vdiassignment_list',
                    link_text='All Assignments',
                    permissions=['netbox_vdi_billing.view_vdiassignment'],
                    buttons=(
                        PluginMenuButton(
                            link='plugins:netbox_vdi_billing:vdiassignment_add',
                            title='Add Assignment',
                            icon_class='mdi mdi-plus-thick',
                            color=ButtonColorChoices.GREEN,
                            permissions=['netbox_vdi_billing.add_vdiassignment'],
                        ),
                    ),
                ),
            ),
        ),
        (
            'Configuration',
            (
                PluginMenuItem(
                    link='plugins:netbox_vdi_billing:costcenter_list',
                    link_text='Cost Centers',
                    permissions=['netbox_vdi_billing.view_costcenter'],
                    buttons=(
                        PluginMenuButton(
                            link='plugins:netbox_vdi_billing:costcenter_add',
                            title='Add Cost Center',
                            icon_class='mdi mdi-plus-thick',
                            color=ButtonColorChoices.GREEN,
                            permissions=['netbox_vdi_billing.add_costcenter'],
                        ),
                        PluginMenuButton(
                            link='plugins:netbox_vdi_billing:bulk_assign',
                            title='Bulk Assign',
                            icon_class='mdi mdi-checkbox-multiple-marked',
                            color=ButtonColorChoices.BLUE,
                            permissions=['netbox_vdi_billing.add_vdiassignment'],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link='plugins:netbox_vdi_billing:vdibillingprofile_list',
                    link_text='Price Profiles',
                    permissions=['netbox_vdi_billing.view_vdibillingprofile'],
                    buttons=(
                        PluginMenuButton(
                            link='plugins:netbox_vdi_billing:vdibillingprofile_add',
                            title='Add Profile',
                            icon_class='mdi mdi-plus-thick',
                            color=ButtonColorChoices.GREEN,
                            permissions=['netbox_vdi_billing.add_vdibillingprofile'],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link='plugins:netbox_vdi_billing:plugin_settings',
                    link_text='Settings',
                    permissions=['netbox_vdi_billing.view_pluginsettings'],
                ),
            ),
        ),
    ),
    icon_class='mdi mdi-currency-eur',
)
