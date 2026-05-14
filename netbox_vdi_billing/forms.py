from django import forms
from netbox.forms import NetBoxModelForm, NetBoxModelBulkEditForm
from utilities.forms.fields import DynamicModelChoiceField, DynamicModelMultipleChoiceField
from virtualization.models import VirtualMachine
from .models import CostCenter, VDIBillingProfile, VDIAssignment


class CostCenterForm(NetBoxModelForm):
    class Meta:
        model = CostCenter
        fields = ('number', 'name', 'department', 'description', 'tags')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class VDIBillingProfileForm(NetBoxModelForm):
    class Meta:
        model = VDIBillingProfile
        fields = ('name', 'base_price', 'vcpu_price', 'ram_price_per_gb',
                  'gpu_surcharge', 'description', 'tags')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class VDIAssignmentForm(NetBoxModelForm):
    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        label='Virtuelle Maschine',
    )
    profile = DynamicModelChoiceField(
        queryset=VDIBillingProfile.objects.all(),
        required=False,
        label='Preisprofil',
    )
    cost_center = DynamicModelChoiceField(
        queryset=CostCenter.objects.all(),
        required=False,
        label='Kostenstelle',
    )

    class Meta:
        model = VDIAssignment
        fields = ('virtual_machine', 'profile', 'cost_center',
                  'assigned_to', 'email', 'cost_override', 'notes', 'tags')
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class VDIAssignmentBulkEditForm(NetBoxModelBulkEditForm):
    cost_center = forms.ModelChoiceField(
        queryset=CostCenter.objects.all(),
        required=False,
        label='Kostenstelle',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    profile = forms.ModelChoiceField(
        queryset=VDIBillingProfile.objects.all(),
        required=False,
        label='Preisprofil',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    assigned_to = forms.CharField(
        max_length=200,
        required=False,
        label='Zugewiesen an',
    )
    email = forms.EmailField(
        required=False,
        label='E-Mail',
    )
    cost_override = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        label='Festpreis (€/Monat)',
    )

    model = VDIAssignment
    nullable_fields = ('cost_center', 'profile', 'assigned_to', 'email', 'cost_override')


class CostCenterBulkEditForm(NetBoxModelBulkEditForm):
    department = forms.CharField(
        max_length=200,
        required=False,
        label='Abteilung',
    )

    model = CostCenter
    nullable_fields = ('department',)


class BulkAssignCostCenterForm(forms.Form):
    """Formular für die Massen-Zuweisung mehrerer VMs zu einer Kostenstelle."""

    cost_center = forms.ModelChoiceField(
        queryset=CostCenter.objects.all(),
        label='Kostenstelle',
        empty_label='— Kostenstelle wählen —',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    profile = forms.ModelChoiceField(
        queryset=VDIBillingProfile.objects.all(),
        required=False,
        label='Preisprofil (optional)',
        empty_label='— kein Profil setzen —',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    overwrite = forms.BooleanField(
        required=False,
        label='Bestehende Zuordnungen überschreiben',
        initial=False,
    )
    virtual_machines = forms.ModelMultipleChoiceField(
        queryset=VirtualMachine.objects.none(),
        label='Virtuelle Maschinen',
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, vm_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if vm_queryset is not None:
            self.fields['virtual_machines'].queryset = vm_queryset
