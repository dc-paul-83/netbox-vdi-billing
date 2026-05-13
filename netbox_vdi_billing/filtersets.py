import django_filters
from netbox.filtersets import NetBoxModelFilterSet
from .models import VDIBillingProfile, VDIAssignment


class VDIBillingProfileFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = VDIBillingProfile
        fields = ('name',)


class VDIAssignmentFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = VDIAssignment
        fields = ('cost_center', 'department', 'assigned_to', 'profile')
