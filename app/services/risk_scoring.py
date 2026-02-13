"""
Risk scoring service for vendors and facilities.
"""
from typing import Tuple
from sqlalchemy.orm import Session

from app.db.models import Vendor, Facility, WatchtowerAlert, RiskLevel


def calculate_vendor_risk(db: Session, vendor: Vendor) -> Tuple[float, RiskLevel]:
    """
    Calculate risk score for a vendor based on alerts and other factors.
    
    Returns:
        Tuple of (risk_score: 0-100, risk_level: RiskLevel)
    """
    base_score = 10.0  # Base risk score
    
    # Factor 1: Active alerts
    active_alerts = db.query(WatchtowerAlert).filter(
        WatchtowerAlert.vendor_id == vendor.id,
        WatchtowerAlert.is_acknowledged == False
    ).all()
    
    for alert in active_alerts:
        if alert.severity == RiskLevel.CRITICAL:
            base_score += 30
        elif alert.severity == RiskLevel.HIGH:
            base_score += 20
        elif alert.severity == RiskLevel.MEDIUM:
            base_score += 10
        else:
            base_score += 5
    
    # Factor 2: Country risk (simplified)
    high_risk_countries = ["China", "India", "Brazil", "Russia"]
    medium_risk_countries = ["Mexico", "Turkey", "Indonesia"]
    
    if vendor.country in high_risk_countries:
        base_score += 15
    elif vendor.country in medium_risk_countries:
        base_score += 8
    
    # Factor 3: Approval status
    if not vendor.is_approved:
        base_score += 20
    
    # Factor 4: Time since last audit
    from datetime import datetime, timedelta
    if vendor.last_audit_date:
        days_since_audit = (datetime.utcnow() - vendor.last_audit_date).days
        if days_since_audit > 365 * 2:  # 2+ years
            base_score += 15
        elif days_since_audit > 365:  # 1+ years
            base_score += 8
    else:
        base_score += 10  # No audit on record
    
    # Normalize to 0-100
    risk_score = min(100, max(0, base_score))
    
    # Determine risk level
    if risk_score >= 70:
        risk_level = RiskLevel.CRITICAL
    elif risk_score >= 50:
        risk_level = RiskLevel.HIGH
    elif risk_score >= 25:
        risk_level = RiskLevel.MEDIUM
    else:
        risk_level = RiskLevel.LOW
    
    return risk_score, risk_level


def calculate_facility_risk(db: Session, facility: Facility) -> Tuple[float, RiskLevel]:
    """
    Calculate risk score for a facility based on alerts and factors.
    
    Returns:
        Tuple of (risk_score: 0-100, risk_level: RiskLevel)
    """
    base_score = 10.0
    
    # Factor 1: Active alerts
    active_alerts = db.query(WatchtowerAlert).filter(
        WatchtowerAlert.facility_id == facility.id,
        WatchtowerAlert.is_acknowledged == False
    ).all()
    
    for alert in active_alerts:
        if alert.severity == RiskLevel.CRITICAL:
            base_score += 30
        elif alert.severity == RiskLevel.HIGH:
            base_score += 20
        elif alert.severity == RiskLevel.MEDIUM:
            base_score += 10
        else:
            base_score += 5
    
    # Factor 2: GMP status
    if facility.gmp_status:
        status = facility.gmp_status.lower()
        if "warning" in status or "483" in status:
            base_score += 25
        elif "pending" in status or "expired" in status:
            base_score += 15
    else:
        base_score += 10
    
    # Factor 3: Country risk
    high_risk_countries = ["China", "India", "Brazil", "Russia"]
    medium_risk_countries = ["Mexico", "Turkey", "Indonesia"]
    
    if facility.country in high_risk_countries:
        base_score += 12
    elif facility.country in medium_risk_countries:
        base_score += 6
    
    # Factor 4: Time since last inspection
    from datetime import datetime
    if facility.last_inspection_date:
        days_since = (datetime.utcnow() - facility.last_inspection_date).days
        if days_since > 365 * 3:  # 3+ years
            base_score += 20
        elif days_since > 365 * 2:  # 2+ years
            base_score += 12
        elif days_since > 365:  # 1+ years
            base_score += 5
    else:
        base_score += 15
    
    # Factor 5: Parent vendor risk
    if facility.vendor:
        vendor_risk = facility.vendor.risk_score or 0
        base_score += vendor_risk * 0.2
    
    # Normalize
    risk_score = min(100, max(0, base_score))
    
    # Determine level
    if risk_score >= 70:
        risk_level = RiskLevel.CRITICAL
    elif risk_score >= 50:
        risk_level = RiskLevel.HIGH
    elif risk_score >= 25:
        risk_level = RiskLevel.MEDIUM
    else:
        risk_level = RiskLevel.LOW
    
    return risk_score, risk_level


def get_risk_factors(db: Session, vendor: Vendor) -> dict:
    """
    Get detailed breakdown of risk factors for a vendor.
    """
    factors = []
    
    # Active alerts
    active_alerts = db.query(WatchtowerAlert).filter(
        WatchtowerAlert.vendor_id == vendor.id,
        WatchtowerAlert.is_acknowledged == False
    ).all()
    
    if active_alerts:
        for alert in active_alerts:
            factors.append({
                "factor": "Active Alert",
                "description": f"{alert.severity.value.upper()} severity alert",
                "impact": "high" if alert.severity in [RiskLevel.CRITICAL, RiskLevel.HIGH] else "medium",
            })
    
    # Country
    high_risk_countries = ["China", "India", "Brazil", "Russia"]
    if vendor.country in high_risk_countries:
        factors.append({
            "factor": "Country Risk",
            "description": f"Located in {vendor.country} (elevated geopolitical risk)",
            "impact": "medium",
        })
    
    # Approval
    if not vendor.is_approved:
        factors.append({
            "factor": "Approval Status",
            "description": "Vendor not yet approved",
            "impact": "high",
        })
    
    # Last audit
    from datetime import datetime
    if vendor.last_audit_date:
        days_since = (datetime.utcnow() - vendor.last_audit_date).days
        if days_since > 365:
            factors.append({
                "factor": "Audit Age",
                "description": f"Last audit was {days_since} days ago",
                "impact": "medium" if days_since < 730 else "high",
            })
    else:
        factors.append({
            "factor": "No Audit Record",
            "description": "No audit has been recorded for this vendor",
            "impact": "medium",
        })
    
    return {
        "vendor_id": vendor.id,
        "vendor_name": vendor.name,
        "current_risk_score": vendor.risk_score,
        "current_risk_level": vendor.risk_level.value if vendor.risk_level else "unknown",
        "factors": factors,
    }
