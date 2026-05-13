from decimal import Decimal
from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel
from virtualization.models import VirtualMachine


class CostCenter(NetBoxModel):
    """
    Kostenstelle — wird mit VDI-Zuordnungen verknüpft.
    Mehrere VMs können derselben Kostenstelle zugewiesen werden.
    """
    number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='KST-Nummer',
        help_text='Eindeutige Kostenstellen-Nummer, z.B. 11554',
    )
    name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Bezeichnung',
        help_text='Optionaler Name der Kostenstelle',
    )
    department = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Abteilung',
    )
    description = models.TextField(blank=True, verbose_name='Beschreibung')

    class Meta:
        ordering = ['number']
        verbose_name = 'Kostenstelle'
        verbose_name_plural = 'Kostenstellen'

    def __str__(self):
        if self.name:
            return f'{self.number} – {self.name}'
        return self.number

    def get_absolute_url(self):
        return reverse('plugins:netbox_vdi_billing:costcenter', args=[self.pk])

    @property
    def vm_count(self):
        return self.assignments.count()

    @property
    def total_monthly(self):
        return round(sum(a.cost_monthly for a in self.assignments.select_related('profile', 'virtual_machine')), 2)


class VDIBillingProfile(NetBoxModel):
    """
    Preisprofil für eine VDI-Klasse (z.B. "Standard", "GPU-Workstation", "Persistent").
    Kosten werden aus VM-Specs (vCPU, RAM, GPU) berechnet.
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Profilname',
    )
    base_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        verbose_name='Grundpreis (€/Monat)',
        help_text='Fixer Grundbetrag unabhängig von den VM-Ressourcen.',
    )
    vcpu_price = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0.00'),
        verbose_name='Preis pro vCPU (€/Monat)',
    )
    ram_price_per_gb = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0.00'),
        verbose_name='Preis pro GB RAM (€/Monat)',
    )
    gpu_surcharge = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0.00'),
        verbose_name='GPU-Aufschlag (€/Monat)',
        help_text='Wird addiert wenn das Custom-Field "gpu" der VM gesetzt ist.',
    )
    description = models.TextField(blank=True, verbose_name='Beschreibung')

    class Meta:
        ordering = ['name']
        verbose_name = 'VDI-Preisprofil'
        verbose_name_plural = 'VDI-Preisprofile'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_vdi_billing:vdibillingprofile', args=[self.pk])

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
    Verknüpft eine NetBox-VM mit Abrechnungsinformationen:
    Kostenstelle, Preisprofil und optionalem Festpreis.
    """
    virtual_machine = models.OneToOneField(
        to=VirtualMachine,
        on_delete=models.CASCADE,
        related_name='vdi_billing',
        verbose_name='Virtuelle Maschine',
    )
    profile = models.ForeignKey(
        to=VDIBillingProfile,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assignments',
        verbose_name='Preisprofil',
        help_text='Profil zur automatischen Kostenberechnung aus VM-Specs.',
    )
    cost_center = models.ForeignKey(
        to=CostCenter,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assignments',
        verbose_name='Kostenstelle',
    )
    assigned_to = models.CharField(
        max_length=200, blank=True,
        verbose_name='Zugewiesen an',
        help_text='Name des Benutzers oder Teams.',
    )
    cost_override = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name='Festpreis (€/Monat)',
        help_text='Überschreibt die Profilberechnung mit einem festen Monatspreis.',
    )
    notes = models.TextField(blank=True, verbose_name='Notizen')

    class Meta:
        ordering = ['virtual_machine__name']
        verbose_name = 'VDI-Abrechnungszuordnung'
        verbose_name_plural = 'VDI-Abrechnungszuordnungen'

    def __str__(self):
        cc = str(self.cost_center) if self.cost_center else 'Keine Kostenstelle'
        return f'{self.virtual_machine.name} – {cc}'

    def get_absolute_url(self):
        if self.pk:
            return reverse('plugins:netbox_vdi_billing:vdiassignment', args=[self.pk])
        return reverse('plugins:netbox_vdi_billing:vdiassignment_list')

    @property
    def cost_monthly(self) -> float:
        """Monatliche Kosten: Festpreis > Profil > 0."""
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
