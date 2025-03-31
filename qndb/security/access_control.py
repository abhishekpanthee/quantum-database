"""
Access Control Module

This module implements permission management and access control
for the quantum database system.
"""

import time
import uuid
import hashlib
import hmac
from typing import Dict, Any, Set, List, Optional, Tuple, Union
import json
from enum import Enum, auto
import logging
logger = logging.getLogger(__name__)

class Permission(Enum):
    """Permissions available in the system."""
    READ = auto()
    WRITE = auto()
    DELETE = auto()
    ADMIN = auto()
    EXECUTE = auto()
    CREATE = auto()
    ALTER = auto()
    DROP = auto()
    
    @classmethod
    def from_string(cls, perm_str: str) -> 'Permission':
        """Convert string to permission enum."""
        return cls[perm_str.upper()]


class ResourceType(Enum):
    """Types of resources that can be protected."""
    TABLE = auto()
    VIEW = auto()
    INDEX = auto()
    FUNCTION = auto()
    PROCEDURE = auto()
    SCHEMA = auto()
    SYSTEM = auto()
    QUERY = auto()
    USER = auto()
    ROLE = auto()
    
    @classmethod
    def from_string(cls, type_str: str) -> 'ResourceType':
        """Convert string to resource type enum."""
        return cls[type_str.upper()]


class AccessDeniedException(Exception):
    """Exception raised when access to a resource is denied."""
    pass


class User:
    """Represents a user in the system."""
    
    def __init__(self, user_id: str, username: str):
        """
        Initialize a user.
        
        Args:
            user_id: Unique identifier for the user
            username: Username for display
        """
        self.user_id = user_id
        self.username = username
        self.roles: Set[str] = set()
        self.direct_permissions: Dict[str, Set[Permission]] = {}  # resource_id -> permissions
        self.attributes: Dict[str, Any] = {}
        self.last_login: Optional[float] = None
        self.failed_logins = 0
    
    def add_role(self, role_id: str) -> None:
        """Add a role to the user."""
        self.roles.add(role_id)
    
    def remove_role(self, role_id: str) -> None:
        """Remove a role from the user."""
        if role_id in self.roles:
            self.roles.remove(role_id)
    
    def grant_permission(self, resource_id: str, permission: Permission) -> None:
        """Grant a permission to the user for a specific resource."""
        if resource_id not in self.direct_permissions:
            self.direct_permissions[resource_id] = set()
        self.direct_permissions[resource_id].add(permission)
    
    def revoke_permission(self, resource_id: str, permission: Permission) -> None:
        """Revoke a permission from the user for a specific resource."""
        if resource_id in self.direct_permissions and permission in self.direct_permissions[resource_id]:
            self.direct_permissions[resource_id].remove(permission)
            if not self.direct_permissions[resource_id]:
                del self.direct_permissions[resource_id]
    
    def record_login(self, success: bool) -> None:
        """Record a login attempt."""
        if success:
            self.last_login = time.time()
            self.failed_logins = 0
        else:
            self.failed_logins += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary representation."""
        return {
            'user_id': self.user_id,
            'username': self.username,
            'roles': list(self.roles),
            'direct_permissions': {
                res_id: [perm.name for perm in perms] 
                for res_id, perms in self.direct_permissions.items()
            },
            'attributes': self.attributes,
            'last_login': self.last_login,
            'failed_logins': self.failed_logins
        }


class Role:
    """Represents a role with specific permissions."""
    
    def __init__(self, role_id: str, name: str, description: str = ""):
        """
        Initialize a role.
        
        Args:
            role_id: Unique identifier for the role
            name: Display name for the role
            description: Optional description
        """
        self.role_id = role_id
        self.name = name
        self.description = description
        self.permissions: Dict[str, Set[Permission]] = {}  # resource_id -> permissions
        self.parent_roles: Set[str] = set()
    
    def grant_permission(self, resource_id: str, permission: Permission) -> None:
        """Grant a permission to the role for a specific resource."""
        if resource_id not in self.permissions:
            self.permissions[resource_id] = set()
        self.permissions[resource_id].add(permission)
    
    def revoke_permission(self, resource_id: str, permission: Permission) -> None:
        """Revoke a permission from the role for a specific resource."""
        if resource_id in self.permissions and permission in self.permissions[resource_id]:
            self.permissions[resource_id].remove(permission)
            if not self.permissions[resource_id]:
                del self.permissions[resource_id]
    
    def add_parent_role(self, parent_role_id: str) -> None:
        """Add a parent role for inheritance."""
        self.parent_roles.add(parent_role_id)
    
    def remove_parent_role(self, parent_role_id: str) -> None:
        """Remove a parent role."""
        if parent_role_id in self.parent_roles:
            self.parent_roles.remove(parent_role_id)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert role to dictionary representation."""
        return {
            'role_id': self.role_id,
            'name': self.name,
            'description': self.description,
            'permissions': {
                res_id: [perm.name for perm in perms] 
                for res_id, perms in self.permissions.items()
            },
            'parent_roles': list(self.parent_roles)
        }


class Resource:
    """Represents a resource in the system."""
    
    def __init__(self, resource_id: str, name: str, type_: ResourceType, owner_id: str):
        """
        Initialize a resource.
        
        Args:
            resource_id: Unique identifier for the resource
            name: Display name for the resource
            type_: Type of resource
            owner_id: ID of the owning user
        """
        self.resource_id = resource_id
        self.name = name
        self.type = type_
        self.owner_id = owner_id
        self.attributes: Dict[str, Any] = {}
        self.parent_resource_id: Optional[str] = None
    
    def set_parent(self, parent_resource_id: str) -> None:
        """Set the parent resource for inheritance."""
        self.parent_resource_id = parent_resource_id
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert resource to dictionary representation."""
        return {
            'resource_id': self.resource_id,
            'name': self.name,
            'type': self.type.name,
            'owner_id': self.owner_id,
            'attributes': self.attributes,
            'parent_resource_id': self.parent_resource_id
        }


class AccessControlList:
    """Manages permissions for resources."""
    
    def __init__(self):
        """Initialize the access control list."""
        self.entries: Dict[str, Dict[str, Set[Permission]]] = {}  # resource_id -> {user_or_role_id -> permissions}
    
    def grant(self, resource_id: str, principal_id: str, permission: Permission) -> None:
        """
        Grant a permission to a principal (user or role) for a resource.
        
        Args:
            resource_id: ID of the resource
            principal_id: ID of the user or role
            permission: Permission to grant
        """
        if resource_id not in self.entries:
            self.entries[resource_id] = {}
        
        if principal_id not in self.entries[resource_id]:
            self.entries[resource_id][principal_id] = set()
        
        self.entries[resource_id][principal_id].add(permission)
    
    def revoke(self, resource_id: str, principal_id: str, permission: Permission) -> None:
        """
        Revoke a permission from a principal for a resource.
        
        Args:
            resource_id: ID of the resource
            principal_id: ID of the user or role
            permission: Permission to revoke
        """
        if resource_id in self.entries and principal_id in self.entries[resource_id]:
            if permission in self.entries[resource_id][principal_id]:
                self.entries[resource_id][principal_id].remove(permission)
                
                # Clean up empty entries
                if not self.entries[resource_id][principal_id]:
                    del self.entries[resource_id][principal_id]
                
                if not self.entries[resource_id]:
                    del self.entries[resource_id]
    
    def get_permissions(self, resource_id: str, principal_id: str) -> Set[Permission]:
        """
        Get permissions for a principal on a resource.
        
        Args:
            resource_id: ID of the resource
            principal_id: ID of the user or role
            
        Returns:
            Set of permissions
        """
        if resource_id in self.entries and principal_id in self.entries[resource_id]:
            return self.entries[resource_id][principal_id].copy()
        return set()
    
    def has_permission(self, resource_id: str, principal_id: str, permission: Permission) -> bool:
        """
        Check if a principal has a specific permission on a resource.
        
        Args:
            resource_id: ID of the resource
            principal_id: ID of the user or role
            permission: Permission to check
            
        Returns:
            True if the principal has the permission
        """
        return permission in self.get_permissions(resource_id, principal_id)
    
    def get_principals_with_permission(self, resource_id: str, permission: Permission) -> Set[str]:
        """
        Get all principals that have a specific permission on a resource.
        
        Args:
            resource_id: ID of the resource
            permission: Permission to check
            
        Returns:
            Set of principal IDs
        """
        result = set()
        if resource_id in self.entries:
            for principal_id, permissions in self.entries[resource_id].items():
                if permission in permissions:
                    result.add(principal_id)
        return result


class AccessControlManager:
    """Manages access control for the database system."""
    
    def __init__(self):
        """Initialize the access control manager."""
        self.users: Dict[str, User] = {}
        self.roles: Dict[str, Role] = {}
        self.resources: Dict[str, Resource] = {}
        self.acl = AccessControlList()
        
        # Initialize system resources and roles
        self._init_system_roles()
        self._init_system_resources()
    
    def _init_system_resources(self) -> None:
        """Initialize system resources."""
        # Create system resource with admin as owner (admin should exist by now)
        if "system" not in self.resources:
            self.create_resource("system", "System", ResourceType.SYSTEM, "admin")
    
    def _init_system_roles(self) -> None:
        """Initialize system roles with proper permissions."""
        # First create admin role
        admin_role = self.create_role("admin", "Administrator", "Full system access")
        
        # Create default roles
        self.create_role("reader", "Reader", "Read-only access")
        self.create_role("writer", "Writer", "Read and write access")
        
        # Create system admin user if it doesn't exist
        if "admin" not in self.users:
            self.create_user("admin", "admin")
            self.assign_role("admin", "admin")
    
    def debug_user_permissions(self, user_id: str) -> None:
        """Print debug information about a user's permissions."""
        if user_id not in self.users:
            print(f"User {user_id} not found")
            return
        
        user = self.users[user_id]
        print(f"\n=== Permission Debug for User {user_id} ({user.username}) ===")
        print("Direct permissions:")
        for resource, perms in user.direct_permissions.items():
            print(f"  {resource}: {[p.name for p in perms]}")
        
        print("\nRoles:", user.roles)
        for role_id in user.roles:
            if role_id in self.roles:
                role = self.roles[role_id]
                print(f"\nRole {role_id} ({role.name}) permissions:")
                for resource, perms in role.permissions.items():
                    print(f"  {resource}: {[p.name for p in perms]}")
            else:
                print(f"Role {role_id} not found")
        
        print("\nAll resources in system:")
        for resource_id, resource in self.resources.items():
            print(f"  {resource_id} ({resource.type.name})")
    
    def create_user(self, username: str, user_id: Optional[str] = None) -> str:
        """
        Create a new user.
        
        Args:
            username: Username
            user_id: Optional user ID (generated if not provided)
            
        Returns:
            User ID
        """
        if user_id is None:
            user_id = str(uuid.uuid4())
        
        if user_id in self.users:
            raise ValueError(f"User with ID {user_id} already exists")
        
        user = User(user_id, username)
        self.users[user_id] = user
        
        # Create a user-specific resource
        user_resource_id = f"user:{user_id}"
        self.create_resource(user_resource_id, f"User {username}", ResourceType.USER, user_id)
        
        return user_id
    
    def create_role(self, role_id: str, name: str, description: str = "") -> Role:
        """
        Create a new role.
        
        Args:
            role_id: Role ID
            name: Role name
            description: Optional description
            
        Returns:
            The created Role object
        """
        if role_id in self.roles:
            raise ValueError(f"Role with ID {role_id} already exists")
        
        role = Role(role_id, name, description)
        self.roles[role_id] = role
        
        return role
    
    def create_resource(self, resource_id: str, name: str, 
                       resource_type: ResourceType, owner_id: str) -> Resource:
        """
        Create a new resource.
        
        Args:
            resource_id: Resource ID
            name: Resource name
            resource_type: Type of resource
            owner_id: Owner's user ID
            
        Returns:
            The created Resource object
        """
        if resource_id in self.resources:
            raise ValueError(f"Resource with ID {resource_id} already exists")
        
        resource = Resource(resource_id, name, resource_type, owner_id)
        self.resources[resource_id] = resource
        
        # Automatically grant full access to the owner
        self.grant_permission(owner_id, resource_id, Permission.ADMIN)
        
        return resource
    
    def assign_role(self, user_id: str, role_id: str) -> None:
        """
        Assign a role to a user.
        
        Args:
            user_id: User ID
            role_id: Role ID
        """
        if user_id not in self.users:
            raise ValueError(f"User with ID {user_id} does not exist")
        
        if role_id not in self.roles:
            raise ValueError(f"Role with ID {role_id} does not exist")
        
        self.users[user_id].add_role(role_id)
    
    def revoke_role(self, user_id: str, role_id: str) -> None:
        """
        Revoke a role from a user.
        
        Args:
            user_id: User ID
            role_id: Role ID
        """
        if user_id not in self.users:
            raise ValueError(f"User with ID {user_id} does not exist")
        
        self.users[user_id].remove_role(role_id)
    
    def grant_permission(self, principal_id: str, resource_id: str, 
                        permission: Permission) -> None:
        """
        Grant a permission to a principal (user or role) for a resource.
        
        Args:
            principal_id: User or role ID
            resource_id: Resource ID
            permission: Permission to grant
        """
        if resource_id not in self.resources:
            raise ValueError(f"Resource with ID {resource_id} does not exist")
        
        # Check if this is a user or role
        if principal_id in self.users:
            self.users[principal_id].grant_permission(resource_id, permission)
        elif principal_id in self.roles:
            self.roles[principal_id].grant_permission(resource_id, permission)
        else:
            raise ValueError(f"Principal with ID {principal_id} does not exist")
        
        # Also update the ACL
        self.acl.grant(resource_id, principal_id, permission)
    
    def revoke_permission(self, principal_id: str, resource_id: str, 
                         permission: Permission) -> None:
        """
        Revoke a permission from a principal for a resource.
        
        Args:
            principal_id: User or role ID
            resource_id: Resource ID
            permission: Permission to revoke
        """
        # Check if this is a user or role
        if principal_id in self.users:
            self.users[principal_id].revoke_permission(resource_id, permission)
        elif principal_id in self.roles:
            self.roles[principal_id].revoke_permission(resource_id, permission)
        
        # Also update the ACL
        self.acl.revoke(resource_id, principal_id, permission)
    
    def check_permission(self, user_id: str, resource_id: str, 
                        permission: Permission) -> bool:
        """
        Check if a user has a specific permission on a resource.
        
        Args:
            user_id: User ID
            resource_id: Resource ID
            permission: Permission to check
            
        Returns:
            True if the user has the permission
        """
        if user_id not in self.users:
            return False
        
        # Bypass permission checks for admin users
        if "admin" in self.users[user_id].roles:
            return True
        
        # Check if user has direct permission
        user = self.users[user_id]
        if resource_id in user.direct_permissions and permission in user.direct_permissions[resource_id]:
            return True
        
        # Check permissions from roles
        for role_id in user.roles:
            if role_id in self.roles:
                role = self.roles[role_id]
                
                # Check direct role permissions
                if resource_id in role.permissions and permission in role.permissions[resource_id]:
                    return True
                
                # Check inherited permissions from parent roles (recursive)
                if self._check_role_hierarchy_permission(role_id, resource_id, permission, set()):
                    return True
        
        # Check resource hierarchy (parent resources)
        if resource_id in self.resources:
            resource = self.resources[resource_id]
            if resource.parent_resource_id:
                return self.check_permission(user_id, resource.parent_resource_id, permission)
        
        return False
    
    def _check_role_hierarchy_permission(self, role_id: str, resource_id: str, 
                                       permission: Permission, visited: Set[str]) -> bool:
        """
        Recursively check for a permission in the role hierarchy.
        
        Args:
            role_id: Role ID to check
            resource_id: Resource ID
            permission: Permission to check
            visited: Set of already visited roles to prevent loops
            
        Returns:
            True if the permission is found in the role hierarchy
        """
        if role_id in visited:
            return False
        
        visited.add(role_id)
        
        # Check current role
        if role_id in self.roles:
            role = self.roles[role_id]
            
            # Direct permission check
            if resource_id in role.permissions and permission in role.permissions[resource_id]:
                return True
            
            # Check parent roles
            for parent_role_id in role.parent_roles:
                if self._check_role_hierarchy_permission(parent_role_id, resource_id, permission, visited):
                    return True
        
        return False
    
    def enforce_permission(self, user_id: str, resource_id: str, 
                          permission: Permission) -> None:
        """
        Enforce a permission check, raising an exception if not allowed.
        
        Args:
            user_id: User ID
            resource_id: Resource ID
            permission: Required permission
            
        Raises:
            AccessDeniedException: If the user doesn't have the required permission
        """
        if not self.check_permission(user_id, resource_id, permission):
            raise AccessDeniedException(
                f"User {user_id} does not have {permission.name} permission on resource {resource_id}"
            )
    
    def get_accessible_resources(self, user_id: str, 
                               permission: Permission) -> List[Resource]:
        """
        Get all resources that a user can access with a specific permission.
        
        Args:
            user_id: User ID
            permission: Required permission
            
        Returns:
            List of accessible resources
        """
        if user_id not in self.users:
            return []
        
        accessible_resources = []
        
        for resource_id, resource in self.resources.items():
            if self.check_permission(user_id, resource_id, permission):
                accessible_resources.append(resource)
        
        return accessible_resources
    
    def authorize_query(self, query, user_id):
        """
        Authorize a query based on user permissions.
        
        Args:
            query: A query dictionary or ParsedQuery object representing the query to authorize
            user_id: The ID of the user attempting to execute the query
        
        Returns:
            bool: True if the query is authorized, False otherwise
        """
        logger.info("Authorizing query for user ID: %s", user_id)
        
        # Bypass authorization for admin users
        if user_id in self.users and "admin" in self.users[user_id].roles:
            return True
        
        # Handle case where user_id might be a User object
        if hasattr(user_id, 'user_id'):
            user_id = user_id.user_id
        
        # Convert ParsedQuery to dict if needed
        if hasattr(query, 'to_dict'):
            query_dict = query.to_dict()
        else:
            query_dict = query
        
        try:
            # Check if user has access to the table
            target_table = query_dict.get('target_table')
            if target_table:
                required_permission = self._get_required_permission(query_dict['query_type'])
                if not self.check_permission(user_id, target_table, required_permission):
                    logger.warning("User %s lacks permission for %s on table %s", 
                                user_id, query_dict['query_type'], target_table)
                    return False
            
            # For quantum operations, check if user has quantum computing privileges
            if query_dict.get('query_type', '').startswith('QUANTUM_'):
                if not self._has_quantum_privileges(user_id):
                    logger.warning("User %s lacks quantum computing privileges", user_id)
                    return False
                
                # Check quantum resource quota
                quantum_clauses = query_dict.get('quantum_clauses', [])
                if not self._check_quantum_resource_quota(user_id, quantum_clauses):
                    logger.warning("User %s exceeds quantum resource quota", user_id)
                    return False
            
            logger.info("Query authorized for user %s", user_id)
            return True
        
        except Exception as e:
            logger.error("Authorization error: %s", str(e))
            return False
    
    def _get_required_permission(self, query_type: str) -> Permission:
        """Map query type to required permission."""
        query_type = query_type.upper()
        if query_type in ["SELECT", "READ"]:
            return Permission.READ
        elif query_type in ["INSERT", "UPDATE", "WRITE"]:
            return Permission.WRITE
        elif query_type == "DELETE":
            return Permission.DELETE
        elif query_type == "CREATE":
            return Permission.CREATE
        elif query_type == "ALTER":
            return Permission.ALTER
        elif query_type == "DROP":
            return Permission.DROP
        return Permission.EXECUTE
    
    def _has_quantum_privileges(self, user_id: str) -> bool:
        """Check if user has quantum computing privileges."""
        if user_id in self.users and "admin" in self.users[user_id].roles:
            return True
        return False
    
    def _check_quantum_resource_quota(self, user_id: str, quantum_clauses: List) -> bool:
        """Check if the query's quantum resource requirements are within user's quota."""
        # Admin users have unlimited quantum resources
        if user_id in self.users and "admin" in self.users[user_id].roles:
            return True
        
        # For non-admin users, implement quota checks here
        # This is a placeholder - implement actual quota checking logic
        return True
    
    def authenticate(self, credentials):
        """
        Authenticate a user with the given credentials.
        
        Args:
            credentials: Can be a username string, or a dictionary with username/password
            
        Returns:
            User object if authentication was successful, None otherwise
        """
        # Handle both string username and dictionary credentials
        if isinstance(credentials, dict):
            username = credentials.get('username')
            password = credentials.get('password')
        else:
            username = credentials
            password = None
        
        # Find the user by username
        user = self.get_user_by_username(username)
        
        if not user:
            logger.warning(f"User not found during authentication: {username}")
            return None
        
        # In a real implementation, we would check the password
        # For this example, any password is accepted
        
        return user
    
    def set_user_password(self, user_id: str, password: str) -> None:
        """
        Set or update a user's password.
        
        Args:
            user_id: User ID
            password: New password to set
        """
        if user_id not in self.users:
            raise ValueError(f"User with ID {user_id} does not exist")
        
        # Store the password directly in user attributes
        self.users[user_id].attributes['password'] = password
        # Track when password was set
        self.users[user_id].attributes['password_updated_at'] = time.time()
    
    def get_user_by_username(self, username):
        """
        Find a user by username.
        
        Args:
            username: The username to search for
            
        Returns:
            User object if found, None otherwise
        """
        if not hasattr(self, 'users'):
            return None
            
        # Search through users dictionary for matching username
        for user_id, user in self.users.items():
            if hasattr(user, 'username') and user.username == username:
                return user
        
        # If we have a direct mapping of usernames to IDs, use that
        if hasattr(self, 'username_to_id'):
            user_id = self.username_to_id.get(username)
            if user_id and user_id in self.users:
                return self.users[user_id]
        
        # For system users where ID might be used as username
        if username in self.users:
            return self.users[username]
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Export the access control system state as a dictionary."""
        return {
            'users': {uid: user.to_dict() for uid, user in self.users.items()},
            'roles': {rid: role.to_dict() for rid, role in self.roles.items()},
            'resources': {rid: res.to_dict() for rid, res in self.resources.items()}
        }
    
    def from_dict(self, data: Dict[str, Any]) -> None:
        """
        Import access control system state from a dictionary.
        
        Args:
            data: Dictionary representation of the access control system
        """
        # Clear existing data
        self.users.clear()
        self.roles.clear()
        self.resources.clear()
        
        # Import roles first
        for role_id, role_data in data.get('roles', {}).items():
            role = Role(role_id, role_data['name'], role_data.get('description', ''))
            for parent_role_id in role_data.get('parent_roles', []):
                role.add_parent_role(parent_role_id)
            self.roles[role_id] = role
        
        # Import users
        for user_id, user_data in data.get('users', {}).items():
            user = User(user_id, user_data['username'])
            for role_id in user_data.get('roles', []):
                user.add_role(role_id)
            user.attributes = user_data.get('attributes', {})
            user.last_login = user_data.get('last_login')
            user.failed_logins = user_data.get('failed_logins', 0)
            self.users[user_id] = user
        
        # Import resources
        for resource_id, resource_data in data.get('resources', {}).items():
            resource = Resource(
                resource_id,
                resource_data['name'],
                ResourceType.from_string(resource_data['type']),
                resource_data['owner_id']
            )
            resource.attributes = resource_data.get('attributes', {})
            resource.parent_resource_id = resource_data.get('parent_resource_id')
            self.resources[resource_id] = resource
        
        # Set up permissions after all entities are created
        for role_id, role_data in data.get('roles', {}).items():
            for resource_id, perm_names in role_data.get('permissions', {}).items():
                for perm_name in perm_names:
                    self.grant_permission(role_id, resource_id, Permission.from_string(perm_name))
        
        for user_id, user_data in data.get('users', {}).items():
            for resource_id, perm_names in user_data.get('direct_permissions', {}).items():
                for perm_name in perm_names:
                    self.grant_permission(user_id, resource_id, Permission.from_string(perm_name))