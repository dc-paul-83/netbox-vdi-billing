import django_filters
from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet
from .models import CostCenter, VDIBillingProfile, VDIAssignment


class CostCenterFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = CostCenter
        fields = ('number', 'name', 'department')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(number__icontains=value) |
            Q(name__icontains=value) |
            Q(department__icontains=value) |
            Q(description__icontains=value)
        )


class VDIBillingProfileFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = VDIBillingProfile
        fields = ('name',)

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value)
        )


class VDIAssignmentFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = VDIAssignment
        fields = ('cost_center', 'assigned_to', 'profile')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(virtual_machine__name__icontains=value) |
            Q(cost_center__number__icontains=value) |
            Q(cost_center__name__icontains=value) |
            Q(assigned_to__icontains=value) |
            Q(notes__icontains=value)
        )
