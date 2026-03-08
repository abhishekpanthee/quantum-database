"""
Core Authorization Models
~~~~~~~~~~~~~~~~~~~~~~~~~~
User, Role, Resource, and ACL data structures shared by RBAC and ABAC engines.
"""

import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from .._standards import LockoutStatus, Permission, ResourceType


class User:
    """Represents an authenticated principal in the system."""

    def __init__(self, user_id: str, username: str) -> None:
        self.user_id = user_id
        self.username = username
        self.password_hash: Optional[str] = None
        self.roles: Set[str] = set()
        self.direct_permissions: Dict[str, Set[Permission]] = {}
        self.attributes: Dict[str, Any] = {}
        self.last_login: Optional[float] = None
        self.failed_logins: int = 0
        self.lockout_until: Optional[float] = None
        self.status: LockoutStatus = LockoutStatus.ACTIVE
        self.created_at: float = time.time()
        self.mfa_enabled: bool = False
        self.oauth_identities: Dict[str, str] = {}  # provider_id → ext id

    # -- role helpers -------------------------------------------------------

    def add_role(self, role_id: str) -> None:
        self.roles.add(role_id)

    def remove_role(self, role_id: str) -> None:
        self.roles.discard(role_id)

    # -- permission helpers -------------------------------------------------

    def grant_permission(self, resource_id: str, perm: Permission) -> None:
        self.direct_permissions.setdefault(resource_id, set()).add(perm)

    def revoke_permission(self, resource_id: str, perm: Permission) -> None:
        if resource_id in self.direct_permissions:
            self.direct_permissions[resource_id].discard(perm)
            if not self.direct_permissions[resource_id]:
                del self.direct_permissions[resource_id]

    # -- login tracking -----------------------------------------------------

    def record_login(self, success: bool) -> None:
        if success:
            self.last_login = time.time()
            self.failed_logins = 0
            self.lockout_until = None
            self.status = LockoutStatus.ACTIVE
        else:
            self.failed_logins += 1

    def is_locked(self) -> bool:
        if self.status == LockoutStatus.DISABLED:
            return True
        if self.status == LockoutStatus.LOCKED:
            if self.lockout_until and time.time() > self.lockout_until:
                self.status = LockoutStatus.ACTIVE
                self.lockout_until = None
                self.failed_logins = 0
                return False
            return True
        return False

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "roles": list(self.roles),
            "direct_permissions": {
                rid: [p.name for p in perms]
                for rid, perms in self.direct_permissions.items()
            },
            "attributes": self.attributes,
            "last_login": self.last_login,
            "failed_logins": self.failed_logins,
            "status": self.status.name,
            "created_at": self.created_at,
            "mfa_enabled": self.mfa_enabled,
        }


class Role:
    """Named collection of permissions with optional hierarchy."""

    def __init__(self, role_id: str, name: str, description: str = "") -> None:
        self.role_id = role_id
        self.name = name
        self.description = description
        self.permissions: Dict[str, Set[Permission]] = {}
        self.parent_roles: Set[str] = set()
        self.wildcard_grants: List[Tuple[str, Set[Permission]]] = []

    def grant_permission(self, resource_id: str, perm: Permission) -> None:
        self.permissions.setdefault(resource_id, set()).add(perm)

    def revoke_permission(self, resource_id: str, perm: Permission) -> None:
        if resource_id in self.permissions:
            self.permissions[resource_id].discard(perm)
            if not self.permissions[resource_id]:
                del self.permissions[resource_id]

    def grant_wildcard(self, pattern: str, perms: Set[Permission]) -> None:
        """Grant permissions on all resources matching *pattern* (regex)."""
        self.wildcard_grants.append((pattern, perms))

    def add_parent_role(self, parent_role_id: str) -> None:
        self.parent_roles.add(parent_role_id)

    def remove_parent_role(self, parent_role_id: str) -> None:
        self.parent_roles.discard(parent_role_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "name": self.name,
            "description": self.description,
            "permissions": {
                rid: [p.name for p in perms]
                for rid, perms in self.permissions.items()
            },
            "parent_roles": list(self.parent_roles),
            "wildcard_grants": [
                {"pattern": pat, "permissions": [p.name for p in perms]}
                for pat, perms in self.wildcard_grants
            ],
        }


class Resource:
    """A named, typed, ownable entity whose access is controlled."""

    def __init__(
        self,
        resource_id: str,
        name: str,
        type_: ResourceType,
        owner_id: str,
    ) -> None:
        self.resource_id = resource_id
        self.name = name
        self.type = type_
        self.owner_id = owner_id
        self.attributes: Dict[str, Any] = {}
        self.parent_resource_id: Optional[str] = None
        # RLS and column-mask lists are populated by the manager
        self.rls_policies: list = []
        self.column_masks: Dict[str, Any] = {}

    def set_parent(self, parent_resource_id: str) -> None:
        self.parent_resource_id = parent_resource_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "name": self.name,
            "type": self.type.name,
            "owner_id": self.owner_id,
            "attributes": self.attributes,
            "parent_resource_id": self.parent_resource_id,
        }


class AccessControlList:
    """Simple resource → principal → permissions mapping."""

    def __init__(self) -> None:
        self.entries: Dict[str, Dict[str, Set[Permission]]] = {}

    def grant(
        self, resource_id: str, principal_id: str, perm: Permission
    ) -> None:
        self.entries.setdefault(resource_id, {}).setdefault(
            principal_id, set()
        ).add(perm)

    def revoke(
        self, resource_id: str, principal_id: str, perm: Permission
    ) -> None:
        bucket = self.entries.get(resource_id, {})
        s = bucket.get(principal_id)
        if s:
            s.discard(perm)
            if not s:
                del bucket[principal_id]
            if not bucket:
                self.entries.pop(resource_id, None)

    def get_permissions(
        self, resource_id: str, principal_id: str
    ) -> Set[Permission]:
        return set(
            self.entries.get(resource_id, {}).get(principal_id, set())
        )

    def has_permission(
        self, resource_id: str, principal_id: str, perm: Permission
    ) -> bool:
        return perm in self.get_permissions(resource_id, principal_id)

    def get_principals_with_permission(
        self, resource_id: str, perm: Permission
    ) -> Set[str]:
        result: Set[str] = set()
        for pid, perms in self.entries.get(resource_id, {}).items():
            if perm in perms:
                result.add(pid)
        return result
