from django import views
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    # Auth
    BloodDonationDashboardView,
    CertificateView,
    CompatibleDonorsView,
    DonateBloodView,
    LoginView,
    MeView,
    # Admin-managed
    DepartmentViewSet,
    ActivityViewSet,
    MemberViewSet,
    UserViewSet,
    # Shared
    PersonViewSet,
    # Pharmacy activity
    DrugViewSet,
    DrugStockViewSet,
    DrugDonationViewSet,
    DrugDistributionViewSet,
    # Standalone
    DashboardView,
    ExpiringDrugsView,
    DonorViewSet,
    PatientViewSet,
    DonationHistoryViewSet,
    MachineViewSet,
    MachineAssignmentViewSet,
    FinancialCategoryViewSet,
    DonationViewSet, 
    ExpenseTransactionViewSet,
    FinancialDashboardView, 
    FinancialReportView, 
    FinancialAuditLogViewSet,
    DonationReceiptView,
    ExpenseReceiptView,
    WarmWinterDonationViewSet,    

)

router = DefaultRouter()
router.register(r'donors', DonorViewSet, basename='donor')
router.register(r'patients', PatientViewSet, basename='patient')
router.register(r'donation-history', DonationHistoryViewSet, basename='donationhistory')  
router.register(r'persons',       PersonViewSet)
router.register(r'departments',   DepartmentViewSet)
router.register(r'activities',    ActivityViewSet)
router.register(r'members',       MemberViewSet)
router.register(r'users',         UserViewSet,             basename='users')
router.register(r'drugs',         DrugViewSet)
router.register(r'stocks',        DrugStockViewSet,        basename='drugstock')
router.register(r'donations',     DrugDonationViewSet)
router.register(r'distributions', DrugDistributionViewSet)
router.register(r'machines',            MachineViewSet,           basename='machine')
router.register(r'machine-assignments', MachineAssignmentViewSet, basename='machine-assignment')
router.register(r'finance/categories', FinancialCategoryViewSet, basename='finance-category')
router.register(r'finance/donations', DonationViewSet, basename='donation')
router.register(r'finance/expenses', ExpenseTransactionViewSet, basename='expense')
router.register(r'finance/audit-log', FinancialAuditLogViewSet, basename='finance-audit-log')
router.register(r'warm-winter', WarmWinterDonationViewSet, basename='warm-winter')
urlpatterns = [
    

    # ── Auth endpoints ────────────────────────────────────────────────────────
    # POST /api/auth/login/    → returns access + refresh tokens + user info
    # POST /api/auth/refresh/  → exchange refresh token for new access token
    # GET  /api/auth/me/       → current user profile + activity accesses
    path('auth/login/',   LoginView.as_view(),        name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(),  name='token-refresh'),
    path('auth/me/',      MeView.as_view(),            name='me'),

    # ── Convenience endpoints ─────────────────────────────────────────────────
    path('dashboard/',      DashboardView.as_view(),    name='dashboard'),
    path('drugs/expiring/', ExpiringDrugsView.as_view(), name='expiring-drugs'),
    # ── Endpoints for donor/patient management ───────────────────────────────
    path('donate/<int:id_patient>/<int:id_donor>/', DonateBloodView.as_view(), name='donate-blood'),
    path('patients/with-compatible-donors/', CompatibleDonorsView.as_view(), name='patients-with-donors'),
    path('certificate/<int:patient_id>/<int:donor_id>/', CertificateView.as_view(), name='certificate'),
    path('dashboard/stats/', BloodDonationDashboardView.as_view(), name='dashboard-stats'),
    # ── machine endpoints ──────────────────────────────────────────────────────
    path('finance/dashboard/', FinancialDashboardView.as_view(), name='finance-dashboard'),
    path('finance/reports/', FinancialReportView.as_view(), name='finance-reports'),
    path('finance/donations/<int:pk>/receipt/', DonationReceiptView.as_view(), name='donation-receipt'),
    path('finance/expenses/<int:pk>/receipt/', ExpenseReceiptView.as_view(), name='expense-receipt'),
    # ── Router endpoints ──────────────────────────────────────────────────────
    path('', include(router.urls)),

    # public endpoints
]

