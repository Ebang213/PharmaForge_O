"""
Tests for GET /api/compliance/readiness.

Covers score 0 (fresh org), partial scores (25/50/75), full score (100),
response shape, and auth enforcement. Fixtures follow the get-or-create
pattern used in test_trading_partners.py.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.db.models import (
    Organization, User, Vendor, EPCISUpload, AuditLog, EPCISValidationStatus,
)
from app.core.security import create_access_token


CHECK_IDS = [
    "trading_partner_license",
    "recent_epcis_upload",
    "latest_upload_valid",
    "audit_packet_generated",
]


# ============= Fixtures =============

@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _get_or_create_org(db: Session, slug: str) -> Organization:
    org = db.query(Organization).filter(Organization.slug == slug).first()
    if not org:
        org = Organization(name=f"Readiness Test Org {slug}", slug=slug)
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


def _get_or_create_user(db: Session, org: Organization, email: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            hashed_password="$2b$12$fakehashnotusedfortesting000000",
            full_name="Readiness Test User",
            organization_id=org.id,
            role="operator",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _headers(user: User, org: Organization) -> dict:
    token = create_access_token(
        {
            "sub": str(user.id),
            "email": user.email,
            "role": "operator",
            "org_id": org.id,
        },
        expires_delta=timedelta(hours=1),
    )
    return {"Authorization": f"Bearer {token}"}


def _reset_org_data(db: Session, org: Organization) -> None:
    """Remove readiness-relevant rows so scores are deterministic on re-runs."""
    db.query(EPCISUpload).filter(EPCISUpload.organization_id == org.id).delete()
    db.query(Vendor).filter(Vendor.organization_id == org.id).delete()
    db.query(AuditLog).filter(
        AuditLog.organization_id == org.id,
        AuditLog.action == "audit_packet_generated",
    ).delete()
    db.commit()


def _add_verified_partner(db: Session, org: Organization) -> Vendor:
    vendor = Vendor(
        organization_id=org.id,
        name="Readiness Wholesaler",
        vendor_type="WHOLESALE_DISTRIBUTOR",
        partner_status="active",
        gln="0123456789012",
        contact_email="ops@readiness-wholesaler.com",
        data_source="user_created",
    )
    db.add(vendor)
    db.commit()
    return vendor


def _add_upload(db: Session, org: Organization, user: User, status: str,
                created_at: datetime) -> EPCISUpload:
    upload = EPCISUpload(
        organization_id=org.id,
        uploaded_by=user.id,
        filename=f"epcis-{status}-{created_at.timestamp()}.json",
        file_path="/tmp/nonexistent-test-file.json",
        validation_status=status,
        created_at=created_at,
    )
    db.add(upload)
    db.commit()
    return upload


def _add_packet_log(db: Session, org: Organization, user: User) -> AuditLog:
    log = AuditLog(
        user_id=user.id,
        organization_id=org.id,
        action="audit_packet_generated",
        entity_type="workflow_run",
        entity_id=1,
    )
    db.add(log)
    db.commit()
    return log


# ============= Score 0: fresh org =============

class TestScoreZero:

    @pytest.fixture(scope="class")
    def setup(self, db: Session):
        org = _get_or_create_org(db, "readiness-zero")
        user = _get_or_create_user(db, org, "readiness-zero@pharmaforgetests.com")
        _reset_org_data(db, org)
        return org, user

    def test_fresh_org_scores_zero(self, client: TestClient, db: Session, setup):
        org, user = setup
        assert db.query(Vendor).filter(Vendor.organization_id == org.id).count() == 0
        assert db.query(EPCISUpload).filter(EPCISUpload.organization_id == org.id).count() == 0

        resp = client.get("/api/compliance/readiness", headers=_headers(user, org))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["score"] == 0
        assert all(not c["passed"] for c in data["checks"])

    def test_response_shape(self, client: TestClient, setup):
        org, user = setup
        resp = client.get("/api/compliance/readiness", headers=_headers(user, org))
        data = resp.json()
        assert set(data.keys()) == {"score", "checks"}
        assert [c["id"] for c in data["checks"]] == CHECK_IDS
        for check in data["checks"]:
            assert set(check.keys()) == {"id", "label", "passed", "detail"}
            assert isinstance(check["passed"], bool)
            assert check["detail"]

    def test_requires_auth(self, client: TestClient):
        resp = client.get("/api/compliance/readiness")
        assert resp.status_code == 401


# ============= Partial scores =============

class TestPartialScores:

    @pytest.fixture(scope="class")
    def setup(self, db: Session):
        org = _get_or_create_org(db, "readiness-partial")
        user = _get_or_create_user(db, org, "readiness-partial@pharmaforgetests.com")
        _reset_org_data(db, org)
        return org, user

    def test_verified_partner_scores_25(self, client: TestClient, db: Session, setup):
        org, user = setup
        _add_verified_partner(db, org)

        resp = client.get("/api/compliance/readiness", headers=_headers(user, org))
        data = resp.json()
        assert data["score"] == 25
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["trading_partner_license"] is True
        assert passed["recent_epcis_upload"] is False
        assert passed["latest_upload_valid"] is False
        assert passed["audit_packet_generated"] is False

    def test_recent_invalid_upload_scores_50(self, client: TestClient, db: Session, setup):
        org, user = setup
        _add_upload(
            db, org, user,
            status=EPCISValidationStatus.INVALID.value,
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        resp = client.get("/api/compliance/readiness", headers=_headers(user, org))
        data = resp.json()
        assert data["score"] == 50
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["recent_epcis_upload"] is True
        assert passed["latest_upload_valid"] is False

    def test_newer_valid_upload_scores_75(self, client: TestClient, db: Session, setup):
        org, user = setup
        _add_upload(
            db, org, user,
            status=EPCISValidationStatus.VALID.value,
            created_at=datetime.now(timezone.utc),
        )

        resp = client.get("/api/compliance/readiness", headers=_headers(user, org))
        data = resp.json()
        assert data["score"] == 75
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["latest_upload_valid"] is True
        assert passed["audit_packet_generated"] is False


# ============= Score 100 =============

class TestScoreHundred:

    @pytest.fixture(scope="class")
    def setup(self, db: Session):
        org = _get_or_create_org(db, "readiness-full")
        user = _get_or_create_user(db, org, "readiness-full@pharmaforgetests.com")
        _reset_org_data(db, org)
        _add_verified_partner(db, org)
        _add_upload(
            db, org, user,
            status=EPCISValidationStatus.VALID.value,
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        _add_packet_log(db, org, user)
        return org, user

    def test_all_checks_pass(self, client: TestClient, setup):
        org, user = setup
        resp = client.get("/api/compliance/readiness", headers=_headers(user, org))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["score"] == 100
        assert all(c["passed"] for c in data["checks"])


# ============= Edge cases =============

class TestEdgeCases:

    @pytest.fixture(scope="class")
    def setup(self, db: Session):
        org = _get_or_create_org(db, "readiness-stale")
        user = _get_or_create_user(db, org, "readiness-stale@pharmaforgetests.com")
        _reset_org_data(db, org)
        return org, user

    def test_old_valid_upload_fails_recency_but_passes_validity(
        self, client: TestClient, db: Session, setup
    ):
        """A valid upload older than 30 days: check 2 fails, check 3 passes."""
        org, user = setup
        _add_upload(
            db, org, user,
            status=EPCISValidationStatus.VALID.value,
            created_at=datetime.now(timezone.utc) - timedelta(days=45),
        )

        resp = client.get("/api/compliance/readiness", headers=_headers(user, org))
        data = resp.json()
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["recent_epcis_upload"] is False
        assert passed["latest_upload_valid"] is True
        assert data["score"] == 25
