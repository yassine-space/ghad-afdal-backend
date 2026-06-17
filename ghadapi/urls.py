from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    # Auth
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
)

router = DefaultRouter()
router.register(r'persons',       PersonViewSet)
router.register(r'departments',   DepartmentViewSet)
router.register(r'activities',    ActivityViewSet)
router.register(r'members',       MemberViewSet)
router.register(r'users',         UserViewSet,             basename='users')
router.register(r'drugs',         DrugViewSet)
router.register(r'stocks',        DrugStockViewSet,        basename='drugstock')
router.register(r'donations',     DrugDonationViewSet)
router.register(r'distributions', DrugDistributionViewSet)

urlpatterns = [
    # ── Router endpoints ──────────────────────────────────────────────────────
    path('', include(router.urls)),

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
]