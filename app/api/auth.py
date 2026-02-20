"""
Authentication API routes.
"""
import re
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr, field_validator, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import get_db
from app.db.models import User, Organization, AuditLog
from app.core.security import (
    verify_password, get_password_hash, create_access_token,
    get_current_user_id, get_token_payload, get_role_value
)
from app.core.config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ============= SCHEMAS =============

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=128)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=10, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    organization_name: Optional[str] = Field(None, max_length=255)
    organization_slug: Optional[str] = Field(None, max_length=100)

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Password must contain at least one letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    role: str
    organization_id: int
    organization_name: str

    model_config = {"from_attributes": True}


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., max_length=128)
    new_password: str = Field(..., min_length=10, max_length=128)

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Password must contain at least one letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v


# ============= ROUTES =============

@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """Authenticate user and return JWT token."""
    user = db.query(User).filter(func.lower(User.email) == login_data.email.lower()).first()

    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled",
        )

    # Update last login
    user.last_login = datetime.now(timezone.utc)

    # Create token with user context
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": get_role_value(user.role),
        "org_id": user.organization_id,
    }

    access_token = create_access_token(token_data)

    # Log the login
    audit_log = AuditLog(
        user_id=user.id,
        organization_id=user.organization_id,
        action="login",
        entity_type="user",
        entity_id=user.id,
        ip_address=request.client.host if request.client else None,
        details={"email": user.email}
    )
    db.add(audit_log)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": get_role_value(user.role),
            "organization_id": user.organization_id,
            "organization_name": user.organization.name,
        }
    )


@router.post("/register", response_model=TokenResponse)
async def register(
    request: Request,
    register_data: RegisterRequest,
    db: Session = Depends(get_db)
):
    """Register a new user and organization."""
    # Check if public registration is allowed
    if not settings.ALLOW_PUBLIC_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is disabled. Contact an administrator.",
        )

    # Check if email exists
    existing = db.query(User).filter(func.lower(User.email) == register_data.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create organization if provided
    if register_data.organization_name:
        slug = register_data.organization_slug or register_data.organization_name.lower().replace(" ", "-")
        existing_org = db.query(Organization).filter(Organization.slug == slug).first()
        if existing_org:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization slug already exists",
            )

        org = Organization(
            name=register_data.organization_name,
            slug=slug,
        )
        db.add(org)
        db.flush()
    else:
        # Use default organization or require org name
        org = db.query(Organization).first()
        if not org:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization name is required for registration",
            )

    # Create user as owner of new org
    from app.db.models import UserRole
    user = User(
        email=register_data.email,
        hashed_password=get_password_hash(register_data.password),
        full_name=register_data.full_name,
        role=UserRole.OWNER.value if register_data.organization_name else UserRole.VIEWER.value,
        organization_id=org.id,
    )
    db.add(user)
    db.flush()

    # Log registration
    audit_log = AuditLog(
        user_id=user.id,
        organization_id=org.id,
        action="register",
        entity_type="user",
        entity_id=user.id,
        ip_address=request.client.host if request.client else None,
        details={"email": user.email, "organization": org.name}
    )
    db.add(audit_log)
    db.commit()

    # Create token
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": get_role_value(user.role),
        "org_id": user.organization_id,
    }
    access_token = create_access_token(token_data)

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": get_role_value(user.role),
            "organization_id": user.organization_id,
            "organization_name": org.name,
        }
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get current authenticated user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=get_role_value(user.role),
        organization_id=user.organization_id,
        organization_name=user.organization.name,
    )


@router.post("/change-password")
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Change current user's password."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    user.hashed_password = get_password_hash(data.new_password)

    # Log password change
    audit_log = AuditLog(
        user_id=user.id,
        organization_id=user.organization_id,
        action="change_password",
        entity_type="user",
        entity_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()

    return {"message": "Password changed successfully"}


@router.post("/logout")
async def logout(
    request: Request,
    token_payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db)
):
    """Log out user (for audit purposes)."""
    user_id = int(token_payload.get("sub"))
    org_id = token_payload.get("org_id")

    audit_log = AuditLog(
        user_id=user_id,
        organization_id=org_id,
        action="logout",
        entity_type="user",
        entity_id=user_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()

    return {"message": "Logged out successfully"}
