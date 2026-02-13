"""
Role-Based Access Control (RBAC) middleware and decorators.
"""
from enum import Enum
from typing import List, Optional
from functools import wraps
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.security import decode_token, security


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


# Role hierarchy: higher index = more permissions
ROLE_HIERARCHY = {
    Role.VIEWER: 0,
    Role.OPERATOR: 1,
    Role.ADMIN: 2,
    Role.OWNER: 3,
}


def has_permission(user_role: Role, required_role: Role) -> bool:
    """Check if user role has sufficient permissions."""
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 0)


class RBACChecker:
    """Dependency for checking role-based access."""
    
    def __init__(self, required_role: Role):
        self.required_role = required_role
    
    async def __call__(
        self, 
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> dict:
        payload = decode_token(credentials.credentials)
        user_role = Role(payload.get("role", "viewer"))
        
        if not has_permission(user_role, self.required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {self.required_role.value}",
            )
        
        return payload


# Convenience dependencies for common role checks
require_viewer = RBACChecker(Role.VIEWER)
require_operator = RBACChecker(Role.OPERATOR)
require_admin = RBACChecker(Role.ADMIN)
require_owner = RBACChecker(Role.OWNER)


async def get_current_user_context(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Get current user context including org_id and project_id."""
    payload = decode_token(credentials.credentials)
    
    # Extract user_id with fallback for different token formats
    user_id_raw = payload.get("sub") or payload.get("user_id") or payload.get("id")
    if user_id_raw is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user identifier (sub)",
        )
    user_id = int(user_id_raw)
    
    return {
        "sub": str(user_id),  # Keep "sub" for backwards compat
        "user_id": user_id,
        "email": payload.get("email"),
        "role": Role(payload.get("role", "viewer")),
        "org_id": payload.get("org_id"),
        "project_id": payload.get("project_id"),
    }



class OrgAccessChecker:
    """Check that a user belongs to the specified organization."""
    
    async def __call__(
        self,
        org_id: int,
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> dict:
        payload = decode_token(credentials.credentials)
        token_org_id = payload.get("org_id")
        
        if token_org_id != org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this organization",
            )
        
        return payload
