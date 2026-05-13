from django import forms
from netbox.forms import NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField
from virtualization.models import VirtualMachine
from .models import VDIBillingProfile, VDIAssignment


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

    class Meta:
        model = VDIAssignment
        fields = ('virtual_machine', 'profile', 'cost_center', 'department',
                  'assigned_to', 'cost_override', 'notes', 'tags')
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
