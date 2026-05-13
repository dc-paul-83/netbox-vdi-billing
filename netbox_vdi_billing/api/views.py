from netbox.api.viewsets import NetBoxModelViewSet
from ..models import VDIBillingProfile, VDIAssignment
from .serializers import VDIBillingProfileSerializer, VDIAssignmentSerializer


class VDIBillingProfileViewSet(NetBoxModelViewSet):
    queryset = VDIBillingProfile.objects.prefetch_related('tags')
    serializer_class = VDIBillingProfileSerializer


class VDIAssignmentViewSet(NetBoxModelViewSet):
    queryset = VDIAssignment.objects.select_related(
        'virtual_machine', 'profile'
    ).prefetch_related('tags')
    serializer_class = VDIAssignmentSerializer
