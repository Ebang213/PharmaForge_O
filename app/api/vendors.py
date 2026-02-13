"""
Vendors API routes.
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.db.session import get_db
from app.db.models import Vendor, Facility, AuditLog, RiskLevel
from app.core.rbac import require_operator, get_current_user_context

router = APIRouter(prefix="/api/vendors", tags=["Vendors"])


def get_risk_level_str(risk_level) -> str:
    """
    Safely extract risk_level as a string.
    
    Handles both enum instances (RiskLevel.LOW) and string values ("low").
    This is needed because PostgreSQL stores enums as strings, and depending
    on how the data was loaded, it may or may not be deserialized as an enum.
    """
    if risk_level is None:
        return "low"
    if hasattr(risk_level, 'value'):
        return risk_level.value
    return str(risk_level)


# ============= SCHEMAS =============

class VendorCreate(BaseModel):
    name: str
    vendor_code: Optional[str] = None
    vendor_type: Optional[str] = None
    duns_number: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    vendor_code: Optional[str] = None
    vendor_type: Optional[str] = None
    duns_number: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    is_approved: Optional[bool] = None
    notes: Optional[str] = None
    metadata: Optional[dict] = None


class VendorResponse(BaseModel):
    id: int
    name: str
    vendor_code: Optional[str]
    vendor_type: Optional[str]
    duns_number: Optional[str]
    address: Optional[str]
    country: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    risk_score: float
    risk_level: str
    is_approved: bool
    approval_date: Optional[datetime]
    last_audit_date: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    facility_count: int = 0
    alert_count: int = 0
    
    class Config:
        orm_mode = True


class FacilityCreate(BaseModel):
    name: str
    facility_code: Optional[str] = None
    facility_type: Optional[str] = None
    fei_number: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    gmp_status: Optional[str] = None


class FacilityResponse(BaseModel):
    id: int
    vendor_id: Optional[int]
    name: str
    facility_code: Optional[str]
    facility_type: Optional[str]
    fei_number: Optional[str]
    address: Optional[str]
    country: Optional[str]
    gmp_status: Optional[str]
    risk_score: float
    risk_level: str
    last_inspection_date: Optional[datetime]
    
    class Config:
        orm_mode = True


# ============= VENDOR ROUTES =============

@router.get("", response_model=List[VendorResponse])
async def list_vendors(
    search: Optional[str] = Query(None, description="Search by name or code"),
    vendor_type: Optional[str] = Query(None, description="Filter by type"),
    risk_level: Optional[str] = Query(None, description="Filter by risk level"),
    approved_only: bool = Query(False, description="Show only approved vendors"),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """List vendors in current organization."""
    query = db.query(Vendor).filter(
        Vendor.organization_id == user_context["org_id"]
    )
    
    if search:
        query = query.filter(
            or_(
                Vendor.name.ilike(f"%{search}%"),
                Vendor.vendor_code.ilike(f"%{search}%")
            )
        )
    
    if vendor_type:
        query = query.filter(Vendor.vendor_type == vendor_type)
    
    if risk_level:
        query = query.filter(Vendor.risk_level == RiskLevel(risk_level))
    
    if approved_only:
        query = query.filter(Vendor.is_approved == True)
    
    vendors = query.order_by(Vendor.name).all()
    
    # Add counts
    result = []
    for v in vendors:
        vendor_dict = {
            "id": v.id,
            "name": v.name,
            "vendor_code": v.vendor_code,
            "vendor_type": v.vendor_type,
            "duns_number": v.duns_number,
            "address": v.address,
            "country": v.country,
            "contact_email": v.contact_email,
            "contact_phone": v.contact_phone,
            "risk_score": v.risk_score,
            "risk_level": get_risk_level_str(v.risk_level),
            "is_approved": v.is_approved,
            "approval_date": v.approval_date,
            "last_audit_date": v.last_audit_date,
            "notes": v.notes,
            "created_at": v.created_at,
            "facility_count": len(v.facilities) if v.facilities else 0,
            "alert_count": len([a for a in v.alerts if not a.is_acknowledged]) if v.alerts else 0,
        }
        result.append(vendor_dict)
    
    return result


@router.post("", response_model=VendorResponse)
async def create_vendor(
    request: Request,
    vendor_data: VendorCreate,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Create a new vendor."""
    vendor = Vendor(
        organization_id=user_context["org_id"],
        name=vendor_data.name,
        vendor_code=vendor_data.vendor_code,
        vendor_type=vendor_data.vendor_type,
        duns_number=vendor_data.duns_number,
        address=vendor_data.address,
        country=vendor_data.country,
        contact_email=vendor_data.contact_email,
        contact_phone=vendor_data.contact_phone,
        notes=vendor_data.notes,
    )
    db.add(vendor)
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="create_vendor",
        entity_type="vendor",
        details={"name": vendor_data.name},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(vendor)
    
    return VendorResponse(
        id=vendor.id,
        name=vendor.name,
        vendor_code=vendor.vendor_code,
        vendor_type=vendor.vendor_type,
        duns_number=vendor.duns_number,
        address=vendor.address,
        country=vendor.country,
        contact_email=vendor.contact_email,
        contact_phone=vendor.contact_phone,
        risk_score=vendor.risk_score,
        risk_level=get_risk_level_str(vendor.risk_level),
        is_approved=vendor.is_approved,
        approval_date=vendor.approval_date,
        last_audit_date=vendor.last_audit_date,
        notes=vendor.notes,
        created_at=vendor.created_at,
        facility_count=0,
        alert_count=0,
    )


@router.get("/{vendor_id}", response_model=VendorResponse)
async def get_vendor(
    vendor_id: int,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Get a specific vendor."""
    vendor = db.query(Vendor).filter(
        Vendor.id == vendor_id,
        Vendor.organization_id == user_context["org_id"]
    ).first()
    
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    return VendorResponse(
        id=vendor.id,
        name=vendor.name,
        vendor_code=vendor.vendor_code,
        vendor_type=vendor.vendor_type,
        duns_number=vendor.duns_number,
        address=vendor.address,
        country=vendor.country,
        contact_email=vendor.contact_email,
        contact_phone=vendor.contact_phone,
        risk_score=vendor.risk_score,
        risk_level=get_risk_level_str(vendor.risk_level),
        is_approved=vendor.is_approved,
        approval_date=vendor.approval_date,
        last_audit_date=vendor.last_audit_date,
        notes=vendor.notes,
        created_at=vendor.created_at,
        facility_count=len(vendor.facilities) if vendor.facilities else 0,
        alert_count=len([a for a in vendor.alerts if not a.is_acknowledged]) if vendor.alerts else 0,
    )


@router.put("/{vendor_id}", response_model=VendorResponse)
async def update_vendor(
    vendor_id: int,
    request: Request,
    update_data: VendorUpdate,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Update a vendor."""
    vendor = db.query(Vendor).filter(
        Vendor.id == vendor_id,
        Vendor.organization_id == user_context["org_id"]
    ).first()
    
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    update_dict = update_data.dict(exclude_unset=True)
    for key, value in update_dict.items():
        if value is not None:
            setattr(vendor, key, value)
    
    if update_data.is_approved is True and vendor.approval_date is None:
        vendor.approval_date = datetime.utcnow()
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="update_vendor",
        entity_type="vendor",
        entity_id=vendor_id,
        details=update_dict,
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(vendor)
    
    return VendorResponse(
        id=vendor.id,
        name=vendor.name,
        vendor_code=vendor.vendor_code,
        vendor_type=vendor.vendor_type,
        duns_number=vendor.duns_number,
        address=vendor.address,
        country=vendor.country,
        contact_email=vendor.contact_email,
        contact_phone=vendor.contact_phone,
        risk_score=vendor.risk_score,
        risk_level=get_risk_level_str(vendor.risk_level),
        is_approved=vendor.is_approved,
        approval_date=vendor.approval_date,
        last_audit_date=vendor.last_audit_date,
        notes=vendor.notes,
        created_at=vendor.created_at,
        facility_count=len(vendor.facilities) if vendor.facilities else 0,
        alert_count=len([a for a in vendor.alerts if not a.is_acknowledged]) if vendor.alerts else 0,
    )


@router.delete("/{vendor_id}")
async def delete_vendor(
    vendor_id: int,
    request: Request,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Delete a vendor."""
    vendor = db.query(Vendor).filter(
        Vendor.id == vendor_id,
        Vendor.organization_id == user_context["org_id"]
    ).first()
    
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    vendor_name = vendor.name
    db.delete(vendor)
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="delete_vendor",
        entity_type="vendor",
        entity_id=vendor_id,
        details={"name": vendor_name},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    
    return {"message": "Vendor deleted successfully"}


# ============= FACILITY ROUTES =============

@router.get("/{vendor_id}/facilities", response_model=List[FacilityResponse])
async def list_vendor_facilities(
    vendor_id: int,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """List facilities for a vendor."""
    vendor = db.query(Vendor).filter(
        Vendor.id == vendor_id,
        Vendor.organization_id == user_context["org_id"]
    ).first()
    
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    return [
        FacilityResponse(
            id=f.id,
            vendor_id=f.vendor_id,
            name=f.name,
            facility_code=f.facility_code,
            facility_type=f.facility_type,
            fei_number=f.fei_number,
            address=f.address,
            country=f.country,
            gmp_status=f.gmp_status,
            risk_score=f.risk_score,
            risk_level=get_risk_level_str(f.risk_level),
            last_inspection_date=f.last_inspection_date,
        )
        for f in vendor.facilities
    ]


@router.post("/{vendor_id}/facilities", response_model=FacilityResponse)
async def create_facility(
    vendor_id: int,
    request: Request,
    facility_data: FacilityCreate,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Create a facility for a vendor."""
    vendor = db.query(Vendor).filter(
        Vendor.id == vendor_id,
        Vendor.organization_id == user_context["org_id"]
    ).first()
    
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    facility = Facility(
        organization_id=user_context["org_id"],
        vendor_id=vendor_id,
        name=facility_data.name,
        facility_code=facility_data.facility_code,
        facility_type=facility_data.facility_type,
        fei_number=facility_data.fei_number,
        address=facility_data.address,
        country=facility_data.country,
        gmp_status=facility_data.gmp_status,
    )
    db.add(facility)
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="create_facility",
        entity_type="facility",
        details={"vendor_id": vendor_id, "name": facility_data.name},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(facility)
    
    return FacilityResponse(
        id=facility.id,
        vendor_id=facility.vendor_id,
        name=facility.name,
        facility_code=facility.facility_code,
        facility_type=facility.facility_type,
        fei_number=facility.fei_number,
        address=facility.address,
        country=facility.country,
        gmp_status=facility.gmp_status,
        risk_score=facility.risk_score,
        risk_level=get_risk_level_str(facility.risk_level),
        last_inspection_date=facility.last_inspection_date,
    )
