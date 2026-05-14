import django_tables2 as tables
from netbox.tables import NetBoxTable, columns
from .models import CostCenter, VDIBillingProfile, VDIAssignment


class CostCenterTable(NetBoxTable):
    number = tables.Column(linkify=True, verbose_name='KST-Nummer')
    name = tables.Column(verbose_name='Bezeichnung')
    department = tables.Column(verbose_name='Abteilung')
    vm_count = tables.Column(accessor='assignment_count', verbose_name='VMs', orderable=True)
    total_monthly = tables.Column(verbose_name='€/Monat', orderable=False)

    def render_total_monthly(self, value):
        if value:
            return f'{value:,.2f} €'.replace(',', '.')
        return '0,00 €'

    class Meta(NetBoxTable.Meta):
        model = CostCenter
        fields = ('pk', 'number', 'name', 'department', 'vm_count', 'total_monthly', 'actions')
        default_columns = ('number', 'name', 'department', 'vm_count', 'total_monthly')


class VDIBillingProfileTable(NetBoxTable):
    name = tables.Column(linkify=True)
    base_price = tables.Column(verbose_name='Grundpreis')
    vcpu_price = tables.Column(verbose_name='€/vCPU')
    ram_price_per_gb = tables.Column(verbose_name='€/GB RAM')
    gpu_surcharge = tables.Column(verbose_name='GPU-Aufschlag')
    assignment_count = tables.Column(verbose_name='Zuordnungen', orderable=False)

    class Meta(NetBoxTable.Meta):
        model = VDIBillingProfile
        fields = ('pk', 'name', 'base_price', 'vcpu_price', 'ram_price_per_gb',
                  'gpu_surcharge', 'assignment_count', 'description', 'actions')
        default_columns = ('name', 'base_price', 'vcpu_price', 'ram_price_per_gb',
                           'gpu_surcharge', 'assignment_count')


class VDIAssignmentTable(NetBoxTable):
    virtual_machine = tables.Column(linkify=True, verbose_name='VM')
    cost_center = tables.Column(linkify=True, verbose_name='Kostenstelle')
    profile = tables.Column(linkify=True, verbose_name='Profil')
    assigned_to = tables.Column(verbose_name='Zugewiesen an')
    email = tables.Column(verbose_name='E-Mail')
    cost_monthly = tables.Column(verbose_name='€/Monat', orderable=False)
    pricing_source = tables.Column(verbose_name='Preisquelle', orderable=False)

    def render_cost_monthly(self, value):
        if value:
            return f'{value:,.2f} €'.replace(',', '.')
        return '—'

    class Meta(NetBoxTable.Meta):
        model = VDIAssignment
        fields = ('pk', 'virtual_machine', 'cost_center', 'profile',
                  'assigned_to', 'email', 'cost_monthly', 'pricing_source', 'actions')
        default_columns = ('virtual_machine', 'cost_center',
                           'assigned_to', 'email', 'cost_monthly', 'pricing_source')
