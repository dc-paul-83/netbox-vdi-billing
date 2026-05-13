from netbox.api.routers import NetBoxRouter
from . import views

router = NetBoxRouter()
router.register('profiles',    views.VDIBillingProfileViewSet)
router.register('assignments', views.VDIAssignmentViewSet)

urlpatterns = router.urls
