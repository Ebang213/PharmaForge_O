"""
Tests for pharmacy registration fields on /api/auth/register.

Covers: registration with and without the new pharmacy fields (they are
optional for backward compatibility), field validation, and the
small-dispenser eligibility boundary at 25/26 employees.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.db.models import Organization
from app.core.config import settings
from app.api.auth import is_small_dispenser, SMALL_DISPENSER_MAX_EMPLOYEE_COUNT


# ============= Fixtures =============

@pytest.fixture(scope="module", autouse=True)
def allow_public_registration():
    """Enable public registration for this module, restore afterwards."""
    original = settings.ALLOW_PUBLIC_REGISTRATION
    settings.ALLOW_PUBLIC_REGISTRATION = True
    yield
    settings.ALLOW_PUBLIC_REGISTRATION = original


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _register_payload(**overrides) -> dict:
    """Valid registration payload with unique email/org per call."""
    unique = uuid.uuid4().hex[:10]
    payload = {
        # NOTE: .test TLD is rejected by EmailStr (special-use domain),
        # so use a plain .com domain for endpoint-level tests
        "email": f"pharm-reg-{unique}@pharmaforgetests.com",
        "password": "testpassword1",
        "full_name": "Pharmacy Test User",
        "organization_name": f"Pharmacy Reg Test {unique}",
    }
    payload.update(overrides)
    return payload


# ============= Backward compatibility =============

class TestRegistrationBackwardCompat:

    def test_register_without_pharmacy_fields(self, client: TestClient, db: Session):
        """The new fields are optional — old-style registration still works."""
        payload = _register_payload()
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["user"]["email"] == payload["email"]
        assert data["user"]["small_dispenser"] is None

        org = db.query(Organization).filter(
            Organization.id == data["user"]["organization_id"]
        ).first()
        assert org is not None
        assert org.pharmacy_name is None
        assert org.state is None
        assert org.employee_count is None

    def test_register_with_pharmacy_fields(self, client: TestClient, db: Session):
        payload = _register_payload(
            pharmacy_name="Main Street Pharmacy",
            state="tx",  # lowercase is normalized to uppercase
            employee_count=8,
        )
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["user"]["small_dispenser"] is True

        org = db.query(Organization).filter(
            Organization.id == data["user"]["organization_id"]
        ).first()
        assert org is not None
        assert org.pharmacy_name == "Main Street Pharmacy"
        assert org.state == "TX"
        assert org.employee_count == 8

    def test_pharmacy_name_used_as_org_name_when_org_name_missing(
        self, client: TestClient, db: Session
    ):
        unique = uuid.uuid4().hex[:10]
        payload = _register_payload(pharmacy_name=f"Solo Pharmacy {unique}")
        del payload["organization_name"]
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["user"]["organization_name"] == f"Solo Pharmacy {unique}"
        assert data["user"]["role"] == "owner"


# ============= Validation =============

class TestPharmacyFieldValidation:

    def test_invalid_state_rejected(self, client: TestClient):
        resp = client.post(
            "/api/auth/register",
            json=_register_payload(state="Texas"),
        )
        assert resp.status_code == 422

    def test_non_alpha_state_rejected(self, client: TestClient):
        resp = client.post(
            "/api/auth/register",
            json=_register_payload(state="1A"),
        )
        assert resp.status_code == 422

    def test_negative_employee_count_rejected(self, client: TestClient):
        resp = client.post(
            "/api/auth/register",
            json=_register_payload(employee_count=-1),
        )
        assert resp.status_code == 422


# ============= Small-dispenser eligibility boundary =============

class TestSmallDispenserBoundary:

    def test_helper_boundary(self):
        assert SMALL_DISPENSER_MAX_EMPLOYEE_COUNT == 25
        assert is_small_dispenser(25) is True
        assert is_small_dispenser(26) is False
        assert is_small_dispenser(0) is True
        assert is_small_dispenser(None) is None

    def test_register_at_25_is_small_dispenser(self, client: TestClient):
        resp = client.post(
            "/api/auth/register",
            json=_register_payload(employee_count=25),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["user"]["small_dispenser"] is True

    def test_register_at_26_is_not_small_dispenser(self, client: TestClient):
        resp = client.post(
            "/api/auth/register",
            json=_register_payload(employee_count=26),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["user"]["small_dispenser"] is False


# ============= Registration disabled =============

class TestRegistrationDisabled:

    def test_register_403_when_public_registration_disabled(self, client: TestClient):
        original = settings.ALLOW_PUBLIC_REGISTRATION
        settings.ALLOW_PUBLIC_REGISTRATION = False
        try:
            resp = client.post("/api/auth/register", json=_register_payload())
            assert resp.status_code == 403
        finally:
            settings.ALLOW_PUBLIC_REGISTRATION = original
