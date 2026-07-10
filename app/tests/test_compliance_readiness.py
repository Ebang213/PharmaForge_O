"""
Tests for GET /api/compliance/readiness.

Covers score 0 (fresh org), partial scores (20/60/80), full score (100),
response shape, alert counts, packet-generation auditing, chain-break and
critical-issue behavior, organization isolation, and auth enforcement.
Fixtures follow the get-or-create pattern used in test_trading_partners.py.

Scoring: five checks at 20 points each.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.db.models import (
    Organization, User, Vendor, EPCISUpload, EPCISIssue, AuditLog,
    EPCISValidationStatus, RiskLevel,
)
from app.core.security import create_access_token


CHECK_IDS = [
    "trading_partner_license",
    "recent_epcis_upload",
    "latest_upload_valid",
    "chain_integrity",
    "audit_packet_generated",
]

RESPONSE_KEYS = {
    "score", "checks", "active_alert_count", "blocking_issue_count",
    "latest_upload_id", "latest_upload_status",
}


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
    upload_ids = [
        row.id for row in db.query(EPCISUpload.id).filter(
            EPCISUpload.organization_id == org.id,
        ).all()
    ]
    if upload_ids:
        db.query(EPCISIssue).filter(
            EPCISIssue.upload_id.in_(upload_ids),
        ).delete(synchronize_session=False)
        db.query(AuditLog).filter(
            AuditLog.entity_type == "epcis_upload",
            AuditLog.entity_id.in_(upload_ids),
        ).delete(synchronize_session=False)
    db.query(EPCISUpload).filter(
        EPCISUpload.organization_id == org.id,
    ).delete(synchronize_session=False)
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


def _add_incomplete_active_partner(db: Session, org: Organization) -> Vendor:
    """Active partner with no identifier/contact — counts as an alert."""
    vendor = Vendor(
        organization_id=org.id,
        name="Incomplete Wholesaler",
        vendor_type="WHOLESALE_DISTRIBUTOR",
        partner_status="active",
        data_source="user_created",
    )
    db.add(vendor)
    db.commit()
    return vendor


def _add_upload(db: Session, org: Organization, user: User, status: str,
                created_at: datetime, chain_break_count: int = 0) -> EPCISUpload:
    upload = EPCISUpload(
        organization_id=org.id,
        uploaded_by=user.id,
        filename=f"epcis-{status}-{created_at.timestamp()}.json",
        file_path="/tmp/nonexistent-test-file.json",
        file_hash="testhash" + created_at.strftime("%Y%m%d%H%M%S%f"),
        validation_status=status,
        created_at=created_at,
        chain_break_count=chain_break_count,
        event_count=0,
    )
    db.add(upload)
    db.commit()
    return upload


def _add_critical_issue(db: Session, upload: EPCISUpload) -> EPCISIssue:
    issue = EPCISIssue(
        upload_id=upload.id,
        issue_type="missing_field",
        severity=RiskLevel.CRITICAL,
        message="Critical test issue",
    )
    db.add(issue)
    db.commit()
    return issue


def _add_packet_log(db: Session, org: Organization, user: User,
                    upload: EPCISUpload) -> AuditLog:
    log = AuditLog(
        user_id=user.id,
        organization_id=org.id,
        action="audit_packet_generated",
        entity_type="epcis_upload",
        entity_id=upload.id,
    )
    db.add(log)
    db.commit()
    return log


def _readiness(client: TestClient, user: User, org: Organization) -> dict:
    resp = client.get("/api/compliance/readiness", headers=_headers(user, org))
    assert resp.status_code == 200, resp.text
    return resp.json()


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

        data = _readiness(client, user, org)
        assert data["score"] == 0
        assert all(not c["passed"] for c in data["checks"])
        assert data["active_alert_count"] == 0
        assert data["blocking_issue_count"] == 0
        assert data["latest_upload_id"] is None
        assert data["latest_upload_status"] is None

    def test_response_shape(self, client: TestClient, setup):
        org, user = setup
        data = _readiness(client, user, org)
        assert set(data.keys()) == RESPONSE_KEYS
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

    def test_verified_partner_scores_20(self, client: TestClient, db: Session, setup):
        org, user = setup
        _add_verified_partner(db, org)

        data = _readiness(client, user, org)
        assert data["score"] == 20
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["trading_partner_license"] is True
        assert passed["recent_epcis_upload"] is False
        assert passed["latest_upload_valid"] is False
        assert passed["chain_integrity"] is False
        assert passed["audit_packet_generated"] is False

    def test_recent_invalid_upload_scores_60(self, client: TestClient, db: Session, setup):
        org, user = setup
        upload = _add_upload(
            db, org, user,
            status=EPCISValidationStatus.INVALID.value,
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        data = _readiness(client, user, org)
        # partner + recent upload + chain integrity (the invalid row carries
        # no chain breaks or critical issue records) = 60
        assert data["score"] == 60
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["recent_epcis_upload"] is True
        assert passed["latest_upload_valid"] is False
        # Invalid latest upload is an actionable alert
        assert data["active_alert_count"] == 1
        assert data["latest_upload_id"] == upload.id
        assert data["latest_upload_status"] == "invalid"

    def test_newer_valid_upload_scores_80(self, client: TestClient, db: Session, setup):
        org, user = setup
        _add_upload(
            db, org, user,
            status=EPCISValidationStatus.VALID.value,
            created_at=datetime.now(timezone.utc),
        )

        data = _readiness(client, user, org)
        assert data["score"] == 80
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["latest_upload_valid"] is True
        assert passed["chain_integrity"] is True
        # A valid upload alone is NOT an inspection packet
        assert passed["audit_packet_generated"] is False
        assert data["active_alert_count"] == 0


# ============= Score 100 =============

class TestScoreHundred:

    @pytest.fixture(scope="class")
    def setup(self, db: Session):
        org = _get_or_create_org(db, "readiness-full")
        user = _get_or_create_user(db, org, "readiness-full@pharmaforgetests.com")
        _reset_org_data(db, org)
        _add_verified_partner(db, org)
        upload = _add_upload(
            db, org, user,
            status=EPCISValidationStatus.VALID.value,
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        _add_packet_log(db, org, user, upload)
        return org, user

    def test_all_checks_pass(self, client: TestClient, setup):
        org, user = setup
        data = _readiness(client, user, org)
        assert data["score"] == 100
        assert all(c["passed"] for c in data["checks"])
        assert data["active_alert_count"] == 0
        assert data["blocking_issue_count"] == 0


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
        """A valid upload older than 30 days: check 2 fails, checks 3+4 pass."""
        org, user = setup
        _add_upload(
            db, org, user,
            status=EPCISValidationStatus.VALID.value,
            created_at=datetime.now(timezone.utc) - timedelta(days=45),
        )

        data = _readiness(client, user, org)
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["recent_epcis_upload"] is False
        assert passed["latest_upload_valid"] is True
        assert passed["chain_integrity"] is True
        assert passed["audit_packet_generated"] is False
        assert data["score"] == 40


# ============= Packet generation via the API =============

class TestPacketGeneration:
    """Downloading the audit packet must create the audit event that the
    readiness packet check keys off."""

    @pytest.fixture(scope="class")
    def setup(self, db: Session):
        org = _get_or_create_org(db, "readiness-packet")
        user = _get_or_create_user(db, org, "readiness-packet@pharmaforgetests.com")
        _reset_org_data(db, org)
        _add_verified_partner(db, org)
        upload = _add_upload(
            db, org, user,
            status=EPCISValidationStatus.VALID.value,
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        return org, user, upload

    def test_valid_upload_without_packet_check_is_false(
        self, client: TestClient, setup
    ):
        org, user, upload = setup
        data = _readiness(client, user, org)
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["latest_upload_valid"] is True
        assert passed["audit_packet_generated"] is False
        assert data["score"] == 80

    def test_packet_download_creates_audit_event(
        self, client: TestClient, db: Session, setup
    ):
        org, user, upload = setup
        resp = client.get(
            f"/api/dscsa/uploads/{upload.id}/audit-packet",
            headers=_headers(user, org),
        )
        assert resp.status_code == 200, resp.text

        db.expire_all()
        logs = db.query(AuditLog).filter(
            AuditLog.organization_id == org.id,
            AuditLog.action == "audit_packet_generated",
            AuditLog.entity_type == "epcis_upload",
            AuditLog.entity_id == upload.id,
        ).all()
        assert len(logs) == 1
        log = logs[0]
        assert log.user_id == user.id
        details = log.details
        assert details["filename"] == upload.filename
        assert details["file_hash"] == upload.file_hash
        assert details["validation_status"] == "valid"
        assert details["event_count"] == 0
        assert details["issue_count"] == 0
        assert details["chain_break_count"] == 0
        assert details["generated_at"]
        assert details["requested_by_user_id"] == user.id
        assert details["organization_id"] == org.id

        # The packet documents its own generation event
        packet = resp.json()
        actions = [e["action"] for e in packet["audit_log_entries"]]
        assert "audit_packet_generated" in actions

    def test_readiness_packet_check_flips_after_generation(
        self, client: TestClient, setup
    ):
        org, user, upload = setup
        data = _readiness(client, user, org)
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["audit_packet_generated"] is True
        assert data["score"] == 100
        assert data["active_alert_count"] == 0

    def test_repeated_downloads_stay_valid_and_auditable(
        self, client: TestClient, db: Session, setup
    ):
        org, user, upload = setup
        resp = client.get(
            f"/api/dscsa/uploads/{upload.id}/audit-packet",
            headers=_headers(user, org),
        )
        assert resp.status_code == 200

        db.expire_all()
        log_count = db.query(AuditLog).filter(
            AuditLog.organization_id == org.id,
            AuditLog.action == "audit_packet_generated",
            AuditLog.entity_type == "epcis_upload",
            AuditLog.entity_id == upload.id,
        ).count()
        assert log_count == 2  # one entry per download — fully auditable

        # Readiness stays passing; no duplicate errors
        data = _readiness(client, user, org)
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["audit_packet_generated"] is True
        assert data["score"] == 100


# ============= Chain breaks =============

class TestChainBreaks:

    @pytest.fixture(scope="class")
    def setup(self, db: Session):
        org = _get_or_create_org(db, "readiness-chainbreak")
        user = _get_or_create_user(db, org, "readiness-chainbreak@pharmaforgetests.com")
        _reset_org_data(db, org)
        _add_verified_partner(db, org)
        return org, user

    def test_chain_breaks_block_chain_integrity_check(
        self, client: TestClient, db: Session, setup
    ):
        org, user = setup
        _add_upload(
            db, org, user,
            status=EPCISValidationStatus.CHAIN_BREAK.value,
            created_at=datetime.now(timezone.utc),
            chain_break_count=2,
        )

        data = _readiness(client, user, org)
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["chain_integrity"] is False
        assert passed["latest_upload_valid"] is False
        assert data["blocking_issue_count"] == 2
        # Two unresolved chain breaks = two actionable alerts
        assert data["active_alert_count"] == 2
        assert data["latest_upload_status"] == "chain_break"

    def test_corrected_reupload_unblocks_check(
        self, client: TestClient, db: Session, setup
    ):
        """Re-uploading a corrected file is the only resolution path."""
        org, user = setup
        _add_upload(
            db, org, user,
            status=EPCISValidationStatus.VALID.value,
            created_at=datetime.now(timezone.utc) + timedelta(seconds=1),
        )

        data = _readiness(client, user, org)
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["chain_integrity"] is True
        assert data["blocking_issue_count"] == 0
        assert data["active_alert_count"] == 0


# ============= Critical issues and alert counting =============

class TestCriticalIssues:

    @pytest.fixture(scope="class")
    def setup(self, db: Session):
        org = _get_or_create_org(db, "readiness-critical")
        user = _get_or_create_user(db, org, "readiness-critical@pharmaforgetests.com")
        _reset_org_data(db, org)
        return org, user

    def test_critical_issues_increase_active_alert_count(
        self, client: TestClient, db: Session, setup
    ):
        org, user = setup
        upload = _add_upload(
            db, org, user,
            status=EPCISValidationStatus.INVALID.value,
            created_at=datetime.now(timezone.utc),
        )

        baseline = _readiness(client, user, org)
        assert baseline["active_alert_count"] == 1  # invalid latest upload

        _add_critical_issue(db, upload)
        _add_critical_issue(db, upload)

        data = _readiness(client, user, org)
        assert data["active_alert_count"] == 3  # invalid + 2 critical issues
        assert data["blocking_issue_count"] == 2
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["chain_integrity"] is False

    def test_incomplete_active_partner_counts_as_alert(
        self, client: TestClient, db: Session, setup
    ):
        org, user = setup
        _add_incomplete_active_partner(db, org)

        data = _readiness(client, user, org)
        # invalid upload + 2 critical issues + 1 incomplete active partner
        assert data["active_alert_count"] == 4


# ============= Organization isolation =============

class TestOrgIsolation:

    @pytest.fixture(scope="class")
    def setup(self, db: Session):
        org_a = _get_or_create_org(db, "readiness-iso-a")
        user_a = _get_or_create_user(db, org_a, "readiness-iso-a@pharmaforgetests.com")
        org_b = _get_or_create_org(db, "readiness-iso-b")
        user_b = _get_or_create_user(db, org_b, "readiness-iso-b@pharmaforgetests.com")
        _reset_org_data(db, org_a)
        _reset_org_data(db, org_b)

        # Org A: fully ready
        _add_verified_partner(db, org_a)
        upload_a = _add_upload(
            db, org_a, user_a,
            status=EPCISValidationStatus.VALID.value,
            created_at=datetime.now(timezone.utc),
        )
        _add_packet_log(db, org_a, user_a, upload_a)

        # Org B: chain-broken upload, no partner, no packet
        upload_b = _add_upload(
            db, org_b, user_b,
            status=EPCISValidationStatus.CHAIN_BREAK.value,
            created_at=datetime.now(timezone.utc),
            chain_break_count=3,
        )
        return org_a, user_a, upload_a, org_b, user_b, upload_b

    def test_org_a_unaffected_by_org_b_problems(self, client: TestClient, setup):
        org_a, user_a, _, _, _, _ = setup
        data = _readiness(client, user_a, org_a)
        assert data["score"] == 100
        assert data["active_alert_count"] == 0
        assert data["blocking_issue_count"] == 0

    def test_org_b_does_not_inherit_org_a_readiness(self, client: TestClient, setup):
        org_a, _, upload_a, org_b, user_b, upload_b = setup
        data = _readiness(client, user_b, org_b)
        passed = {c["id"]: c["passed"] for c in data["checks"]}
        assert passed["trading_partner_license"] is False
        assert passed["chain_integrity"] is False
        # Org A's packet event must not satisfy org B's packet check
        assert passed["audit_packet_generated"] is False
        assert data["latest_upload_id"] == upload_b.id
        assert data["active_alert_count"] == 3

    def test_packet_download_is_org_scoped(self, client: TestClient, setup):
        """Org B cannot download (or audit-log) org A's packet."""
        org_a, _, upload_a, org_b, user_b, _ = setup
        resp = client.get(
            f"/api/dscsa/uploads/{upload_a.id}/audit-packet",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404
