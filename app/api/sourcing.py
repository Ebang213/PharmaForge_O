"""
Smart Sourcing SDR API routes - RFQ and vendor comparison.
"""
from typing import List, Optional
from datetime import datetime
import hashlib
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.db.models import (
    RFQRequest, RFQVendor, RFQQuote, RFQMessage, VendorScorecard,
    Vendor, AuditLog, RFQStatus, MessageStatus, RiskLevel
)
from app.core.rbac import require_operator, require_admin, get_current_user_context
from app.core.config import settings
from app.services.llm_provider import generate_rfq_email

router = APIRouter(prefix="/api/sourcing", tags=["Sourcing"])


def get_risk_level_str(risk_level) -> str:
    """
    Safely extract risk_level as a string.
    
    Handles both enum instances (RiskLevel.LOW) and string values ("low").
    """
    if risk_level is None:
        return "low"
    if hasattr(risk_level, 'value'):
        return risk_level.value
    return str(risk_level)


# ============= SCHEMAS =============

class RFQCreate(BaseModel):
    title: str
    item_type: str  # API, excipient, packaging
    item_description: str
    specifications: Optional[dict] = None
    quantity: float
    quantity_unit: Optional[str] = None
    delivery_location: Optional[str] = None
    target_date: Optional[datetime] = None
    compliance_constraints: Optional[dict] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    currency: str = "USD"
    vendor_ids: Optional[List[int]] = None  # Vendors to invite


class RFQUpdate(BaseModel):
    title: Optional[str] = None
    item_description: Optional[str] = None
    specifications: Optional[dict] = None
    quantity: Optional[float] = None
    delivery_location: Optional[str] = None
    target_date: Optional[datetime] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None


class RFQResponse(BaseModel):
    id: int
    rfq_number: str
    title: str
    item_type: str
    item_description: str
    quantity: float
    quantity_unit: Optional[str]
    delivery_location: Optional[str]
    target_date: Optional[datetime]
    status: str
    created_at: datetime
    vendor_count: int
    quote_count: int
    
    class Config:
        orm_mode = True


class RFQDetailResponse(RFQResponse):
    specifications: Optional[dict]
    compliance_constraints: Optional[dict]
    budget_min: Optional[float]
    budget_max: Optional[float]
    currency: str
    selected_vendor_id: Optional[int]
    decision_notes: Optional[str]
    vendors: List[dict]
    quotes: List[dict]
    messages: List[dict]
    scorecards: List[dict]


class MessageDraftCreate(BaseModel):
    vendor_id: int
    subject: Optional[str] = None
    custom_notes: Optional[str] = None


class MessageApprove(BaseModel):
    message_ids: List[int]


class QuoteCreate(BaseModel):
    vendor_id: int
    price_per_unit: Optional[float] = None
    total_price: Optional[float] = None
    currency: str = "USD"
    moq: Optional[float] = None
    lead_time_days: Optional[int] = None
    incoterms: Optional[str] = None
    validity_date: Optional[datetime] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None


class AwardDecision(BaseModel):
    vendor_id: int
    decision_notes: Optional[str] = None


# ============= ROUTES =============

@router.get("/rfq", response_model=List[RFQResponse])
async def list_rfqs(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """List RFQ requests."""
    query = db.query(RFQRequest).filter(
        RFQRequest.organization_id == user_context["org_id"]
    )
    
    if status:
        query = query.filter(RFQRequest.status == RFQStatus(status))
    
    rfqs = query.order_by(desc(RFQRequest.created_at)).offset(offset).limit(limit).all()
    
    return [
        RFQResponse(
            id=r.id,
            rfq_number=r.rfq_number,
            title=r.title,
            item_type=r.item_type,
            item_description=r.item_description,
            quantity=r.quantity,
            quantity_unit=r.quantity_unit,
            delivery_location=r.delivery_location,
            target_date=r.target_date,
            status=r.status.value if r.status else "draft",
            created_at=r.created_at,
            vendor_count=len(r.rfq_vendors) if r.rfq_vendors else 0,
            quote_count=len(r.quotes) if r.quotes else 0,
        )
        for r in rfqs
    ]


@router.post("/rfq", response_model=RFQDetailResponse)
async def create_rfq(
    request: Request,
    rfq_data: RFQCreate,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Create a new RFQ."""
    org_id = user_context["org_id"]
    user_id = int(user_context["sub"])
    
    # Generate RFQ number
    rfq_number = f"RFQ-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    
    rfq = RFQRequest(
        organization_id=org_id,
        created_by=user_id,
        rfq_number=rfq_number,
        title=rfq_data.title,
        item_type=rfq_data.item_type,
        item_description=rfq_data.item_description,
        specifications=rfq_data.specifications,
        quantity=rfq_data.quantity,
        quantity_unit=rfq_data.quantity_unit,
        delivery_location=rfq_data.delivery_location,
        target_date=rfq_data.target_date,
        compliance_constraints=rfq_data.compliance_constraints,
        budget_min=rfq_data.budget_min,
        budget_max=rfq_data.budget_max,
        currency=rfq_data.currency,
        status=RFQStatus.DRAFT,
    )
    db.add(rfq)
    db.flush()
    
    # Add vendors if provided
    if rfq_data.vendor_ids:
        for vid in rfq_data.vendor_ids:
            vendor = db.query(Vendor).filter(
                Vendor.id == vid,
                Vendor.organization_id == org_id
            ).first()
            if vendor:
                rfq_vendor = RFQVendor(
                    rfq_id=rfq.id,
                    vendor_id=vid,
                )
                db.add(rfq_vendor)
    
    # Audit log
    audit_log = AuditLog(
        user_id=user_id,
        organization_id=org_id,
        action="create_rfq",
        entity_type="rfq_request",
        entity_id=rfq.id,
        details={"rfq_number": rfq_number, "title": rfq_data.title},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(rfq)
    
    return _build_rfq_detail(rfq)


@router.get("/rfq/{rfq_id}", response_model=RFQDetailResponse)
async def get_rfq(
    rfq_id: int,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Get RFQ details."""
    rfq = db.query(RFQRequest).filter(
        RFQRequest.id == rfq_id,
        RFQRequest.organization_id == user_context["org_id"]
    ).first()
    
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    
    return _build_rfq_detail(rfq)


@router.put("/rfq/{rfq_id}", response_model=RFQDetailResponse)
async def update_rfq(
    rfq_id: int,
    request: Request,
    update_data: RFQUpdate,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Update an RFQ."""
    rfq = db.query(RFQRequest).filter(
        RFQRequest.id == rfq_id,
        RFQRequest.organization_id == user_context["org_id"]
    ).first()
    
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    
    if rfq.status not in [RFQStatus.DRAFT, RFQStatus.PENDING_APPROVAL]:
        raise HTTPException(status_code=400, detail="Cannot modify RFQ in current status")
    
    update_dict = update_data.dict(exclude_unset=True)
    for key, value in update_dict.items():
        if value is not None:
            setattr(rfq, key, value)
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="update_rfq",
        entity_type="rfq_request",
        entity_id=rfq_id,
        details=update_dict,
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(rfq)
    
    return _build_rfq_detail(rfq)


@router.post("/rfq/{rfq_id}/vendors/{vendor_id}")
async def add_vendor_to_rfq(
    rfq_id: int,
    vendor_id: int,
    request: Request,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Add a vendor to an RFQ."""
    org_id = user_context["org_id"]
    
    rfq = db.query(RFQRequest).filter(
        RFQRequest.id == rfq_id,
        RFQRequest.organization_id == org_id
    ).first()
    
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    
    vendor = db.query(Vendor).filter(
        Vendor.id == vendor_id,
        Vendor.organization_id == org_id
    ).first()
    
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    # Check if already added
    existing = db.query(RFQVendor).filter(
        RFQVendor.rfq_id == rfq_id,
        RFQVendor.vendor_id == vendor_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Vendor already added to this RFQ")
    
    rfq_vendor = RFQVendor(rfq_id=rfq_id, vendor_id=vendor_id)
    db.add(rfq_vendor)
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=org_id,
        action="add_vendor_to_rfq",
        entity_type="rfq_request",
        entity_id=rfq_id,
        details={"vendor_id": vendor_id, "vendor_name": vendor.name},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    
    return {"message": "Vendor added to RFQ"}


@router.post("/rfq/{rfq_id}/drafts", response_model=List[dict])
async def generate_message_drafts(
    rfq_id: int,
    request: Request,
    draft_data: Optional[MessageDraftCreate] = None,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Generate email drafts for RFQ vendors."""
    org_id = user_context["org_id"]
    user_id = int(user_context["sub"])
    
    rfq = db.query(RFQRequest).filter(
        RFQRequest.id == rfq_id,
        RFQRequest.organization_id == org_id
    ).first()
    
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    
    # Get vendors to generate drafts for
    if draft_data and draft_data.vendor_id:
        rfq_vendors = [rv for rv in rfq.rfq_vendors if rv.vendor_id == draft_data.vendor_id]
    else:
        rfq_vendors = rfq.rfq_vendors
    
    if not rfq_vendors:
        raise HTTPException(status_code=400, detail="No vendors to generate drafts for")
    
    created_messages = []
    for rv in rfq_vendors:
        vendor = db.query(Vendor).filter(Vendor.id == rv.vendor_id).first()
        if not vendor:
            continue
        
        # Generate email using LLM
        email_content = generate_rfq_email(
            rfq_number=rfq.rfq_number,
            item_type=rfq.item_type,
            item_description=rfq.item_description,
            specifications=rfq.specifications,
            quantity=rfq.quantity,
            quantity_unit=rfq.quantity_unit,
            delivery_location=rfq.delivery_location,
            target_date=rfq.target_date,
            compliance_constraints=rfq.compliance_constraints,
            vendor_name=vendor.name,
            custom_notes=draft_data.custom_notes if draft_data else None,
        )
        
        subject = draft_data.subject if draft_data and draft_data.subject else f"Request for Quote: {rfq.rfq_number} - {rfq.title}"
        
        message = RFQMessage(
            rfq_id=rfq_id,
            vendor_id=rv.vendor_id,
            created_by=user_id,
            subject=subject,
            body=email_content,
            recipient_email=vendor.contact_email,
            status=MessageStatus.DRAFT,
        )
        db.add(message)
        db.flush()
        
        created_messages.append({
            "id": message.id,
            "vendor_id": rv.vendor_id,
            "vendor_name": vendor.name,
            "subject": subject,
            "body": email_content,
            "recipient_email": vendor.contact_email,
            "status": "draft",
        })
    
    # Update RFQ status
    rfq.status = RFQStatus.PENDING_APPROVAL
    
    # Audit log
    audit_log = AuditLog(
        user_id=user_id,
        organization_id=org_id,
        action="generate_rfq_drafts",
        entity_type="rfq_request",
        entity_id=rfq_id,
        details={"message_count": len(created_messages)},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    
    return created_messages


@router.post("/rfq/{rfq_id}/drafts/approve")
async def approve_messages(
    rfq_id: int,
    request: Request,
    approval_data: MessageApprove,
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Approve message drafts for sending (requires admin approval)."""
    org_id = user_context["org_id"]
    user_id = int(user_context["sub"])
    
    rfq = db.query(RFQRequest).filter(
        RFQRequest.id == rfq_id,
        RFQRequest.organization_id == org_id
    ).first()
    
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    
    approved_count = 0
    for msg_id in approval_data.message_ids:
        message = db.query(RFQMessage).filter(
            RFQMessage.id == msg_id,
            RFQMessage.rfq_id == rfq_id
        ).first()
        
        if message and message.status == MessageStatus.DRAFT:
            message.status = MessageStatus.APPROVED
            message.approved_by = user_id
            message.approved_at = datetime.utcnow()
            approved_count += 1
    
    # Update RFQ status
    rfq.status = RFQStatus.SENT
    
    # Audit log
    audit_log = AuditLog(
        user_id=user_id,
        organization_id=org_id,
        action="approve_rfq_messages",
        entity_type="rfq_request",
        entity_id=rfq_id,
        details={"approved_count": approved_count, "message_ids": approval_data.message_ids},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    
    return {"message": f"Approved {approved_count} messages", "approved_count": approved_count}


@router.post("/rfq/{rfq_id}/quotes", response_model=dict)
async def upload_quote(
    rfq_id: int,
    request: Request,
    quote_data: QuoteCreate,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Manually enter or upload a quote from a vendor."""
    org_id = user_context["org_id"]
    user_id = int(user_context["sub"])
    
    rfq = db.query(RFQRequest).filter(
        RFQRequest.id == rfq_id,
        RFQRequest.organization_id == org_id
    ).first()
    
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    
    # Verify vendor is part of RFQ
    rfq_vendor = db.query(RFQVendor).filter(
        RFQVendor.rfq_id == rfq_id,
        RFQVendor.vendor_id == quote_data.vendor_id
    ).first()
    
    if not rfq_vendor:
        raise HTTPException(status_code=400, detail="Vendor not part of this RFQ")
    
    quote = RFQQuote(
        rfq_id=rfq_id,
        vendor_id=quote_data.vendor_id,
        uploaded_by=user_id,
        price_per_unit=quote_data.price_per_unit,
        total_price=quote_data.total_price,
        currency=quote_data.currency,
        moq=quote_data.moq,
        lead_time_days=quote_data.lead_time_days,
        incoterms=quote_data.incoterms,
        validity_date=quote_data.validity_date,
        payment_terms=quote_data.payment_terms,
        notes=quote_data.notes,
    )
    db.add(quote)
    
    # Mark vendor as responded
    rfq_vendor.responded = True
    
    # Update RFQ status
    if rfq.status == RFQStatus.SENT:
        rfq.status = RFQStatus.QUOTES_RECEIVED
    
    # Audit log
    audit_log = AuditLog(
        user_id=user_id,
        organization_id=org_id,
        action="upload_quote",
        entity_type="rfq_quote",
        entity_id=rfq_id,
        details={"vendor_id": quote_data.vendor_id, "total_price": quote_data.total_price},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(quote)
    
    return {
        "id": quote.id,
        "vendor_id": quote.vendor_id,
        "price_per_unit": quote.price_per_unit,
        "total_price": quote.total_price,
        "lead_time_days": quote.lead_time_days,
        "created_at": quote.created_at,
    }


@router.get("/rfq/{rfq_id}/compare", response_model=dict)
async def compare_quotes(
    rfq_id: int,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Generate vendor comparison and scorecards."""
    org_id = user_context["org_id"]
    
    rfq = db.query(RFQRequest).filter(
        RFQRequest.id == rfq_id,
        RFQRequest.organization_id == org_id
    ).first()
    
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    
    quotes = rfq.quotes
    if not quotes:
        return {"message": "No quotes to compare", "scorecards": []}
    
    # Calculate scores for each vendor
    scorecards = []
    min_price = min(q.total_price for q in quotes if q.total_price) or 1
    min_lead_time = min(q.lead_time_days for q in quotes if q.lead_time_days) or 1
    
    for quote in quotes:
        vendor = db.query(Vendor).filter(Vendor.id == quote.vendor_id).first()
        
        # Price score (lower is better, 100 is best)
        price_score = (min_price / quote.total_price * 100) if quote.total_price else 50
        
        # Lead time score (lower is better)
        lead_time_score = (min_lead_time / quote.lead_time_days * 100) if quote.lead_time_days else 50
        
        # MOQ score (lower relative to required is better)
        moq_score = 100 if not quote.moq or quote.moq <= rfq.quantity else max(0, 100 - ((quote.moq - rfq.quantity) / rfq.quantity * 50))
        
        # Compliance risk from Watchtower
        compliance_risk = vendor.risk_score if vendor else 50
        compliance_score = 100 - compliance_risk
        
        # Reliability (placeholder - would come from historical data)
        reliability_score = 75
        
        # Overall score (weighted average)
        overall_score = (
            price_score * 0.30 +
            lead_time_score * 0.25 +
            moq_score * 0.15 +
            compliance_score * 0.20 +
            reliability_score * 0.10
        )
        
        # Create or update scorecard
        existing = db.query(VendorScorecard).filter(
            VendorScorecard.rfq_id == rfq_id,
            VendorScorecard.vendor_id == quote.vendor_id
        ).first()
        
        if existing:
            scorecard = existing
        else:
            scorecard = VendorScorecard(
                rfq_id=rfq_id,
                vendor_id=quote.vendor_id,
                quote_id=quote.id,
            )
            db.add(scorecard)
        
        scorecard.price_score = price_score
        scorecard.lead_time_score = lead_time_score
        scorecard.moq_score = moq_score
        scorecard.compliance_risk_score = compliance_risk
        scorecard.reliability_score = reliability_score
        scorecard.overall_score = overall_score
        scorecard.price_notes = f"${quote.total_price:,.2f}" if quote.total_price else "N/A"
        scorecard.compliance_issues = {"risk_level": get_risk_level_str(vendor.risk_level if vendor else None)}
        
        scorecards.append({
            "vendor_id": quote.vendor_id,
            "vendor_name": vendor.name if vendor else "Unknown",
            "quote_id": quote.id,
            "price_score": round(price_score, 1),
            "lead_time_score": round(lead_time_score, 1),
            "moq_score": round(moq_score, 1),
            "compliance_score": round(compliance_score, 1),
            "reliability_score": round(reliability_score, 1),
            "overall_score": round(overall_score, 1),
            "total_price": quote.total_price,
            "lead_time_days": quote.lead_time_days,
            "moq": quote.moq,
            "incoterms": quote.incoterms,
            "compliance_risk_level": get_risk_level_str(vendor.risk_level if vendor else None),
        })
    
    # Sort by overall score (descending)
    scorecards.sort(key=lambda x: x["overall_score"], reverse=True)
    
    # Mark the top vendor as recommended
    if scorecards:
        top_scorecard = db.query(VendorScorecard).filter(
            VendorScorecard.rfq_id == rfq_id,
            VendorScorecard.vendor_id == scorecards[0]["vendor_id"]
        ).first()
        if top_scorecard:
            top_scorecard.is_recommended = True
            top_scorecard.recommendation = "Recommended based on best overall score considering price, lead time, MOQ, compliance, and reliability."
    
    # Update RFQ status
    rfq.status = RFQStatus.EVALUATING
    
    db.commit()
    
    return {
        "rfq_id": rfq_id,
        "rfq_number": rfq.rfq_number,
        "recommendation": scorecards[0] if scorecards else None,
        "scorecards": scorecards,
    }


@router.post("/rfq/{rfq_id}/award")
async def award_rfq(
    rfq_id: int,
    request: Request,
    award_data: AwardDecision,
    user_context: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Award RFQ to a vendor (admin only)."""
    org_id = user_context["org_id"]
    user_id = int(user_context["sub"])
    
    rfq = db.query(RFQRequest).filter(
        RFQRequest.id == rfq_id,
        RFQRequest.organization_id == org_id
    ).first()
    
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    
    # Verify vendor has a quote
    quote = db.query(RFQQuote).filter(
        RFQQuote.rfq_id == rfq_id,
        RFQQuote.vendor_id == award_data.vendor_id
    ).first()
    
    if not quote:
        raise HTTPException(status_code=400, detail="Selected vendor has no quote for this RFQ")
    
    rfq.selected_vendor_id = award_data.vendor_id
    rfq.decision_notes = award_data.decision_notes
    rfq.status = RFQStatus.AWARDED
    rfq.closed_at = datetime.utcnow()
    
    vendor = db.query(Vendor).filter(Vendor.id == award_data.vendor_id).first()
    
    # Audit log
    audit_log = AuditLog(
        user_id=user_id,
        organization_id=org_id,
        action="award_rfq",
        entity_type="rfq_request",
        entity_id=rfq_id,
        details={
            "vendor_id": award_data.vendor_id,
            "vendor_name": vendor.name if vendor else "Unknown",
            "decision_notes": award_data.decision_notes,
        },
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    
    return {
        "message": "RFQ awarded successfully",
        "rfq_number": rfq.rfq_number,
        "vendor_id": award_data.vendor_id,
        "vendor_name": vendor.name if vendor else "Unknown",
    }


def _build_rfq_detail(rfq: RFQRequest) -> RFQDetailResponse:
    """Build detailed RFQ response."""
    from app.db.session import SessionLocal
    db = SessionLocal()
    
    try:
        vendors = []
        for rv in rfq.rfq_vendors:
            vendor = db.query(Vendor).filter(Vendor.id == rv.vendor_id).first()
            vendors.append({
                "id": rv.id,
                "vendor_id": rv.vendor_id,
                "vendor_name": vendor.name if vendor else "Unknown",
                "vendor_email": vendor.contact_email if vendor else None,
                "responded": rv.responded,
                "declined": rv.declined,
                "invited_at": rv.invited_at,
            })
        
        quotes = []
        for q in rfq.quotes:
            vendor = db.query(Vendor).filter(Vendor.id == q.vendor_id).first()
            quotes.append({
                "id": q.id,
                "vendor_id": q.vendor_id,
                "vendor_name": vendor.name if vendor else "Unknown",
                "price_per_unit": q.price_per_unit,
                "total_price": q.total_price,
                "currency": q.currency,
                "moq": q.moq,
                "lead_time_days": q.lead_time_days,
                "incoterms": q.incoterms,
                "validity_date": q.validity_date,
                "payment_terms": q.payment_terms,
                "notes": q.notes,
                "created_at": q.created_at,
            })
        
        messages = []
        for m in rfq.messages:
            messages.append({
                "id": m.id,
                "vendor_id": m.vendor_id,
                "subject": m.subject,
                "body": m.body[:500] + "..." if len(m.body) > 500 else m.body,
                "recipient_email": m.recipient_email,
                "status": m.status.value if m.status else "draft",
                "approved_at": m.approved_at,
                "sent_at": m.sent_at,
                "created_at": m.created_at,
            })
        
        scorecards = []
        for sc in db.query(VendorScorecard).filter(VendorScorecard.rfq_id == rfq.id).all():
            vendor = db.query(Vendor).filter(Vendor.id == sc.vendor_id).first()
            scorecards.append({
                "vendor_id": sc.vendor_id,
                "vendor_name": vendor.name if vendor else "Unknown",
                "price_score": sc.price_score,
                "lead_time_score": sc.lead_time_score,
                "moq_score": sc.moq_score,
                "compliance_risk_score": sc.compliance_risk_score,
                "reliability_score": sc.reliability_score,
                "overall_score": sc.overall_score,
                "is_recommended": sc.is_recommended,
                "recommendation": sc.recommendation,
            })
        
        return RFQDetailResponse(
            id=rfq.id,
            rfq_number=rfq.rfq_number,
            title=rfq.title,
            item_type=rfq.item_type,
            item_description=rfq.item_description,
            specifications=rfq.specifications,
            quantity=rfq.quantity,
            quantity_unit=rfq.quantity_unit,
            delivery_location=rfq.delivery_location,
            target_date=rfq.target_date,
            compliance_constraints=rfq.compliance_constraints,
            budget_min=rfq.budget_min,
            budget_max=rfq.budget_max,
            currency=rfq.currency,
            status=rfq.status.value if rfq.status else "draft",
            selected_vendor_id=rfq.selected_vendor_id,
            decision_notes=rfq.decision_notes,
            created_at=rfq.created_at,
            vendor_count=len(vendors),
            quote_count=len(quotes),
            vendors=vendors,
            quotes=quotes,
            messages=messages,
            scorecards=scorecards,
        )
    finally:
        db.close()
