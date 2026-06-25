"""
Trading Partners API routes for DSCSA compliance.

Exposes /api/trading-partners endpoints backed by the existing Vendor model.
Keeps /api/vendors intact for Watchtower and other internal consumers.
"""
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.db.session import get_db
from app.db.models import Vendor, AuditLog
from app.core.rbac import require_operator, get_current_user_context

router = APIRouter(prefix="/api/trading-partners", tags=["Trading Partners"])

VALID_PARTNER_TYPES = [
    "MANUFACTURER",
    "WHOLESALE_DISTRIBUTOR",
    "DISPENSER",
    "REPACKAGER",
    "THIRD_PARTY_LOGISTICS",
    "OTHER",
]

VALID_STATUSES = ["active", "pending_review", "inactive"]


# ============= READINESS LOGIC =============

def compute_readiness(vendor: Vendor) -> tuple[str, list[str]]:
    """
    Determine DSCSA verification status for a trading partner.
    Returns (verification_status, missing_fields).
    """
    missing: list[str] = []

    if not vendor.name:
        missing.append("name")

    if not vendor.vendor_type:
        missing.append("partner_type")

    has_identifier = any([vendor.gln, vendor.dea_number, vendor.state_license_number])
    if not has_identifier:
        missing.append("at_least_one_identifier (gln, dea_number, or state_license_number)")

    has_contact = any([vendor.contact_email, vendor.contact_phone])
    if not has_contact:
        missing.append("contact_email_or_phone")

    effective_status = vendor.partner_status or "active"
    if effective_status != "active":
        missing.append("active_status")

    if missing:
        return "incomplete", missing
    return "verified", []


# ============= SCHEMAS =============

class TradingPartnerCreate(BaseModel):
    name: str
    partner_type: Optional[str] = None
    status: str = "active"
    gln: Optional[str] = None
    dea_number: Optional[str] = None
    state_license_number: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("partner_type")
    @classmethod
    def validate_partner_type(cls, v):
        if v and v not in VALID_PARTNER_TYPES:
            raise ValueError(f"partner_type must be one of: {', '.join(VALID_PARTNER_TYPES)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v and v not in VALID_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(VALID_STATUSES)}")
        return v


class TradingPartnerUpdate(BaseModel):
    name: Optional[str] = None
    partner_type: Optional[str] = None
    status: Optional[str] = None
    gln: Optional[str] = None
    dea_number: Optional[str] = None
    state_license_number: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("partner_type")
    @classmethod
    def validate_partner_type(cls, v):
        if v and v not in VALID_PARTNER_TYPES:
            raise ValueError(f"partner_type must be one of: {', '.join(VALID_PARTNER_TYPES)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v and v not in VALID_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(VALID_STATUSES)}")
        return v


class TradingPartnerResponse(BaseModel):
    id: int
    name: str
    partner_type: Optional[str] = None
    status: str
    gln: Optional[str] = None
    dea_number: Optional[str] = None
    state_license_number: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    verification_status: str
    last_verified_at: Optional[datetime] = None
    missing_fields: List[str] = []
    data_source: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TradingPartnerListResponse(BaseModel):
    items: List[TradingPartnerResponse]
    total: int
    limit: int
    offset: int


class ReadinessSummary(BaseModel):
    total_trading_partners: int
    verified_partners: int
    incomplete_partners: int
    readiness_percentage: int


# ============= HELPERS =============

def _vendor_to_response(vendor: Vendor) -> TradingPartnerResponse:
    vs, missing = compute_readiness(vendor)
    return TradingPartnerResponse(
        id=vendor.id,
        name=vendor.name,
        partner_type=vendor.vendor_type,
        status=vendor.partner_status or "active",
        gln=vendor.gln,
        dea_number=vendor.dea_number,
        state_license_number=vendor.state_license_number,
        state=vendor.state,
        country=vendor.country,
        contact_name=vendor.contact_name,
        contact_email=vendor.contact_email,
        phone=vendor.contact_phone,
        address=vendor.address,
        notes=vendor.notes,
        verification_status=vs,
        last_verified_at=vendor.last_verified_at,
        missing_fields=missing,
        data_source=vendor.data_source,
        created_at=vendor.created_at,
        updated_at=vendor.updated_at,
    )


# ============= ROUTES =============

@router.get("/readiness", response_model=ReadinessSummary)
async def get_readiness_summary(
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    """Return DSCSA readiness stats for all trading partners."""
    partners = db.query(Vendor).filter(
        Vendor.organization_id == user_context["org_id"]
    ).all()

    total = len(partners)
    verified = 0
    incomplete = 0
    for p in partners:
        vs, _ = compute_readiness(p)
        if vs == "verified":
            verified += 1
        else:
            incomplete += 1

    pct = int(verified / total * 100) if total > 0 else 0
    return ReadinessSummary(
        total_trading_partners=total,
        verified_partners=verified,
        incomplete_partners=incomplete,
        readiness_percentage=pct,
    )


@router.get("", response_model=TradingPartnerListResponse)
async def list_trading_partners(
    search: Optional[str] = Query(None),
    partner_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    """List trading partners for the current organization."""
    query = db.query(Vendor).filter(
        Vendor.organization_id == user_context["org_id"]
    )

    if search:
        query = query.filter(
            or_(
                Vendor.name.ilike(f"%{search}%"),
                Vendor.contact_email.ilike(f"%{search}%"),
            )
        )

    if partner_type:
        query = query.filter(Vendor.vendor_type == partner_type)

    if status:
        query = query.filter(Vendor.partner_status == status)

    total = query.count()
    vendors = query.order_by(Vendor.name).offset(offset).limit(limit).all()

    return TradingPartnerListResponse(
        items=[_vendor_to_response(v) for v in vendors],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TradingPartnerResponse, status_code=201)
async def create_trading_partner(
    request: Request,
    data: TradingPartnerCreate,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """Create a new trading partner."""
    vendor = Vendor(
        organization_id=user_context["org_id"],
        name=data.name,
        vendor_type=data.partner_type,
        partner_status=data.status,
        gln=data.gln,
        dea_number=data.dea_number,
        state_license_number=data.state_license_number,
        state=data.state,
        country=data.country,
        contact_name=data.contact_name,
        contact_email=data.contact_email,
        contact_phone=data.phone,
        address=data.address,
        notes=data.notes,
        data_source="user_created",
    )
    db.add(vendor)

    audit = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="create_trading_partner",
        entity_type="vendor",
        details={"name": data.name, "partner_type": data.partner_type},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()
    db.refresh(vendor)

    return _vendor_to_response(vendor)


@router.get("/{partner_id}", response_model=TradingPartnerResponse)
async def get_trading_partner(
    partner_id: int,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    """Get a specific trading partner by ID."""
    vendor = db.query(Vendor).filter(
        Vendor.id == partner_id,
        Vendor.organization_id == user_context["org_id"],
    ).first()

    if not vendor:
        raise HTTPException(status_code=404, detail="Trading partner not found")

    return _vendor_to_response(vendor)


@router.patch("/{partner_id}", response_model=TradingPartnerResponse)
async def update_trading_partner(
    partner_id: int,
    request: Request,
    data: TradingPartnerUpdate,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """Update a trading partner (partial update)."""
    vendor = db.query(Vendor).filter(
        Vendor.id == partner_id,
        Vendor.organization_id == user_context["org_id"],
    ).first()

    if not vendor:
        raise HTTPException(status_code=404, detail="Trading partner not found")

    update_dict = data.model_dump(exclude_unset=True)

    field_map = {
        "partner_type": "vendor_type",
        "status": "partner_status",
        "phone": "contact_phone",
    }

    for key, value in update_dict.items():
        mapped = field_map.get(key, key)
        setattr(vendor, mapped, value)

    if update_dict:
        vendor.last_verified_at = None

    audit = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="update_trading_partner",
        entity_type="vendor",
        entity_id=partner_id,
        details=update_dict,
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()
    db.refresh(vendor)

    return _vendor_to_response(vendor)


@router.delete("/{partner_id}")
async def delete_trading_partner(
    partner_id: int,
    request: Request,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """Delete a trading partner."""
    vendor = db.query(Vendor).filter(
        Vendor.id == partner_id,
        Vendor.organization_id == user_context["org_id"],
    ).first()

    if not vendor:
        raise HTTPException(status_code=404, detail="Trading partner not found")

    name = vendor.name
    db.delete(vendor)

    audit = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="delete_trading_partner",
        entity_type="vendor",
        entity_id=partner_id,
        details={"name": name},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()

    return {"message": "Trading partner deleted"}
