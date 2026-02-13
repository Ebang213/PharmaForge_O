"""
Audit Log API routes.
"""
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.db.models import AuditLog
from app.core.rbac import require_admin, get_current_user_context

router = APIRouter(prefix="/api/audit", tags=["Audit"])


# ============= SCHEMAS =============

class AuditLogResponse(BaseModel):
    id: int
    timestamp: datetime
    user_id: Optional[int]
    user_email: Optional[str]
    action: str
    entity_type: Optional[str]
    entity_id: Optional[int]
    details: Optional[dict]
    ip_address: Optional[str]
    
    class Config:
        orm_mode = True


class AuditSummary(BaseModel):
    total_events: int
    events_today: int
    top_actions: List[dict]
    top_users: List[dict]


# ============= ROUTES =============

@router.get("/logs", response_model=List[AuditLogResponse])
async def list_audit_logs(
    action: Optional[str] = Query(None, description="Filter by action type"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    user_id: Optional[int] = Query(None, description="Filter by user"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List audit logs for current organization (admin only)."""
    query = db.query(AuditLog).filter(
        AuditLog.organization_id == user_context["org_id"]
    )
    
    if action:
        query = query.filter(AuditLog.action == action)
    
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)
    
    logs = query.order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit).all()
    
    return [
        AuditLogResponse(
            id=log.id,
            timestamp=log.timestamp,
            user_id=log.user_id,
            user_email=log.user.email if log.user else None,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            details=log.details,
            ip_address=log.ip_address,
        )
        for log in logs
    ]


@router.get("/summary", response_model=AuditSummary)
async def get_audit_summary(
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get audit log summary (admin only)."""
    org_id = user_context["org_id"]
    
    # Total events
    total = db.query(AuditLog).filter(AuditLog.organization_id == org_id).count()
    
    # Events today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = db.query(AuditLog).filter(
        AuditLog.organization_id == org_id,
        AuditLog.timestamp >= today_start
    ).count()
    
    # Top actions (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    from sqlalchemy import func
    
    action_counts = db.query(
        AuditLog.action,
        func.count(AuditLog.id).label('count')
    ).filter(
        AuditLog.organization_id == org_id,
        AuditLog.timestamp >= week_ago
    ).group_by(AuditLog.action).order_by(desc('count')).limit(10).all()
    
    top_actions = [{"action": a, "count": c} for a, c in action_counts]
    
    # Top users
    user_counts = db.query(
        AuditLog.user_id,
        func.count(AuditLog.id).label('count')
    ).filter(
        AuditLog.organization_id == org_id,
        AuditLog.timestamp >= week_ago,
        AuditLog.user_id.isnot(None)
    ).group_by(AuditLog.user_id).order_by(desc('count')).limit(10).all()
    
    top_users = [{"user_id": u, "count": c} for u, c in user_counts]
    
    return AuditSummary(
        total_events=total,
        events_today=today_count,
        top_actions=top_actions,
        top_users=top_users,
    )


@router.get("/actions")
async def list_action_types(
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all unique action types in audit log."""
    from sqlalchemy import distinct
    
    actions = db.query(distinct(AuditLog.action)).filter(
        AuditLog.organization_id == user_context["org_id"]
    ).all()
    
    return [a[0] for a in actions]


@router.get("/entity-types")
async def list_entity_types(
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all unique entity types in audit log."""
    from sqlalchemy import distinct
    
    types = db.query(distinct(AuditLog.entity_type)).filter(
        AuditLog.organization_id == user_context["org_id"],
        AuditLog.entity_type.isnot(None)
    ).all()
    
    return [t[0] for t in types]
