"""
Admin API routes - User management and system administration.
Requires ADMIN or OWNER role for all endpoints.
"""
import re
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, Organization, AuditLog, UserRole
from app.core.security import get_password_hash, get_role_value
from app.core.rbac import require_admin, get_current_user_context

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ============= SCHEMAS =============

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "viewer"  # viewer, operator, admin, owner
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Enforce password requirements."""
        if len(v) < 10:
            raise ValueError('Password must be at least 10 characters')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Password must contain at least one letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is valid."""
        valid_roles = ['viewer', 'operator', 'admin', 'owner']
        if v.lower() not in valid_roles:
            raise ValueError(f'Role must be one of: {", ".join(valid_roles)}')
        return v.lower()


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    organization_id: int
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


# ============= ROUTES =============

@router.get("/users", response_model=List[UserResponse])
async def list_users(
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    List all users in the organization.
    Admin-only endpoint.
    """
    users = db.query(User).filter(
        User.organization_id == user_context["org_id"]
    ).order_by(User.email).all()
    
    return [
        UserResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=get_role_value(u.role),
            is_active=u.is_active,
            organization_id=u.organization_id,
            created_at=u.created_at,
            last_login=u.last_login,
        )
        for u in users
    ]


@router.post("/users", response_model=UserResponse)
async def create_user(
    request: Request,
    user_data: UserCreate,
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Create a new user.
    Admin-only endpoint.
    
    Password requirements:
    - Minimum 10 characters
    - At least one letter
    - At least one number
    """
    # Check if email already exists
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Map role string to enum
    role_map = {
        'viewer': UserRole.VIEWER,
        'operator': UserRole.OPERATOR,
        'admin': UserRole.ADMIN,
        'owner': UserRole.OWNER,
    }
    
    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=role_map.get(user_data.role, UserRole.VIEWER).value,
        organization_id=user_context["org_id"],
        is_active=True,
    )
    db.add(user)
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="create_user",
        entity_type="user",
        details={"email": user_data.email, "role": user_data.role},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(user)
    
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=get_role_value(user.role),
        is_active=user.is_active,
        organization_id=user.organization_id,
        created_at=user.created_at,
        last_login=user.last_login,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get a specific user by ID. Admin-only."""
    user = db.query(User).filter(
        User.id == user_id,
        User.organization_id == user_context["org_id"]
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=get_role_value(user.role),
        is_active=user.is_active,
        organization_id=user.organization_id,
        created_at=user.created_at,
        last_login=user.last_login,
    )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: Request,
    update_data: UserUpdate,
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update a user. Admin-only."""
    user = db.query(User).filter(
        User.id == user_id,
        User.organization_id == user_context["org_id"]
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update fields
    if update_data.full_name is not None:
        user.full_name = update_data.full_name
    
    if update_data.role is not None:
        role_map = {
            'viewer': UserRole.VIEWER,
            'operator': UserRole.OPERATOR,
            'admin': UserRole.ADMIN,
            'owner': UserRole.OWNER,
        }
        if update_data.role.lower() in role_map:
            user.role = role_map[update_data.role.lower()].value
    
    if update_data.is_active is not None:
        user.is_active = update_data.is_active
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="update_user",
        entity_type="user",
        entity_id=user_id,
        details=update_data.model_dump(exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(user)
    
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=get_role_value(user.role),
        is_active=user.is_active,
        organization_id=user.organization_id,
        created_at=user.created_at,
        last_login=user.last_login,
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a user. Admin-only. Cannot delete yourself."""
    if int(user_context["sub"]) == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    user = db.query(User).filter(
        User.id == user_id,
        User.organization_id == user_context["org_id"]
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_email = user.email
    db.delete(user)
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="delete_user",
        entity_type="user",
        entity_id=user_id,
        details={"email": user_email},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    
    return {"message": f"User {user_email} deleted"}


class PasswordResetRequest(BaseModel):
    new_password: str
    
    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Enforce password requirements."""
        if len(v) < 10:
            raise ValueError('Password must be at least 10 characters')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Password must contain at least one letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    request: Request,
    password_data: PasswordResetRequest,
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Reset a user's password (admin sets temporary password).
    Admin-only endpoint.
    
    The user should change this password on their next login.
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.organization_id == user_context["org_id"]
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update password
    user.hashed_password = get_password_hash(password_data.new_password)
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="reset_user_password",
        entity_type="user",
        entity_id=user_id,
        details={"email": user.email},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    
    return {"message": f"Password reset for {user.email}. User should change password on next login."}
