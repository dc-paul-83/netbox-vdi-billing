import django_filters
from netbox.filtersets import NetBoxModelFilterSet
from .models import CostCenter, VDIBillingProfile, VDIAssignment


class CostCenterFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = CostCenter
        fields = ('number', 'name', 'department')


class VDIBillingProfileFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = VDIBillingProfile
        fields = ('name',)


class VDIAssignmentFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = VDIAssignment
        fields = ('cost_center', 'assigned_to', 'profile')
