from django.urls import path
from . import views

urlpatterns = [

    # ── Chargeback Übersicht ──────────────────────────────────────────────────
    path('', views.ChargebackOverviewView.as_view(), name='chargeback_overview'),
    path('print/<int:cost_center_pk>/', views.ChargebackPrintView.as_view(), name='chargeback_print'),

    # ── Kostenstellen ─────────────────────────────────────────────────────────
    path('cost-centers/', views.CostCenterListView.as_view(), name='costcenter_list'),
    path('cost-centers/add/', views.CostCenterEditView.as_view(), name='costcenter_add'),
    path('cost-centers/<int:pk>/', views.CostCenterView.as_view(), name='costcenter'),
    path('cost-centers/<int:pk>/edit/', views.CostCenterEditView.as_view(), name='costcenter_edit'),
    path('cost-centers/<int:pk>/delete/', views.CostCenterDeleteView.as_view(), name='costcenter_delete'),
    path('cost-centers/<int:pk>/changelog/', views.CostCenterChangeLogView.as_view(), name='costcenter_changelog'),

    # ── Massen-Zuweisung ─────────────────────────────────────────────────────
    path('bulk-assign/', views.BulkAssignCostCenterView.as_view(), name='bulk_assign'),

    # ── Preisprofile ──────────────────────────────────────────────────────────
    path('profiles/', views.VDIBillingProfileListView.as_view(), name='vdibillingprofile_list'),
    path('profiles/add/', views.VDIBillingProfileEditView.as_view(), name='vdibillingprofile_add'),
    path('profiles/<int:pk>/', views.VDIBillingProfileView.as_view(), name='vdibillingprofile'),
    path('profiles/<int:pk>/edit/', views.VDIBillingProfileEditView.as_view(), name='vdibillingprofile_edit'),
    path('profiles/<int:pk>/delete/', views.VDIBillingProfileDeleteView.as_view(), name='vdibillingprofile_delete'),
    path('profiles/<int:pk>/changelog/', views.VDIBillingProfileChangeLogView.as_view(), name='vdibillingprofile_changelog'),

    # ── Zuordnungen ───────────────────────────────────────────────────────────
    path('assignments/', views.VDIAssignmentListView.as_view(), name='vdiassignment_list'),
    path('assignments/add/', views.VDIAssignmentEditView.as_view(), name='vdiassignment_add'),
    path('assignments/<int:pk>/', views.VDIAssignmentView.as_view(), name='vdiassignment'),
    path('assignments/<int:pk>/edit/', views.VDIAssignmentEditView.as_view(), name='vdiassignment_edit'),
    path('assignments/<int:pk>/delete/', views.VDIAssignmentDeleteView.as_view(), name='vdiassignment_delete'),
    path('assignments/<int:pk>/changelog/', views.VDIAssignmentChangeLogView.as_view(), name='vdiassignment_changelog'),
]
