"""
RBAC Engine — AccessControlManager
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Central orchestrator for authentication, authorization, session management,
and account lifecycle.  Composes the auth and ABAC subsystems.
"""

import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Union

from .._standards import (
    AccessDeniedException,
    AccountLockedException,
    AuthenticationException,
    LockoutStatus,
    Permission,
    ResourceType,
    QUERY_PERMISSION_MAP,
    MAX_FAILED_ATTEMPTS,
    LOCKOUT_DURATION_SECONDS,
)
from ..auth.password import PasswordHasher
from ..auth.jwt_manager import JWTManager
from ..auth.oauth import OIDCManager
from .abac import ABACEngine
from .models import AccessControlList, Resource, Role, User
from .rls import ColumnMask, RLSPolicy, apply_column_masks, filter_rows

logger = logging.getLogger(__name__)

_password_hasher = PasswordHasher()


class AccessControlManager:
    """Production-grade access-control manager.

    Combines:
    * **Password authentication** (scrypt / bcrypt / argon2)
    * **JWT session management** (access + refresh tokens)
    * **OAuth2 / OIDC** enterprise SSO
    * **RBAC** with role hierarchy, wildcard grants
    * **ABAC** policy engine
    * **Row-Level Security** and **column masking**
    * **Account lockout** after *N* failed attempts
    """

    def __init__(
        self,
        *,
        max_failed_attempts: int = MAX_FAILED_ATTEMPTS,
        lockout_duration_seconds: int = LOCKOUT_DURATION_SECONDS,
    ) -> None:
        self.users: Dict[str, User] = {}
        self.roles: Dict[str, Role] = {}
        self.resources: Dict[str, Resource] = {}
        self.acl = AccessControlList()

        # Sub-systems
        self.jwt = JWTManager()
        self.oidc = OIDCManager()
        self.abac = ABACEngine()
        self._hasher = _password_hasher

        # Lockout config
        self._max_failed = max_failed_attempts
        self._lockout_duration = lockout_duration_seconds

        # Bootstrap
        self._init_system_roles()
        self._init_system_resources()

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def _init_system_roles(self) -> None:
        self.create_role("admin", "Administrator", "Full system access")
        self.create_role("reader", "Reader", "Read-only access")
        self.create_role("writer", "Writer", "Read and write access")
        if "admin" not in self.users:
            self.create_user("admin", "admin")
            self.assign_role("admin", "admin")

    def _init_system_resources(self) -> None:
        if "system" not in self.resources:
            self.create_resource(
                "system", "System", ResourceType.SYSTEM, "admin"
            )

    # ------------------------------------------------------------------
    # User management
    # ------------------------------------------------------------------

    def create_user(
        self, username: str, user_id: Optional[str] = None
    ) -> str:
        if user_id is None:
            user_id = str(uuid.uuid4())
        if user_id in self.users:
            raise ValueError(f"User with ID {user_id} already exists")
        user = User(user_id, username)
        self.users[user_id] = user
        self.create_resource(
            f"user:{user_id}",
            f"User {username}",
            ResourceType.USER,
            user_id,
        )
        return user_id

    def set_user_password(self, user_id: str, password: str) -> None:
        if user_id not in self.users:
            raise ValueError(f"User {user_id} does not exist")
        self.users[user_id].password_hash = self._hasher.hash(password)
        self.users[user_id].attributes["password_updated_at"] = time.time()

    def get_user_by_username(self, username: str) -> Optional[User]:
        for u in self.users.values():
            if u.username == username:
                return u
        return self.users.get(username)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(
        self, credentials: Union[str, Dict[str, Any]]
    ) -> Optional[User]:
        if isinstance(credentials, dict):
            username = credentials.get("username", "")
            password = credentials.get("password")
        else:
            username = credentials
            password = None

        user = self.get_user_by_username(username)
        if user is None:
            logger.warning("Auth failed — unknown user: %s", username)
            return None

        if user.is_locked():
            raise AccountLockedException(
                f"Account {username} is locked"
            )

        if password is not None and user.password_hash is not None:
            if not self._hasher.verify(password, user.password_hash):
                user.record_login(False)
                self._maybe_lock(user)
                logger.warning("Auth failed — bad password: %s", username)
                return None

        user.record_login(True)
        return user

    def authenticate_and_issue_token(
        self, credentials: Dict[str, Any]
    ) -> Dict[str, str]:
        """Authenticate and return JWT access + refresh tokens."""
        user = self.authenticate(credentials)
        if user is None:
            raise AuthenticationException("Invalid credentials")
        claims = {
            "sub": user.user_id,
            "username": user.username,
            "roles": list(user.roles),
        }
        access = self.jwt.create_token(claims)
        refresh = self.jwt.create_refresh_token(claims)
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "Bearer",
        }

    def validate_session(self, token: str) -> Dict[str, Any]:
        return self.jwt.verify_token(token)

    def logout(self, token: str) -> None:
        self.jwt.revoke_token(token)

    # ------------------------------------------------------------------
    # Account lockout
    # ------------------------------------------------------------------

    def _maybe_lock(self, user: User) -> None:
        if user.failed_logins >= self._max_failed:
            user.status = LockoutStatus.LOCKED
            user.lockout_until = time.time() + self._lockout_duration
            logger.warning(
                "Account locked: %s (failed=%d)",
                user.username,
                user.failed_logins,
            )

    def unlock_account(self, user_id: str) -> None:
        if user_id in self.users:
            u = self.users[user_id]
            u.status = LockoutStatus.ACTIVE
            u.failed_logins = 0
            u.lockout_until = None

    def disable_account(self, user_id: str) -> None:
        if user_id in self.users:
            self.users[user_id].status = LockoutStatus.DISABLED

    # ------------------------------------------------------------------
    # Role / permission management
    # ------------------------------------------------------------------

    def create_role(
        self, role_id: str, name: str, description: str = ""
    ) -> Role:
        if role_id in self.roles:
            raise ValueError(f"Role {role_id} already exists")
        role = Role(role_id, name, description)
        self.roles[role_id] = role
        return role

    def create_resource(
        self,
        resource_id: str,
        name: str,
        resource_type: ResourceType,
        owner_id: str,
    ) -> Resource:
        if resource_id in self.resources:
            raise ValueError(f"Resource {resource_id} already exists")
        resource = Resource(resource_id, name, resource_type, owner_id)
        self.resources[resource_id] = resource
        self.grant_permission(owner_id, resource_id, Permission.ADMIN)
        return resource

    def assign_role(self, user_id: str, role_id: str) -> None:
        if user_id not in self.users:
            raise ValueError(f"User {user_id} does not exist")
        if role_id not in self.roles:
            raise ValueError(f"Role {role_id} does not exist")
        self.users[user_id].add_role(role_id)

    def revoke_role(self, user_id: str, role_id: str) -> None:
        if user_id not in self.users:
            raise ValueError(f"User {user_id} does not exist")
        self.users[user_id].remove_role(role_id)

    def grant_permission(
        self, principal_id: str, resource_id: str, permission: Permission
    ) -> None:
        if resource_id not in self.resources:
            raise ValueError(f"Resource {resource_id} does not exist")
        if principal_id in self.users:
            self.users[principal_id].grant_permission(resource_id, permission)
        elif principal_id in self.roles:
            self.roles[principal_id].grant_permission(resource_id, permission)
        else:
            raise ValueError(f"Principal {principal_id} does not exist")
        self.acl.grant(resource_id, principal_id, permission)

    def revoke_permission(
        self, principal_id: str, resource_id: str, permission: Permission
    ) -> None:
        if principal_id in self.users:
            self.users[principal_id].revoke_permission(resource_id, permission)
        elif principal_id in self.roles:
            self.roles[principal_id].revoke_permission(resource_id, permission)
        self.acl.revoke(resource_id, principal_id, permission)

    def grant_wildcard(
        self, role_id: str, pattern: str, perms: Set[Permission]
    ) -> None:
        if role_id not in self.roles:
            raise ValueError(f"Role {role_id} does not exist")
        self.roles[role_id].grant_wildcard(pattern, perms)

    # ------------------------------------------------------------------
    # Permission checking (RBAC + ABAC + wildcards)
    # ------------------------------------------------------------------

    def check_permission(
        self, user_id: str, resource_id: str, permission: Permission
    ) -> bool:
        if user_id not in self.users:
            return False
        user = self.users[user_id]

        # Admin bypass
        if "admin" in user.roles:
            return True

        # 1) ABAC
        resource = self.resources.get(resource_id)
        abac_ctx = {
            "user_id": user_id,
            "username": user.username,
            "resource_id": resource_id,
            "resource_type": resource.type.name if resource else None,
            "permission": permission.name,
            "time": time.time(),
            **user.attributes,
        }
        abac_result = self.abac.evaluate(abac_ctx)
        if abac_result is False:
            return False
        if abac_result is True:
            return True

        # 2) Direct user permissions
        if resource_id in user.direct_permissions:
            if permission in user.direct_permissions[resource_id]:
                return True

        # 3) Role hierarchy + wildcards
        for role_id in user.roles:
            if self._check_role_hierarchy_permission(
                role_id, resource_id, permission, set()
            ):
                return True

        # 4) Resource hierarchy
        if resource and resource.parent_resource_id:
            return self.check_permission(
                user_id, resource.parent_resource_id, permission
            )

        return False

    def _check_role_hierarchy_permission(
        self,
        role_id: str,
        resource_id: str,
        perm: Permission,
        visited: Set[str],
    ) -> bool:
        if role_id in visited:
            return False
        visited.add(role_id)
        role = self.roles.get(role_id)
        if role is None:
            return False

        # Direct
        if resource_id in role.permissions:
            if perm in role.permissions[resource_id]:
                return True

        # Wildcard
        for pattern, perms in role.wildcard_grants:
            if perm in perms and re.match(pattern, resource_id):
                return True

        # Parents
        for pid in role.parent_roles:
            if self._check_role_hierarchy_permission(
                pid, resource_id, perm, visited
            ):
                return True
        return False

    def enforce_permission(
        self, user_id: str, resource_id: str, permission: Permission
    ) -> None:
        if not self.check_permission(user_id, resource_id, permission):
            raise AccessDeniedException(
                f"User {user_id} lacks {permission.name} on {resource_id}"
            )

    def get_accessible_resources(
        self, user_id: str, permission: Permission
    ) -> List[Resource]:
        return [
            r
            for r in self.resources.values()
            if self.check_permission(user_id, r.resource_id, permission)
        ]

    # ------------------------------------------------------------------
    # Row-Level Security
    # ------------------------------------------------------------------

    def add_rls_policy(
        self, resource_id: str, policy: RLSPolicy
    ) -> None:
        if resource_id not in self.resources:
            raise ValueError(f"Resource {resource_id} does not exist")
        self.resources[resource_id].rls_policies.append(policy)

    def filter_rows(
        self,
        resource_id: str,
        user_id: str,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        resource = self.resources.get(resource_id)
        if resource is None or not resource.rls_policies:
            return rows
        user = self.users.get(user_id)
        if user is None:
            return []
        return filter_rows(resource.rls_policies, user, rows)

    # ------------------------------------------------------------------
    # Column masking
    # ------------------------------------------------------------------

    def add_column_mask(
        self, resource_id: str, mask: ColumnMask
    ) -> None:
        if resource_id not in self.resources:
            raise ValueError(f"Resource {resource_id} does not exist")
        self.resources[resource_id].column_masks[mask.column_name] = mask

    def apply_column_masks(
        self,
        resource_id: str,
        user_id: str,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        resource = self.resources.get(resource_id)
        if resource is None or not resource.column_masks:
            return rows
        user = self.users.get(user_id)
        if user is None:
            return rows
        return apply_column_masks(resource.column_masks, user, rows)

    # ------------------------------------------------------------------
    # Query authorization (legacy compat)
    # ------------------------------------------------------------------

    def authorize_query(self, query: Any, user_id: Any) -> bool:
        logger.info("Authorizing query for user ID: %s", user_id)
        if hasattr(user_id, "user_id"):
            user_id = user_id.user_id
        if user_id in self.users and "admin" in self.users[user_id].roles:
            return True
        qd = query.to_dict() if hasattr(query, "to_dict") else query
        try:
            target = qd.get("target_table")
            if target:
                req = self._get_required_permission(qd["query_type"])
                if not self.check_permission(user_id, target, req):
                    return False
            if qd.get("query_type", "").startswith("QUANTUM_"):
                if not self._has_quantum_privileges(user_id):
                    return False
                if not self._check_quantum_resource_quota(
                    user_id, qd.get("quantum_clauses", [])
                ):
                    return False
            return True
        except Exception as exc:
            logger.error("Authorization error: %s", exc)
            return False

    @staticmethod
    def _get_required_permission(query_type: str) -> Permission:
        return QUERY_PERMISSION_MAP.get(
            query_type.upper(), Permission.EXECUTE
        )

    def _has_quantum_privileges(self, user_id: str) -> bool:
        return (
            user_id in self.users
            and "admin" in self.users[user_id].roles
        )

    def _check_quantum_resource_quota(
        self, user_id: str, quantum_clauses: List
    ) -> bool:
        if user_id in self.users and "admin" in self.users[user_id].roles:
            return True
        return True

    # ------------------------------------------------------------------
    # Debug / export
    # ------------------------------------------------------------------

    def debug_user_permissions(self, user_id: str) -> None:
        if user_id not in self.users:
            print(f"User {user_id} not found")
            return
        user = self.users[user_id]
        print(f"\n=== Permission Debug for {user_id} ({user.username}) ===")
        print(
            "Direct:",
            {
                r: [p.name for p in ps]
                for r, ps in user.direct_permissions.items()
            },
        )
        print("Roles:", user.roles)
        for rid in user.roles:
            role = self.roles.get(rid)
            if role:
                print(f"  Role {rid}: {role.permissions}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "users": {uid: u.to_dict() for uid, u in self.users.items()},
            "roles": {rid: r.to_dict() for rid, r in self.roles.items()},
            "resources": {
                rid: r.to_dict() for rid, r in self.resources.items()
            },
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        self.users.clear()
        self.roles.clear()
        self.resources.clear()

        for role_id, rd in data.get("roles", {}).items():
            role = Role(role_id, rd["name"], rd.get("description", ""))
            for pid in rd.get("parent_roles", []):
                role.add_parent_role(pid)
            self.roles[role_id] = role

        for user_id, ud in data.get("users", {}).items():
            user = User(user_id, ud["username"])
            for rid in ud.get("roles", []):
                user.add_role(rid)
            user.attributes = ud.get("attributes", {})
            user.last_login = ud.get("last_login")
            user.failed_logins = ud.get("failed_logins", 0)
            self.users[user_id] = user

        for res_id, rd in data.get("resources", {}).items():
            res = Resource(
                res_id,
                rd["name"],
                ResourceType.from_string(rd["type"]),
                rd["owner_id"],
            )
            res.attributes = rd.get("attributes", {})
            res.parent_resource_id = rd.get("parent_resource_id")
            self.resources[res_id] = res

        for role_id, rd in data.get("roles", {}).items():
            for res_id, pnames in rd.get("permissions", {}).items():
                for pn in pnames:
                    self.grant_permission(
                        role_id, res_id, Permission.from_string(pn)
                    )

        for user_id, ud in data.get("users", {}).items():
            for res_id, pnames in ud.get("direct_permissions", {}).items():
                for pn in pnames:
                    self.grant_permission(
                        user_id, res_id, Permission.from_string(pn)
                    )
