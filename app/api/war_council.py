"""
War Council API routes - Multi-persona strategic responses.
"""
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.db.models import WarCouncilSession, WarCouncilResponse, AuditLog, Vendor
from app.core.rbac import require_operator, get_current_user_context
from app.services.llm_provider import generate_war_council_response
from app.core.security import get_role_value

router = APIRouter(prefix="/api/war-council", tags=["War Council"])


# ============= SCHEMAS =============

class WarCouncilQuery(BaseModel):
    question: str
    vendor_ids: Optional[List[int]] = None
    event_ids: Optional[List[int]] = None
    context_notes: Optional[str] = None


class PersonaResponse(BaseModel):
    persona: str
    response: str
    key_points: List[str]
    risk_level: str
    recommended_actions: List[str]


class WarCouncilResult(BaseModel):
    session_id: int
    response_id: int
    question: str
    regulatory: PersonaResponse
    supply_chain: PersonaResponse
    legal: PersonaResponse
    synthesis: str
    overall_risk: str
    priority_actions: List[str]
    created_at: datetime


class SessionListResponse(BaseModel):
    id: int
    title: Optional[str]
    created_at: datetime
    response_count: int
    
    class Config:
        orm_mode = True


# ============= ROUTES =============

@router.post("/query", response_model=WarCouncilResult)
async def query_war_council(
    request: Request,
    query_data: WarCouncilQuery,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Get multi-persona strategic response to a question."""
    org_id = user_context["org_id"]
    user_id = int(user_context["sub"])
    
    # Build context from related entities
    context = {
        "vendor_ids": query_data.vendor_ids or [],
        "event_ids": query_data.event_ids or [],
        "notes": query_data.context_notes,
    }
    
    # Get vendor details if provided
    vendor_context = []
    if query_data.vendor_ids:
        vendors = db.query(Vendor).filter(
            Vendor.id.in_(query_data.vendor_ids),
            Vendor.organization_id == org_id
        ).all()
        vendor_context = [
            {
                "id": v.id,
                "name": v.name,
                "type": v.vendor_type,
                "risk_score": v.risk_score,
                "risk_level": get_role_value(v.risk_level) if v.risk_level else "unknown",
                "country": v.country,
            }
            for v in vendors
        ]
        context["vendors"] = vendor_context
    
    # Create session
    session = WarCouncilSession(
        organization_id=org_id,
        user_id=user_id,
        title=query_data.question[:100],
        context=context,
    )
    db.add(session)
    db.flush()
    
    # Generate multi-persona responses
    result = generate_war_council_response(
        question=query_data.question,
        context=context,
    )
    
    # Store response
    response = WarCouncilResponse(
        session_id=session.id,
        question=query_data.question,
        regulatory_response=result["regulatory"]["response"],
        supply_chain_response=result["supply_chain"]["response"],
        legal_response=result["legal"]["response"],
        synthesis=result["synthesis"],
        references=result.get("references", {}),
    )
    db.add(response)
    
    # Audit log
    audit_log = AuditLog(
        user_id=user_id,
        organization_id=org_id,
        action="war_council_query",
        entity_type="war_council_session",
        entity_id=session.id,
        details={
            "question": query_data.question[:200],
            "vendor_ids": query_data.vendor_ids,
        },
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    
    return WarCouncilResult(
        session_id=session.id,
        response_id=response.id,
        question=query_data.question,
        regulatory=PersonaResponse(
            persona="Regulatory Affairs",
            response=result["regulatory"]["response"],
            key_points=result["regulatory"]["key_points"],
            risk_level=result["regulatory"]["risk_level"],
            recommended_actions=result["regulatory"]["actions"],
        ),
        supply_chain=PersonaResponse(
            persona="Supply Chain",
            response=result["supply_chain"]["response"],
            key_points=result["supply_chain"]["key_points"],
            risk_level=result["supply_chain"]["risk_level"],
            recommended_actions=result["supply_chain"]["actions"],
        ),
        legal=PersonaResponse(
            persona="Legal Counsel",
            response=result["legal"]["response"],
            key_points=result["legal"]["key_points"],
            risk_level=result["legal"]["risk_level"],
            recommended_actions=result["legal"]["actions"],
        ),
        synthesis=result["synthesis"],
        overall_risk=result["overall_risk"],
        priority_actions=result["priority_actions"],
        created_at=datetime.now(timezone.utc),
    )


@router.get("/sessions", response_model=List[SessionListResponse])
async def list_sessions(
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """List War Council sessions."""
    sessions = db.query(WarCouncilSession).filter(
        WarCouncilSession.organization_id == user_context["org_id"]
    ).order_by(desc(WarCouncilSession.created_at)).offset(offset).limit(limit).all()
    
    return [
        SessionListResponse(
            id=s.id,
            title=s.title,
            created_at=s.created_at,
            response_count=len(s.responses) if s.responses else 0,
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=dict)
async def get_session(
    session_id: int,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Get War Council session details."""
    session = db.query(WarCouncilSession).filter(
        WarCouncilSession.id == session_id,
        WarCouncilSession.organization_id == user_context["org_id"]
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "id": session.id,
        "title": session.title,
        "context": session.context,
        "created_at": session.created_at,
        "responses": [
            {
                "id": r.id,
                "question": r.question,
                "regulatory_response": r.regulatory_response,
                "supply_chain_response": r.supply_chain_response,
                "legal_response": r.legal_response,
                "synthesis": r.synthesis,
                "references": r.references,
                "created_at": r.created_at,
            }
            for r in session.responses
        ],
    }


@router.post("/analyze", response_model=WarCouncilResult)
async def analyze_war_council(
    request: Request,
    query_data: WarCouncilQuery,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """
    Alias for /query - analyze a question with the War Council.
    
    Works with or without vendor context. If no vendor_ids provided,
    analyzes the question based on general regulatory/supply chain/legal perspectives.
    """
    return await query_war_council(request, query_data, user_context, db)


@router.get("/health")
async def war_council_health(
    db: Session = Depends(get_db)
):
    """
    War Council module health check.
    Returns status and configuration info.
    """
    from app.core.config import settings
    
    # Get session count
    session_count = db.query(WarCouncilSession).count()
    
    return {
        "status": "healthy",
        "module": "war_council",
        "llm_provider": settings.LLM_PROVIDER,
        "mock_mode": settings.LLM_PROVIDER == "mock",
        "session_count": session_count,
        "message": "Mock responses enabled" if settings.LLM_PROVIDER == "mock" else "LLM integration active"
    }

