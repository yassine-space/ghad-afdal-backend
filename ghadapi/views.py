from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.utils import timezone
from datetime import timedelta

from django.db.models import Sum

from .models import (
    Person,
    Department,
    Activity,
    Member,
    Drug,
    DrugStock,
    DrugDonation,
    DonationItem,
    DrugDistribution,
    DistributionItem,
    get_user_activities,
)

from .serializers import (
    UserSerializer,
    PersonSerializer,
    DepartmentSerializer,
    ActivitySerializer,
    MemberSerializer,
    DrugSerializer,
    DrugStockSerializer,
    DrugDonationSerializer,
    DrugDistributionSerializer,
)

from .permissions import (
    HasActivityAccess,
    HasActivityAccessByKeyword,
    IsAdminOnly,
    IsAuthenticatedAnyActivity,
)


# ─────────────────────────────────────────────
# AUTH VIEWS  
# ─────────────────────────────────────────────

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends the default JWT login response to include user info
    and their activity accesses — so the frontend knows immediately
    what the user can see after login.
    """
    def validate(self, attrs):
        data  = super().validate(attrs)
        user  = self.user
        data['user'] = UserSerializer(user).data
        return data


class LoginView(TokenObtainPairView):
    """
    POST /api/auth/login/
    Body: { "username": "...", "password": "..." }
    Returns: { "access": "...", "refresh": "...", "user": { ...profile + activities... } }
    """
    serializer_class = CustomTokenObtainPairSerializer


class MeView(APIView):
    """
    GET   /api/auth/me/    → current user profile + linked person details
    PATCH /api/auth/me/    → change own password only (username is admin-only)
    """
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)
        user = (
            User.objects
            .select_related('profile__person')
            .prefetch_related('activity_accesses__activity__department')
            .get(pk=request.user.pk)
        )
        data = UserSerializer(user).data
        try:
            person_obj = user.profile.person if user.profile else None
        except Exception:
            person_obj = None
        if person_obj:
            data['person_detail'] = PersonSerializer(person_obj).data
        else:
            data['person_detail'] = None
        return Response(data)

    def patch(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)
        from .serializers import MeUpdateSerializer
        serializer = MeUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response({'detail': 'تم تغيير كلمة المرور بنجاح.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
# ─────────────────────────────────────────────
# ADMIN-MANAGED VIEWSETS
# Reads are open to any authenticated user (sidebar/members page need them).
# Writes (POST/PUT/PATCH/DELETE) are admin only.
# ─────────────────────────────────────────────

class DepartmentViewSet(viewsets.ModelViewSet):
    """
    GET             /api/departments/  → any authenticated user
    POST/PUT/DELETE /api/departments/  → admin only
    """
    queryset           = Department.objects.all()
    serializer_class   = DepartmentSerializer

    def get_permissions(self):
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return [IsAuthenticatedAnyActivity()]
        return [IsAdminOnly()]


class ActivityViewSet(viewsets.ModelViewSet):
    """
    GET             /api/activities/  → any authenticated user
    POST/PUT/DELETE /api/activities/  → admin only
    """
    queryset           = Activity.objects.select_related('department').all()
    serializer_class   = ActivitySerializer

    def get_permissions(self):
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return [IsAuthenticatedAnyActivity()]
        return [IsAdminOnly()]


class MemberViewSet(viewsets.ModelViewSet):
    """
    GET             /api/members/  → any authenticated user
    POST/PUT/DELETE /api/members/  → admin only
    """
    queryset           = Member.objects.select_related('person', 'department').all()
    serializer_class   = MemberSerializer

    def get_permissions(self):
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return [IsAuthenticatedAnyActivity()]
        return [IsAdminOnly()]


# ─────────────────────────────────────────────
# SHARED RESOURCE — PERSONS
# Any authenticated user can read persons.
# Only admin can create/edit/delete.
# ─────────────────────────────────────────────

class PersonViewSet(viewsets.ModelViewSet):
    """
    GET/POST/PUT/DELETE /api/persons/ → any authenticated user
    (Regular users need full CRUD on persons via PeoplePage)
    """
    queryset           = Person.objects.all()
    serializer_class   = PersonSerializer
    permission_classes = [IsAuthenticated]


# ─────────────────────────────────────────────
# PHARMACY ACTIVITY VIEWSETS
# These require the user to be assigned to the
# 'Pharmacy' activity inside a department.
#
# HOW TO CONFIGURE:
#   required_activity   = exact name of the Activity in your DB
#   required_department = exact name of the Department in your DB
#
# Change these strings to match what you create in the admin panel.
# ─────────────────────────────────────────────

class DrugViewSet(viewsets.ModelViewSet):
    """
    Required: an activity whose NAME contains one of activity_keywords
    (matched case-insensitively, substring match — so it works no matter
    exactly how you named the activity/department in the admin panel).
    GET           → viewer
    POST/PUT/PATCH → editor
    DELETE        → manager
    """
    queryset            = Drug.objects.all()
    serializer_class    = DrugSerializer
    permission_classes  = [HasActivityAccessByKeyword]
    activity_keywords   = ['pharma', 'صيدل', 'drug', 'دواء', 'medicine']

    @action(detail=False, methods=['get'], url_path='expiring_soon')
    def expiring_soon(self, request):
        """
        GET /api/drugs/expiring_soon/?days=30
        Returns stock entries expiring within N days.
        Requires viewer access.
        """
        days    = int(request.query_params.get('days', 30))
        cutoff  = timezone.now().date() + timedelta(days=days)
        stocks  = DrugStock.objects.filter(
            expiration_date__lte=cutoff,
            quantity_available__gt=0,
        ).select_related('drug')
        return Response(DrugStockSerializer(stocks, many=True).data)

    @action(detail=True, methods=['get'], url_path='stock')
    def stock(self, request, pk=None):
        """
        GET /api/drugs/{id}/stock/
        Returns all stock batches for a single drug plus lifetime totals.
        Requires viewer access.
        """
        drug = self.get_object()

        # Current available batches (non-zero only)
        stocks = DrugStock.objects.filter(drug=drug, quantity_available__gt=0)
        available = stocks.aggregate(total=Sum('quantity_available'))['total'] or 0

        # Lifetime total received (all donation items for this drug)
        total_received = (
            DonationItem.objects
            .filter(drug=drug)
            .aggregate(total=Sum('quantity'))['total'] or 0
        )

        # Lifetime total distributed (validated distributions only)
        total_distributed = (
            DistributionItem.objects
            .filter(stock__drug=drug, distribution__is_validated=True)
            .aggregate(total=Sum('quantity'))['total'] or 0
        )

        return Response({
            'drug_id':           drug.id,
            'available':         available,
            'total_received':    total_received,
            'total_distributed': total_distributed,
            'batches':           DrugStockSerializer(stocks, many=True).data,
        })


class DrugStockViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only — stock is managed automatically via signals and validate().
    GET /api/stocks/          → all non-zero stock entries
    GET /api/stocks/?drug=5   → filter by drug id
    Requires viewer access on a pharmacy-keyword activity.
    """
    serializer_class    = DrugStockSerializer
    permission_classes  = [HasActivityAccessByKeyword]
    activity_keywords   = ['pharma', 'صيدل', 'drug', 'دواء', 'medicine']

    def get_queryset(self):
        qs = DrugStock.objects.select_related('drug').filter(quantity_available__gt=0)
        drug_id = self.request.query_params.get('drug')
        if drug_id:
            qs = qs.filter(drug_id=drug_id)
        return qs


class DrugDonationViewSet(viewsets.ModelViewSet):
    """
    GET           → viewer on pharmacy-keyword activity
    POST/PUT/PATCH → editor on pharmacy-keyword activity
    DELETE        → manager on pharmacy-keyword activity
    """
    queryset            = DrugDonation.objects.prefetch_related('items__drug').all()
    serializer_class    = DrugDonationSerializer
    permission_classes  = [HasActivityAccessByKeyword]
    activity_keywords   = ['pharma', 'صيدل', 'drug', 'دواء', 'medicine']


class DrugDistributionViewSet(viewsets.ModelViewSet):
    """
    GET            → viewer on pharmacy-keyword activity
    POST/PUT/PATCH  → editor on pharmacy-keyword activity
    DELETE         → manager on pharmacy-keyword activity
    validate action → editor on pharmacy-keyword activity (explicit check inside)
    """
    queryset = DrugDistribution.objects.prefetch_related(
        'items__stock__drug'
    ).select_related('beneficiary').all()
    serializer_class    = DrugDistributionSerializer
    permission_classes  = [HasActivityAccessByKeyword]
    activity_keywords   = ['pharma', 'صيدل', 'drug', 'دواء', 'medicine']

    @action(detail=True, methods=['post'], url_path='validate')
    def validate_distribution(self, request, pk=None):
        """
        POST /api/distributions/{id}/validate/
        Validates the distribution and deducts stock atomically.
        Requires at least editor access.
        """
        # Extra explicit check for this sensitive action
        if not request.user.is_superuser:
            from .models import get_user_activities
            LEVEL_RANK = {'viewer': 1, 'editor': 2, 'manager': 3}
            accesses = get_user_activities(request.user)
            has_editor = any(
                any(kw.lower() in (a.activity.name or '').lower() for kw in self.activity_keywords)
                and LEVEL_RANK.get(a.access_level, 0) >= LEVEL_RANK['editor']
                for a in accesses
            )
            if not has_editor:
                return Response(
                    {'detail': 'You need editor access to validate distributions.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        distribution = self.get_object()
        try:
            distribution.validate()
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(DrugDistributionSerializer(distribution).data)


# ─────────────────────────────────────────────
# DASHBOARD
# Any authenticated user sees it.
# Numbers are scoped to what the user can access.
# ─────────────────────────────────────────────

class DashboardView(APIView):
    """
    GET /api/dashboard/
    Returns counts. Superuser sees everything.
    Regular users see counts scoped to their assigned activities.
    """
    permission_classes = [IsAuthenticatedAnyActivity]

    def get(self, request):
        user = request.user

        if user.is_superuser:
            # Admin sees global totals
            data = {
                'persons':        Person.objects.count(),
                'departments':    Department.objects.count(),
                'drugs':          Drug.objects.count(),
                'donations':      DrugDonation.objects.count(),
                'distributions':  DrugDistribution.objects.count(),
                'stock_entries':  DrugStock.objects.filter(quantity_available__gt=0).count(),
            }
        else:
            # Regular user sees only what their activities cover
            accesses = get_user_activities(user)
            data = {
                'your_activities': [
                    {
                        'activity':   a.activity.name,
                        'department': a.activity.department.name,
                        'level':      a.access_level,
                    }
                    for a in accesses
                ],
                'persons':       Person.objects.count(),
                'stock_entries': DrugStock.objects.filter(quantity_available__gt=0).count(),
            }

        return Response(data)


class ExpiringDrugsView(APIView):
    """
    GET /api/drugs/expiring/?days=30
    Requires viewer access on Pharmacy activity.
    """
    permission_classes = [IsAuthenticatedAnyActivity]

    def get(self, request):
        days   = int(request.query_params.get('days', 30))
        cutoff = timezone.now().date() + timedelta(days=days)
        stocks = DrugStock.objects.filter(
            expiration_date__lte=cutoff,
            quantity_available__gt=0,
        ).select_related('drug')
        return Response(DrugStockSerializer(stocks, many=True).data)

# ─────────────────────────────────────────────
# USER MANAGEMENT (superuser only)
# ─────────────────────────────────────────────

from .models import User, UserProfile, UserActivityAccess
from .serializers import UserCreateSerializer, UserUpdateSerializer

class UserViewSet(viewsets.ModelViewSet):
    """
    Full user CRUD for superuser.
    GET    /api/users/          → list all users with their accesses
    POST   /api/users/          → create user
    GET    /api/users/{id}/     → retrieve one user
    PUT    /api/users/{id}/     → update user (password optional)
    DELETE /api/users/{id}/     → delete user
    POST   /api/users/{id}/set_person/    → link user to a Person
    POST   /api/users/{id}/set_access/    → add/update an activity access
    DELETE /api/users/{id}/remove_access/ → remove an activity access
    """
    permission_classes = [IsAdminOnly]

    def get_queryset(self):
        return User.objects.exclude(is_superuser=True).prefetch_related(
            'activity_accesses__activity__department',
            'profile__person',
        ).order_by('username')

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        if self.action in ('update', 'partial_update'):
            return UserUpdateSerializer
        return UserSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return Response(UserSerializer(instance).data)

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        return Response(UserSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'], url_path='set_person')
    def set_person(self, request, pk=None):
        """Link or unlink a Person to this user account."""
        user = self.get_object()
        person_id = request.data.get('person_id')  # pass null to unlink
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if person_id:
            try:
                from .models import Person
                person = Person.objects.get(id=person_id)
                existing = UserProfile.objects.filter(person=person).exclude(user=user).first()
                if existing:
                    return Response(
                        {'detail': f'هذا الشخص مرتبط بالفعل بالمستخدم {existing.user.username}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                profile.person = person
            except Person.DoesNotExist:
                return Response({'detail': 'الشخص غير موجود'}, status=status.HTTP_404_NOT_FOUND)
        else:
            profile.person = None
        profile.save()
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=['post'], url_path='set_access')
    def set_access(self, request, pk=None):
        """Add or update an activity access for this user."""
        user = self.get_object()
        activity_id  = request.data.get('activity_id')
        access_level = request.data.get('access_level', 'viewer')
        if not activity_id:
            return Response({'detail': 'activity_id مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            activity = Activity.objects.get(id=activity_id)
        except Activity.DoesNotExist:
            return Response({'detail': 'النشاط غير موجود'}, status=status.HTTP_404_NOT_FOUND)
        access, created = UserActivityAccess.objects.update_or_create(
            user=user, activity=activity,
            defaults={'access_level': access_level}
        )
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=['delete'], url_path='remove_access/(?P<access_id>[^/.]+)')
    def remove_access(self, request, pk=None, access_id=None):
        """Remove a specific activity access row."""
        user = self.get_object()
        try:
            access = UserActivityAccess.objects.get(id=access_id, user=user)
            access.delete()
        except UserActivityAccess.DoesNotExist:
            return Response({'detail': 'الصلاحية غير موجودة'}, status=status.HTTP_404_NOT_FOUND)
        return Response(UserSerializer(user).data)