"""
permissions.py
──────────────
Reusable DRF permission classes built on top of UserActivityAccess.

Usage in any ViewSet or APIView:

    from .permissions import HasActivityAccess, IsAdminOrReadOnly

    class DrugViewSet(viewsets.ModelViewSet):
        permission_classes = [HasActivityAccess]
        required_activity   = 'Pharmacy'
        required_department = 'Medical'
        # viewer  → GET (list, retrieve)
        # editor  → POST, PUT, PATCH
        # manager → DELETE
"""

from rest_framework.permissions import BasePermission
from .models import has_activity_access, get_user_activities


# ─────────────────────────────────────────────
# LEVEL MAP
# Maps HTTP method → minimum required access level
# ─────────────────────────────────────────────

METHOD_LEVEL_MAP = {
    'GET':    'viewer',
    'HEAD':   'viewer',
    'OPTIONS':'viewer',
    'POST':   'editor',
    'PUT':    'editor',
    'PATCH':  'editor',
    'DELETE': 'manager',
}


class HasActivityAccess(BasePermission):
    """
    Checks that the logged-in user has access to the activity
    defined on the ViewSet via:
        required_activity   = 'Pharmacy'
        required_department = 'Medical'

    Access level is derived from the HTTP method:
        GET/HEAD/OPTIONS → viewer
        POST/PUT/PATCH   → editor
        DELETE           → manager

    Superusers always pass.
    Unauthenticated users always fail.
    """
    message = "You do not have permission to perform this action on this activity."

    def has_permission(self, request, view):
        # Must be authenticated
        if not request.user or not request.user.is_authenticated:
            return False

        # Superuser bypasses everything
        if request.user.is_superuser:
            return True

        # Get activity + department from the view class
        activity_name   = getattr(view, 'required_activity',   None)
        department_name = getattr(view, 'required_department',  None)

        if not activity_name or not department_name:
            # If the view forgot to declare these, deny by default
            return False

        required_level = METHOD_LEVEL_MAP.get(request.method, 'manager')

        return has_activity_access(
            request.user,
            activity_name,
            department_name,
            required_level
        )


class HasActivityAccessByKeyword(BasePermission):
    """
    Same idea as HasActivityAccess, but instead of requiring an EXACT
    name match for the activity, it matches by KEYWORD (case-insensitive,
    substring match) against the activity name only — department is ignored.

    This is more forgiving: it works no matter what you actually named
    the activity/department in the admin panel, as long as the activity
    name contains one of the configured keywords (e.g. 'صيدل', 'pharma').

    Usage on a ViewSet:
        permission_classes = [HasActivityAccessByKeyword]
        activity_keywords  = ['pharma', 'صيدل', 'drug', 'دواء', 'medicine']

    Superusers always pass.
    """
    message = "You do not have permission to perform this action on this activity."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        keywords = getattr(view, 'activity_keywords', None)
        if not keywords:
            return False

        required_level = METHOD_LEVEL_MAP.get(request.method, 'manager')
        LEVEL_RANK = {'viewer': 1, 'editor': 2, 'manager': 3}
        required_rank = LEVEL_RANK.get(required_level, 1)

        accesses = get_user_activities(request.user)
        for access in accesses:
            name = (access.activity.name or '').lower()
            if any(kw.lower() in name for kw in keywords):
                if LEVEL_RANK.get(access.access_level, 0) >= required_rank:
                    return True
        return False


class IsAdminOnly(BasePermission):
    """
    Only the superuser can access this endpoint.
    Used for: departments, activities, members management.
    """
    message = "Only the system administrator can access this resource."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


class IsAuthenticatedAnyActivity(BasePermission):
    """
    Any logged-in user can access this — regardless of which activity they belong to.
    Used for: dashboard, shared resources like persons list.
    But write operations (POST/PUT/DELETE) are still restricted to superuser.
    """
    message = "You must be logged in to access this resource."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Read → any authenticated user
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True

        # Write → superuser only
        return request.user.is_superuser