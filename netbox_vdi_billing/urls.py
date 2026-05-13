from django.urls import path
from . import views

urlpatterns = [

    # ── Chargeback Übersicht ──────────────────────────────────────────────────
    path('', views.ChargebackOverviewView.as_view(), name='chargeback_overview'),
    path('print/<str:cost_center>/', views.ChargebackPrintView.as_view(), name='chargeback_print'),

    # ── Preisprofile ──────────────────────────────────────────────────────────
    path('profiles/', views.VDIBillingProfileListView.as_view(), name='vdibillingprofile_list'),
    path('profiles/add/', views.VDIBillingProfileEditView.as_view(), name='vdibillingprofile_add'),
    path('profiles/<int:pk>/', views.VDIBillingProfileView.as_view(), name='vdibillingprofile'),
    path('profiles/<int:pk>/edit/', views.VDIBillingProfileEditView.as_view(), name='vdibillingprofile_edit'),
    path('profiles/<int:pk>/delete/', views.VDIBillingProfileDeleteView.as_view(), name='vdibillingprofile_delete'),

    # ── Zuordnungen ───────────────────────────────────────────────────────────
    path('assignments/', views.VDIAssignmentListView.as_view(), name='vdiassignment_list'),
    path('assignments/add/', views.VDIAssignmentEditView.as_view(), name='vdiassignment_add'),
    path('assignments/<int:pk>/', views.VDIAssignmentView.as_view(), name='vdiassignment'),
    path('assignments/<int:pk>/edit/', views.VDIAssignmentEditView.as_view(), name='vdiassignment_edit'),
    path('assignments/<int:pk>/delete/', views.VDIAssignmentDeleteView.as_view(), name='vdiassignment_delete'),
]
