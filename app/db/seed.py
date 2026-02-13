"""
Database seeding script for initial data.
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import random

from app.db.session import SessionLocal, init_db
from app.db.models import (
    Organization, User, Project, Vendor, Facility, 
    WatchtowerEvent, WatchtowerAlert, RiskLevel, UserRole
)
from app.core.security import get_password_hash


def seed_database():
    """Seed the database with initial data."""
    init_db()
    db = SessionLocal()
    
    try:
        # Check if already seeded
        if db.query(Organization).first():
            print("Database already seeded. Skipping...")
            return
        
        print("Seeding database...")
        
        # Create demo organization
        org = Organization(
            name="Acme Pharmaceuticals",
            slug="acme-pharma",
            settings={"timezone": "America/New_York"}
        )
        db.add(org)
        db.flush()
        
        # Create admin user
        admin = User(
            email="admin@acmepharma.com",
            hashed_password=get_password_hash("admin123"),
            full_name="System Administrator",
            role=UserRole.OWNER,
            organization_id=org.id,
            is_active=True
        )
        db.add(admin)
        
        # Create additional users
        users_data = [
            ("operator@acmepharma.com", "Operator User", UserRole.OPERATOR),
            ("viewer@acmepharma.com", "Viewer User", UserRole.VIEWER),
        ]
        for email, name, role in users_data:
            user = User(
                email=email,
                hashed_password=get_password_hash("password123"),
                full_name=name,
                role=role,
                organization_id=org.id,
            )
            db.add(user)
        
        # Create project
        project = Project(
            name="Q1 2025 Supply Chain",
            description="Main supply chain operations for Q1 2025",
            organization_id=org.id
        )
        db.add(project)
        
        # Create vendors
        vendors_data = [
            ("Teva Pharmaceuticals", "TEVA001", "API supplier", "United States", 25.0, RiskLevel.LOW),
            ("Sandoz Inc", "SAND001", "API supplier", "Germany", 45.0, RiskLevel.MEDIUM),
            ("Dr. Reddy's Laboratories", "DRL001", "API supplier", "India", 60.0, RiskLevel.HIGH),
            ("Capsugel", "CAPS001", "Packaging", "Belgium", 15.0, RiskLevel.LOW),
            ("Colorcon", "COLR001", "Excipient", "United States", 20.0, RiskLevel.LOW),
            ("BASF Pharma", "BASF001", "Excipient", "Germany", 35.0, RiskLevel.MEDIUM),
            ("Lonza", "LONZ001", "CMO", "Switzerland", 30.0, RiskLevel.LOW),
            ("Catalent", "CATL001", "CMO", "United States", 40.0, RiskLevel.MEDIUM),
        ]
        
        vendors = []
        for name, code, vtype, country, risk, level in vendors_data:
            vendor = Vendor(
                organization_id=org.id,
                name=name,
                vendor_code=code,
                vendor_type=vtype,
                country=country,
                risk_score=risk,
                risk_level=level,
                is_approved=True,
                contact_email=f"contact@{code.lower()}.com"
            )
            db.add(vendor)
            vendors.append(vendor)
        
        db.flush()
        
        # Create facilities
        facilities_data = [
            (vendors[0], "Teva Sellersville", "FAC001", "manufacturing", "United States", 20.0),
            (vendors[1], "Sandoz Kundl", "FAC002", "manufacturing", "Austria", 35.0),
            (vendors[2], "DRL Hyderabad", "FAC003", "manufacturing", "India", 55.0),
            (vendors[6], "Lonza Visp", "FAC004", "manufacturing", "Switzerland", 25.0),
        ]
        
        for vendor, name, code, ftype, country, risk in facilities_data:
            facility = Facility(
                organization_id=org.id,
                vendor_id=vendor.id,
                name=name,
                facility_code=code,
                facility_type=ftype,
                country=country,
                risk_score=risk,
                risk_level=RiskLevel.LOW if risk < 30 else (RiskLevel.MEDIUM if risk < 50 else RiskLevel.HIGH)
            )
            db.add(facility)
        
        db.flush()
        
        # Create Watchtower events
        events_data = [
            ("shortage", "fda", "SH-2024-001", "Amoxicillin Shortage", 
             "Ongoing shortage of Amoxicillin oral suspension due to increased demand.",
             RiskLevel.HIGH, ["Amoxicillin", "NDC: 0781-1234"], ["Sandoz Inc"]),
            ("recall", "fda", "RC-2024-042", "Class II Recall - Lisinopril",
             "Voluntary recall due to labeling issues on specific lot numbers.",
             RiskLevel.MEDIUM, ["Lisinopril 10mg"], ["Teva Pharmaceuticals"]),
            ("warning_letter", "fda", "WL-2024-088", "FDA Warning Letter - GMP Violations",
             "Warning letter issued for GMP violations at manufacturing facility.",
             RiskLevel.CRITICAL, [], ["Dr. Reddy's Laboratories"]),
            ("inspection", "fda", "INS-2024-200", "Form 483 Observations",
             "Routine inspection resulted in minor observations regarding documentation.",
             RiskLevel.LOW, [], ["Lonza"]),
            ("shortage", "fda", "SH-2024-015", "Adderall Supply Constraints",
             "Manufacturing capacity issues affecting Adderall supply.",
             RiskLevel.HIGH, ["Adderall", "Amphetamine salts"], ["Teva Pharmaceuticals"]),
        ]
        
        for etype, source, ext_id, title, desc, severity, products, companies in events_data:
            event = WatchtowerEvent(
                event_type=etype,
                source=source,
                external_id=ext_id,
                title=title,
                description=desc,
                severity=severity,
                affected_products=products,
                affected_companies=companies,
                event_date=datetime.utcnow() - timedelta(days=random.randint(1, 30))
            )
            db.add(event)
        
        db.flush()
        
        # Create alerts linking events to vendors
        events = db.query(WatchtowerEvent).all()
        for event in events:
            # Find matching vendor
            for company in event.affected_companies or []:
                for vendor in vendors:
                    if company.lower() in vendor.name.lower():
                        alert = WatchtowerAlert(
                            organization_id=org.id,
                            event_id=event.id,
                            vendor_id=vendor.id,
                            severity=event.severity,
                        )
                        db.add(alert)
                        break
        
        db.commit()
        print("Database seeded successfully!")
        print("\nDemo credentials:")
        print("  Email: admin@acmepharma.com")
        print("  Password: admin123")
        
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
