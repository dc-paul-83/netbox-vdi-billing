from decimal import Decimal
from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel
from virtualization.models import VirtualMachine


class PluginSettings(models.Model):
    """
    Global plugin settings for optional features.
    Singleton pattern: only one record exists.
    """
    billing_enabled = models.BooleanField(
        default=True,
        verbose_name='Enable Billing',
        help_text='Show cost calculations in assignments, overview, and PDFs.',
    )
    show_gpu_badge = models.BooleanField(
        default=True,
        verbose_name='Show GPU Badge',
        help_text='Display GPU status badge in assignment list.',
    )
    show_email = models.BooleanField(
        default=True,
        verbose_name='Show Email Addresses',
        help_text='Show email column in assignments (if synchronized from AD).',
    )
    last_modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Plugin Setting'
        verbose_name_plural = 'Plugin Settings'

    def __str__(self):
        return 'VDI Billing Plugin – Einstellungen'

    @classmethod
    def get_settings(cls):
        """Gibt die einzige PluginSettings-Instanz zurück oder erzeugt sie."""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings


class CostCenter(NetBoxModel):
    """
    Cost Center — linked to VDI assignments.
    Multiple VMs can be assigned to the same cost center.
    """
    number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Cost Center Number',
        help_text='Unique cost center identifier, e.g., 11554',
    )
    name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Name',
        help_text='Optional name/description of the cost center',
    )
    department = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Department',
    )
    description = models.TextField(blank=True, verbose_name='Description')

    class Meta:
        ordering = ['number']
        verbose_name = 'Cost Center'
        verbose_name_plural = 'Cost Centers'

    def __str__(self):
        if self.name:
            return f'{self.number} – {self.name}'
        return self.number

    def get_absolute_url(self):
        return reverse('plugins:netbox_vdi_billing:costcenter', args=[self.pk])

    def to_csv(self):
        return (
            self.number,
            self.name,
            self.department,
            self.description,
        )

    @property
    def vm_count(self):
        return self.assignments.count()

    @property
    def total_monthly(self):
        return round(sum(a.cost_monthly for a in self.assignments.select_related('profile', 'virtual_machine')), 2)


class VDIBillingProfile(NetBoxModel):
    """
    Price profile for a VDI class (e.g., Standard, GPU Workstation, Persistent).
    Costs are calculated from VM specifications (vCPU, RAM, GPU).
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Profile Name',
    )
    base_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        verbose_name='Base Price (€/month)',
        help_text='Fixed monthly amount per VM, independent of resources.',
    )
    vcpu_price = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0.00'),
        verbose_name='Price per vCPU (€/month)',
    )
    ram_price_per_gb = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0.00'),
        verbose_name='Price per GB RAM (€/month)',
    )
    gpu_surcharge = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0.00'),
        verbose_name='GPU Surcharge (€/month)',
        help_text='Added when VM has VDI-GPU tag or gpu custom field.',
    )
    description = models.TextField(blank=True, verbose_name='Description')

    class Meta:
        ordering = ['name']
        verbose_name = 'VDI Billing Profile'
        verbose_name_plural = 'VDI Billing Profiles'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_vdi_billing:vdibillingprofile', args=[self.pk])

    def to_csv(self):
        return (
            self.name,
            self.base_price,
            self.vcpu_price,
            self.ram_price_per_gb,
            self.gpu_surcharge,
            self.description,
        )

    def calculate_cost(self, vm: VirtualMachine) -> float:
        """Berechnet den Monatspreis für eine konkrete VM."""
        cost = float(self.base_price)
        cost += float(self.vcpu_price) * float(vm.vcpus or 0)
        cost += float(self.ram_price_per_gb) * float(vm.memory or 0) / 1024.0
        # GPU-Erkennung: Custom Field "gpu" ODER Tag "VDI-GPU"
        has_gpu = bool(vm.custom_field_data.get('gpu'))
        if not has_gpu and float(self.gpu_surcharge) > 0:
            has_gpu = vm.tags.filter(name='VDI-GPU').exists()
        if has_gpu:
            cost += float(self.gpu_surcharge)
        return round(cost, 2)


class VDIAssignment(NetBoxModel):
    """
    Links a NetBox VM to billing information:
    Cost center, price profile, and optional fixed price.
    """
    virtual_machine = models.OneToOneField(
        to=VirtualMachine,
        on_delete=models.CASCADE,
        related_name='vdi_billing',
        verbose_name='Virtual Machine',
    )
    profile = models.ForeignKey(
        to=VDIBillingProfile,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assignments',
        verbose_name='Price Profile',
        help_text='Profile for automatic cost calculation based on VM specs.',
    )
    cost_center = models.ForeignKey(
        to=CostCenter,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assignments',
        verbose_name='Cost Center',
    )
    assigned_to = models.CharField(
        max_length=200, blank=True,
        verbose_name='Assigned To',
        help_text='Name of user or team.',
    )
    email = models.EmailField(
        blank=True,
        verbose_name='Email Address',
        help_text='User email (synchronized from Active Directory).',
    )
    cost_override = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name='Fixed Price (€/month)',
        help_text='Overrides profile calculation with a fixed monthly price.',
    )
    notes = models.TextField(blank=True, verbose_name='Notes')

    class Meta:
        ordering = ['virtual_machine__name']
        verbose_name = 'VDI Assignment'
        verbose_name_plural = 'VDI Assignments'

    def __str__(self):
        cc = str(self.cost_center) if self.cost_center else 'Keine Kostenstelle'
        return f'{self.virtual_machine.name} – {cc}'

    def get_absolute_url(self):
        if self.pk:
            return reverse('plugins:netbox_vdi_billing:vdiassignment', args=[self.pk])
        return reverse('plugins:netbox_vdi_billing:vdiassignment_list')

    def to_csv(self):
        return (
            self.virtual_machine.name,
            self.cost_center.number if self.cost_center else '',
            self.cost_center.department if self.cost_center else '',
            self.profile.name if self.profile else '',
            self.assigned_to,
            self.email,
            self.cost_override if self.cost_override is not None else '',
            self.cost_monthly,
            self.notes,
        )

    @property
    def cost_monthly(self) -> float:
        """Monthly cost: fixed price > profile > 0."""
        if self.cost_override is not None:
            return round(float(self.cost_override), 2)
        if self.profile:
            return self.profile.calculate_cost(self.virtual_machine)
        return 0.0

    @property
    def cost_yearly(self) -> float:
        return round(self.cost_monthly * 12, 2)

    @property
    def pricing_source(self) -> str:
        if self.cost_override is not None:
            return 'Festpreis'
        if self.profile:
            return f'Profil: {self.profile.name}'
        return '—'
