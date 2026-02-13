"""
Organizations and Projects API routes.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Organization, Project, User, AuditLog
from app.core.rbac import require_admin, require_owner, get_current_user_context
from app.core.security import get_role_value

router = APIRouter(prefix="/api", tags=["Organizations"])


# ============= SCHEMAS =============

class OrganizationResponse(BaseModel):
    id: int
    name: str
    slug: str
    settings: dict
    
    class Config:
        orm_mode = True


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    settings: Optional[dict] = None


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    
    class Config:
        orm_mode = True


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


# ============= ORGANIZATION ROUTES =============

@router.get("/orgs/current", response_model=OrganizationResponse)
async def get_current_organization(
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Get current user's organization."""
    org = db.query(Organization).filter(Organization.id == user_context["org_id"]).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.put("/orgs/current", response_model=OrganizationResponse)
async def update_current_organization(
    request: Request,
    update_data: OrganizationUpdate,
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update current organization (admin only)."""
    org = db.query(Organization).filter(
        Organization.id == user_context["org_id"]
    ).first()
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    if update_data.name:
        org.name = update_data.name
    if update_data.settings is not None:
        org.settings = update_data.settings
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=org.id,
        action="update_organization",
        entity_type="organization",
        entity_id=org.id,
        details=update_data.dict(exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(org)
    
    return org


@router.get("/orgs/current/users", response_model=List[dict])
async def list_organization_users(
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List users in current organization (admin only)."""
    users = db.query(User).filter(
        User.organization_id == user_context["org_id"]
    ).all()
    
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": get_role_value(u.role),
            "is_active": u.is_active,
            "last_login": u.last_login.isoformat() if u.last_login else None,
        }
        for u in users
    ]


# ============= PROJECT ROUTES =============

@router.get("/projects", response_model=List[ProjectResponse])
async def list_projects(
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """List projects in current organization."""
    projects = db.query(Project).filter(
        Project.organization_id == user_context["org_id"],
        Project.is_active == True
    ).all()
    return projects


@router.post("/projects", response_model=ProjectResponse)
async def create_project(
    request: Request,
    project_data: ProjectCreate,
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Create a new project (admin only)."""
    # Check for duplicate name
    existing = db.query(Project).filter(
        Project.organization_id == user_context["org_id"],
        Project.name == project_data.name
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project with this name already exists",
        )
    
    project = Project(
        name=project_data.name,
        description=project_data.description,
        organization_id=user_context["org_id"],
    )
    db.add(project)
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="create_project",
        entity_type="project",
        details={"name": project_data.name},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(project)
    
    return project


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Get a specific project."""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.organization_id == user_context["org_id"]
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return project


@router.put("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    request: Request,
    update_data: ProjectUpdate,
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update a project (admin only)."""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.organization_id == user_context["org_id"]
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if update_data.name is not None:
        project.name = update_data.name
    if update_data.description is not None:
        project.description = update_data.description
    if update_data.is_active is not None:
        project.is_active = update_data.is_active
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="update_project",
        entity_type="project",
        entity_id=project_id,
        details=update_data.dict(exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(project)
    
    return project
