"""Shared DRF permission classes used across apps.

Centralizing role checks here means the 'admin can see everything, everyone
else only their own data' rule is defined once instead of being copy-pasted
(and sometimes forgotten) in every view.
"""
from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Allows access only to users with role == 'admin'."""

    message = 'Admin privileges required.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'admin')


class IsOwnerOrAdmin(BasePermission):
    """Object-level permission: owner of the object (via `.user`) or an admin."""

    message = 'You do not have permission to access this resource.'

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True
        owner = getattr(obj, 'user', None)
        return owner is not None and owner_id_matches(owner, request.user)


def owner_id_matches(owner, user):
    return owner.pk == user.pk
