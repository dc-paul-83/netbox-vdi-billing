from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from virtualization.api.serializers import VirtualMachineSerializer
from ..models import VDIBillingProfile, VDIAssignment


class VDIBillingProfileSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_vdi_billing-api:vdibillingprofile-detail'
    )
    display = serializers.SerializerMethodField()

    def get_display(self, obj):
        return str(obj)

    class Meta:
        model = VDIBillingProfile
        fields = (
            'id', 'url', 'display', 'name',
            'base_price', 'vcpu_price', 'ram_price_per_gb', 'gpu_surcharge',
            'description', 'tags', 'custom_fields', 'created', 'last_updated',
        )


class VDIAssignmentSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_vdi_billing-api:vdiassignment-detail'
    )
    display = serializers.SerializerMethodField()
    profile = VDIBillingProfileSerializer(nested=True, required=False, allow_null=True)

    def get_display(self, obj):
        return str(obj)

    class Meta:
        model = VDIAssignment
        fields = (
            'id', 'url', 'display',
            'virtual_machine', 'profile',
            'cost_center', 'department', 'assigned_to',
            'cost_override', 'notes',
            'tags', 'custom_fields', 'created', 'last_updated',
        )
