from netbox.plugins.templates import PluginTemplateExtension


class VMBillingPanel(PluginTemplateExtension):
    """
    Zeigt Abrechnungsinfos auf der NetBox VM-Detailseite an.
    """
    models = ['virtualization.virtualmachine']

    def right_page(self):
        vm = self.context['object']
        try:
            assignment = vm.vdi_billing
        except Exception:
            assignment = None

        return self.render(
            'netbox_vdi_billing/inc/vm_billing_panel.html',
            extra_context={
                'assignment': assignment,
                'vm': vm,
            },
        )


template_extensions = [VMBillingPanel]
