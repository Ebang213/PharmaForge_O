"""
Database session management with SQLAlchemy.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from contextlib import contextmanager

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for database session."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """
    Initialize database connection and run startup tasks.
    
    IMPORTANT: Schema is managed by Alembic migrations, NOT create_all().
    Run `alembic upgrade head` before first startup.
    
    Startup order:
    1. Run preflight check (validates DB connectivity)
    2. Verify schema exists (tables were created by Alembic)
    3. Bootstrap admin if ADMIN_BOOTSTRAP_* env vars set and no users exist
    4. Seed demo data ONLY if SEED_DEMO=true (never in production)
    """
    from sqlalchemy import inspect, text
    
    # Run preflight check first - exits if DB is unreachable
    from app.db.preflight import run_db_preflight
    run_db_preflight()
    
    # Import models to register them (but don't create tables)
    from app.db import models  # noqa
    
    # Verify schema exists - tables should be created by Alembic migration
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    required_tables = ['organizations', 'users']  # Core tables that must exist
    
    missing = [t for t in required_tables if t not in existing_tables]
    if missing:
        print("=" * 60)
        print("⚠️  DATABASE SCHEMA MISSING")
        print("-" * 60)
        print(f"Missing required tables: {missing}")
        print("")
        print("To fix this, run the Alembic migrations:")
        print("   docker exec pharmaforge_api sh -c 'cd /code && alembic upgrade head'")
        print("")
        print("Then restart the API container:")
        print("   docker-compose -f docker-compose.prod.yml restart api")
        print("=" * 60)
        
        # In development mode, create tables automatically
        if settings.DEBUG:
            print("DEBUG=true: Auto-creating tables (NOT for production!)")
            Base.metadata.create_all(bind=engine)
        else:
            # In production, we don't auto-create - require explicit migration
            # Application will fail gracefully on API calls
            print("Production mode: Waiting for migrations to be run...")
            return  # Exit early, don't try to bootstrap
    else:
        print(f"✅ Database schema verified: {len(existing_tables)} tables found")
    
    # Check for Alembic version table to verify migrations ran
    if 'alembic_version' in existing_tables:
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                version = result.scalar()
                print(f"✅ Alembic migration version: {version}")
        except Exception as e:
            print(f"⚠️  Could not read migration version: {e}")
    else:
        print("⚠️  alembic_version table not found - migrations may not have been run")
    
    # Always try admin bootstrap first (production path)
    bootstrap_admin()
    
    # Only seed demo data if explicitly enabled
    if settings.SEED_DEMO:
        print("SEED_DEMO=true: Seeding demo data...")
        seed_demo_data()
    else:
        print("SEED_DEMO=false: Skipping demo data seeding (production mode)")



def bootstrap_admin():
    """
    Bootstrap initial admin user from environment variables.
    
    This is the production-safe way to create the first admin user.
    Only runs if:
    - ADMIN_BOOTSTRAP_EMAIL and ADMIN_BOOTSTRAP_PASSWORD are set
    - No users exist in the database yet
    
    Completely idempotent - does nothing if users already exist.
    """
    from app.db.models import Organization, User, UserRole
    from app.core.security import get_password_hash
    
    email = settings.ADMIN_BOOTSTRAP_EMAIL
    password = settings.ADMIN_BOOTSTRAP_PASSWORD
    
    if not email or not password:
        print("Admin bootstrap: ADMIN_BOOTSTRAP_EMAIL/PASSWORD not set. Skipping.")
        return
    
    # Validate password strength
    if len(password) < 10:
        print("WARNING: ADMIN_BOOTSTRAP_PASSWORD must be at least 10 characters. Skipping bootstrap.")
        return
    
    db = SessionLocal()
    try:
        # Check if any users exist
        existing_user = db.query(User).first()
        if existing_user:
            print(f"Admin bootstrap: Users already exist (e.g., {existing_user.email}). Skipping bootstrap.")
            return
        
        # Check if organization exists, create if not
        org = db.query(Organization).first()
        if not org:
            org = Organization(
                name="PharmaForge",
                slug="pharmaforge",
                settings={"timezone": "UTC"}
            )
            db.add(org)
            db.flush()
        
        # Create bootstrap admin
        admin = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name="Administrator",
            role=UserRole.OWNER.value,  # Use .value to get lowercase string for Postgres enum
            organization_id=org.id,
            is_active=True
        )
        db.add(admin)
        db.commit()
        
        print(f"✅ Bootstrap admin created: {email}")
        print("IMPORTANT: Change this password immediately after first login!")
        
    except Exception as e:
        db.rollback()
        print(f"Bootstrap error: {e}")
    finally:
        db.close()



def seed_demo_data():
    """
    Seed demo data for development/testing ONLY.
    
    WARNING: This creates predictable demo credentials.
    NEVER enable SEED_DEMO=true in production!
    """
    from datetime import datetime, timedelta, timezone
    import random
    from app.db.models import (
        Organization, User, UserRole, Vendor, Facility,
        WatchtowerEvent, WatchtowerAlert, RiskLevel
    )
    from app.core.security import get_password_hash
    
    db = SessionLocal()
    try:
        # Check if already seeded (has vendors = full demo data exists)
        if db.query(Vendor).first():
            print("Demo data already exists. Skipping...")
            return
        
        # Get or create organization  
        org = db.query(Organization).first()
        if not org:
            org = Organization(
                name="Acme Pharmaceuticals (DEMO)",
                slug="acme-pharma-demo",
                settings={"timezone": "America/New_York"}
            )
            db.add(org)
            db.flush()
        
        # Create demo admin if no users exist
        if not db.query(User).first():
            # Only create demo user in demo seed mode
            demo_admin = User(
                email="demo@example.com",
                hashed_password=get_password_hash("demo1234567"),
                full_name="Demo Administrator",
                role=UserRole.OWNER.value,
                organization_id=org.id,
                is_active=True
            )
            db.add(demo_admin)
            print("Created demo user: demo@example.com / demo1234567")
        
        # Create vendors
        vendors_data = [
            ("Teva Pharmaceuticals", "TEVA001", "API supplier", "United States", 25.0, RiskLevel.LOW.value),
            ("Sandoz Inc", "SAND001", "API supplier", "Germany", 45.0, RiskLevel.MEDIUM.value),
            ("Dr. Reddy's Laboratories", "DRL001", "API supplier", "India", 60.0, RiskLevel.HIGH.value),
            ("Capsugel", "CAPS001", "Packaging", "Belgium", 15.0, RiskLevel.LOW.value),
            ("Colorcon", "COLR001", "Excipient", "United States", 20.0, RiskLevel.LOW.value),
            ("BASF Pharma", "BASF001", "Excipient", "Germany", 35.0, RiskLevel.MEDIUM.value),
            ("Lonza", "LONZ001", "CMO", "Switzerland", 30.0, RiskLevel.LOW.value),
            ("Catalent", "CATL001", "CMO", "United States", 40.0, RiskLevel.MEDIUM.value),
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
                risk_level=RiskLevel.LOW.value if risk < 30 else (RiskLevel.MEDIUM.value if risk < 50 else RiskLevel.HIGH.value)
            )
            db.add(facility)
        
        db.flush()
        
        # Create Watchtower events
        events_data = [
            ("shortage", "fda", "SH-2024-001", "Amoxicillin Shortage", 
             "Ongoing shortage of Amoxicillin oral suspension due to increased demand.",
             RiskLevel.HIGH.value, ["Amoxicillin", "NDC: 0781-1234"], ["Sandoz Inc"]),
            ("recall", "fda", "RC-2024-042", "Class II Recall - Lisinopril",
             "Voluntary recall due to labeling issues on specific lot numbers.",
             RiskLevel.MEDIUM.value, ["Lisinopril 10mg"], ["Teva Pharmaceuticals"]),
            ("warning_letter", "fda", "WL-2024-088", "FDA Warning Letter - GMP Violations",
             "Warning letter issued for GMP violations at manufacturing facility.",
             RiskLevel.CRITICAL.value, [], ["Dr. Reddy's Laboratories"]),
            ("inspection", "fda", "INS-2024-200", "Form 483 Observations",
             "Routine inspection resulted in minor observations regarding documentation.",
             RiskLevel.LOW.value, [], ["Lonza"]),
            ("shortage", "fda", "SH-2024-015", "Adderall Supply Constraints",
             "Manufacturing capacity issues affecting Adderall supply.",
             RiskLevel.HIGH.value, ["Adderall", "Amphetamine salts"], ["Teva Pharmaceuticals"]),
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
                event_date=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30))
            )
            db.add(event)
        
        db.flush()
        
        # Create alerts linking events to vendors
        events = db.query(WatchtowerEvent).all()
        for event in events:
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
        print("Demo data seeded: 8 vendors, 4 facilities, 5 events, alerts")
        
    except Exception as e:
        db.rollback()
        print(f"Demo seeding error: {e}")
    finally:
        db.close()
