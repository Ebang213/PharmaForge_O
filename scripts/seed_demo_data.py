"""
Seed demo data for Risk Intelligence Loop verification.
Creates 3 vendors, 1 facility, and 1 sample evidence file.
Run: python -m scripts.seed_demo_data
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.db.models import (
    Organization, User, Vendor, Facility, Evidence, 
    RiskLevel, UserRole
)
from app.core.security import hash_password
import hashlib


def seed_demo_data():
    """Create demo data for verification."""
    db = SessionLocal()
    
    try:
        # 1. Check/create organization
        org = db.query(Organization).filter(Organization.slug == "acme-pharma").first()
        if not org:
            org = Organization(
                name="Acme Pharma",
                slug="acme-pharma",
                settings={"timezone": "America/New_York"}
            )
            db.add(org)
            db.flush()
            print(f"✅ Created organization: {org.name} (ID: {org.id})")
        else:
            print(f"✓ Organization exists: {org.name} (ID: {org.id})")
        
        # 2. Check/create admin user
        admin = db.query(User).filter(User.email == "admin@acmepharma.com").first()
        if not admin:
            admin = User(
                email="admin@acmepharma.com",
                hashed_password=hash_password("admin123"),
                full_name="Demo Admin",
                role=UserRole.ADMIN,
                organization_id=org.id,
                is_active=True
            )
            db.add(admin)
            db.flush()
            print(f"✅ Created admin user: {admin.email} (ID: {admin.id})")
        else:
            print(f"✓ Admin user exists: {admin.email} (ID: {admin.id})")
        
        # 3. Create 3 vendors
        vendor_data = [
            {
                "name": "PharmaChem Supplies",
                "vendor_code": "VND-001",
                "vendor_type": "API Supplier",
                "country": "India",
                "contact_email": "orders@pharmachem.example.com",
                "risk_score": 35.0,
                "risk_level": RiskLevel.MEDIUM,
                "is_approved": True
            },
            {
                "name": "BioLabs Inc",
                "vendor_code": "VND-002",
                "vendor_type": "Excipient Manufacturer",
                "country": "Germany",
                "contact_email": "supply@biolabs.example.com",
                "risk_score": 15.0,
                "risk_level": RiskLevel.LOW,
                "is_approved": True
            },
            {
                "name": "MedPack Solutions",
                "vendor_code": "VND-003",
                "vendor_type": "Packaging",
                "country": "China",
                "contact_email": "sales@medpack.example.com",
                "risk_score": 68.0,
                "risk_level": RiskLevel.HIGH,
                "is_approved": False
            }
        ]
        
        created_vendors = 0
        for vd in vendor_data:
            existing = db.query(Vendor).filter(
                Vendor.organization_id == org.id,
                Vendor.vendor_code == vd["vendor_code"]
            ).first()
            if not existing:
                vendor = Vendor(organization_id=org.id, **vd)
                db.add(vendor)
                created_vendors += 1
        
        if created_vendors > 0:
            db.flush()
            print(f"✅ Created {created_vendors} new vendors")
        else:
            print(f"✓ All 3 vendors already exist")
        
        # 4. Create 1 facility
        facility = db.query(Facility).filter(
            Facility.organization_id == org.id,
            Facility.facility_code == "FAC-001"
        ).first()
        if not facility:
            # Get first vendor for linking
            first_vendor = db.query(Vendor).filter(
                Vendor.organization_id == org.id
            ).first()
            
            facility = Facility(
                organization_id=org.id,
                vendor_id=first_vendor.id if first_vendor else None,
                name="PharmaChem Mumbai Plant",
                facility_code="FAC-001",
                facility_type="manufacturing",
                fei_number="3012345678",
                country="India",
                gmp_status="Approved",
                risk_score=40.0,
                risk_level=RiskLevel.MEDIUM
            )
            db.add(facility)
            db.flush()
            print(f"✅ Created facility: {facility.name}")
        else:
            print(f"✓ Facility exists: {facility.name}")
        
        # 5. Create sample evidence file
        sample_text = """
Sample FDA Warning Letter Evidence

To: PharmaChem Supplies
Re: Warning Letter - cGMP Violations

This warning letter documents cGMP violations observed during our inspection
of your pharmaceutical manufacturing facility.

Key Findings:
1. Temperature deviations in cold storage areas (21 CFR 211.142)
2. Inadequate supplier qualification procedures (21 CFR 211.84)
3. Missing batch records for lot #BATCH-2025-001
4. Inadequate deviation investigation procedures (21 CFR 211.192)

Affected Products:
- Acetaminophen API (Lot: ACET-2025-001)
- Ibuprofen API (Lot: IBU-2025-002)

You must respond within 15 business days with a corrective action plan.

Signed,
FDA Office of Regulatory Affairs
"""
        
        sample_hash = hashlib.sha256(sample_text.encode()).hexdigest()
        evidence = db.query(Evidence).filter(
            Evidence.organization_id == org.id,
            Evidence.sha256 == sample_hash
        ).first()
        
        if not evidence:
            # Create storage directory
            storage_dir = "/tmp/pharmaforge/evidence"
            os.makedirs(storage_dir, exist_ok=True)
            storage_path = os.path.join(storage_dir, f"{sample_hash}_sample_warning_letter.txt")
            
            with open(storage_path, "w") as f:
                f.write(sample_text)
            
            evidence = Evidence(
                organization_id=org.id,
                filename="sample_warning_letter.txt",
                content_type="text/plain",
                storage_path=storage_path,
                sha256=sample_hash,
                uploaded_by=admin.id,
                extracted_text=sample_text,
                source="copilot"
            )
            db.add(evidence)
            db.flush()
            print(f"✅ Created sample evidence: {evidence.filename} (ID: {evidence.id})")
        else:
            print(f"✓ Sample evidence exists: {evidence.filename} (ID: {evidence.id})")
        
        db.commit()
        
        print("\n" + "="*60)
        print("DEMO DATA SEED COMPLETE")
        print("="*60)
        print(f"""
Summary:
- Organization: Acme Pharma
- Admin User: admin@acmepharma.com / admin123
- Vendors: 3 (PharmaChem, BioLabs, MedPack)
- Facilities: 1 (Mumbai Plant)
- Evidence: 1 sample warning letter

You can now test the Golden Loop:
1. Login at http://localhost:5173
2. Go to Mission Control > Start Here
3. Select the sample evidence
4. Run Findings -> Correlate -> Generate Plan -> Export
""")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()
