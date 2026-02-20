"""
Watchtower ingestion service for FDA events.
"""
from datetime import datetime, timedelta, timezone
import random
from typing import List, Dict, Any

from app.core.logging import get_logger
from app.db.session import get_db_context
from app.db.models import WatchtowerEvent, WatchtowerAlert, Vendor, RiskLevel

logger = get_logger(__name__)


def ingest_fda_events():
    """Ingest FDA enforcement/shortage events (scheduled job)."""
    with get_db_context() as db:
        try:
            # Try to fetch real FDA data
            events = fetch_fda_enforcement_events()
            events.extend(fetch_fda_shortage_events())
            
            if not events:
                logger.info("No new events from FDA API, using seed data")
                events = generate_seed_events()
            
            added = 0
            for event_data in events:
                existing = db.query(WatchtowerEvent).filter(
                    WatchtowerEvent.source == event_data["source"],
                    WatchtowerEvent.external_id == event_data["external_id"]
                ).first()
                
                if existing:
                    continue
                
                event = WatchtowerEvent(
                    event_type=event_data["event_type"],
                    source=event_data["source"],
                    external_id=event_data["external_id"],
                    title=event_data["title"],
                    description=event_data["description"],
                    severity=RiskLevel(event_data.get("severity", "medium")),
                    affected_products=event_data.get("affected_products", []),
                    affected_companies=event_data.get("affected_companies", []),
                    event_date=event_data.get("event_date"),
                    source_url=event_data.get("source_url"),
                    raw_data=event_data.get("raw_data"),
                )
                db.add(event)
                db.flush()
                
                # Create alerts for matching vendors
                create_vendor_alerts(db, event)
                added += 1
            
            db.commit()
            logger.info(f"Ingested {added} new Watchtower events")
            
        except Exception as e:
            logger.error(f"Watchtower ingestion failed: {e}")
            db.rollback()


def fetch_fda_enforcement_events() -> List[Dict[str, Any]]:
    """Fetch FDA enforcement events via API."""
    try:
        import requests
        response = requests.get(
            "https://api.fda.gov/drug/enforcement.json",
            params={"limit": 20, "sort": "report_date:desc"},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            events = []
            for item in data.get("results", []):
                events.append({
                    "event_type": "recall",
                    "source": "fda",
                    "external_id": item.get("recall_number", item.get("event_id")),
                    "title": f"Recall: {item.get('product_description', 'Unknown')[:100]}",
                    "description": item.get("reason_for_recall", ""),
                    "severity": _map_recall_class(item.get("classification")),
                    "affected_products": [item.get("product_description", "Unknown")],
                    "affected_companies": [item.get("recalling_firm", "Unknown")],
                    "event_date": _parse_fda_date(item.get("report_date")),
                    "source_url": f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRES/res.cfm?id={item.get('recall_number', '')}",
                    "raw_data": item,
                })
            return events
    except Exception as e:
        logger.warning(f"FDA enforcement API error: {e}")
    return []


def fetch_fda_shortage_events() -> List[Dict[str, Any]]:
    """Fetch FDA drug shortage events."""
    try:
        import requests
        response = requests.get(
            "https://api.fda.gov/drug/drugsfda.json",
            params={"limit": 10, "search": "products.active_ingredients.name:*"},
            timeout=10
        )
        # Note: FDA shortage API is limited; this is a placeholder
    except Exception as e:
        logger.warning(f"FDA shortage API error: {e}")
    return []


def generate_seed_events() -> List[Dict[str, Any]]:
    """Generate seed events for demo purposes."""
    return [
        {
            "event_type": "shortage",
            "source": "fda_seed",
            "external_id": f"SH-SEED-{datetime.now(timezone.utc).strftime('%Y%m%d')}-001",
            "title": "Ongoing API Supply Constraint - Metformin",
            "description": "Multiple manufacturers reporting reduced capacity for metformin HCl API.",
            "severity": "high",
            "affected_products": ["Metformin HCl", "Metformin ER"],
            "affected_companies": ["Multiple manufacturers"],
            "event_date": datetime.now(timezone.utc) - timedelta(days=random.randint(1, 5)),
        },
        {
            "event_type": "warning_letter",
            "source": "fda_seed",
            "external_id": f"WL-SEED-{datetime.now(timezone.utc).strftime('%Y%m%d')}-001",
            "title": "Warning Letter - GMP Violations at API Facility",
            "description": "FDA issued warning letter citing multiple GMP violations.",
            "severity": "critical",
            "affected_products": [],
            "affected_companies": ["Seed Pharma API"],
            "event_date": datetime.now(timezone.utc) - timedelta(days=random.randint(1, 10)),
        },
    ]


def create_vendor_alerts(db, event: WatchtowerEvent):
    """Create alerts linking event to matching vendors."""
    vendors = db.query(Vendor).all()
    for vendor in vendors:
        if _vendor_matches_event(vendor, event):
            existing = db.query(WatchtowerAlert).filter(
                WatchtowerAlert.event_id == event.id,
                WatchtowerAlert.vendor_id == vendor.id
            ).first()
            if not existing:
                alert = WatchtowerAlert(
                    organization_id=vendor.organization_id,
                    event_id=event.id,
                    vendor_id=vendor.id,
                    severity=event.severity,
                )
                db.add(alert)


def _vendor_matches_event(vendor: Vendor, event: WatchtowerEvent) -> bool:
    """Check if vendor is affected by event."""
    for company in (event.affected_companies or []):
        if company.lower() in vendor.name.lower() or vendor.name.lower() in company.lower():
            return True
    return False


def _map_recall_class(classification: str) -> str:
    """Map FDA recall classification to risk level."""
    if not classification:
        return "medium"
    if "I" in classification and "II" not in classification:
        return "critical"
    elif "II" in classification:
        return "high"
    return "medium"


def _parse_fda_date(date_str: str) -> datetime:
    """Parse FDA date format."""
    if not date_str:
        return datetime.now(timezone.utc)
    try:
        return datetime.strptime(date_str[:8], "%Y%m%d")
    except:
        return datetime.now(timezone.utc)
