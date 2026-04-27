"""
Integration tests for /api/trading-partners endpoints.

Tests: create, list, get, update (PATCH), delete, readiness, auth enforcement,
validation rejection, and malformed payload handling.
"""
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.db.models import Organization, User, Vendor
from app.core.security import create_access_token


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
def test_org(db: Session):
    org = db.query(Organization).filter(Organization.slug == "tp-api-test").first()
    if not org:
        org = Organization(name="Trading Partner API Test Org", slug="tp-api-test")
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


@pytest.fixture(scope="module")
def test_user(db: Session, test_org: Organization):
    user = db.query(User).filter(User.email == "tp-api-test@pharmaforge.test").first()
    if not user:
        user = User(
            email="tp-api-test@pharmaforge.test",
            hashed_password="$2b$12$fakehashnotusedfortesting000000",
            full_name="TP API Test User",
            organization_id=test_org.id,
            role="operator",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture(scope="module")
def viewer_user(db: Session, test_org: Organization):
    user = db.query(User).filter(User.email == "tp-viewer@pharmaforge.test").first()
    if not user:
        user = User(
            email="tp-viewer@pharmaforge.test",
            hashed_password="$2b$12$fakehashnotusedfortesting000000",
            full_name="TP Viewer User",
            organization_id=test_org.id,
            role="viewer",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture(scope="module")
def auth_headers(test_user: User, test_org: Organization):
    token = create_access_token(
        {
            "sub": str(test_user.id),
            "email": test_user.email,
            "role": "operator",
            "org_id": test_org.id,
        },
        expires_delta=timedelta(hours=1),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def viewer_headers(viewer_user: User, test_org: Organization):
    token = create_access_token(
        {
            "sub": str(viewer_user.id),
            "email": viewer_user.email,
            "role": "viewer",
            "org_id": test_org.id,
        },
        expires_delta=timedelta(hours=1),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ============= Create =============

class TestCreateTradingPartner:

    def test_create_minimal_valid(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/trading-partners",
            json={"name": "Test Wholesaler", "partner_type": "WHOLESALE_DISTRIBUTOR", "status": "active"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "Test Wholesaler"
        assert data["partner_type"] == "WHOLESALE_DISTRIBUTOR"
        assert data["status"] == "active"
        assert data["verification_status"] == "incomplete"
        assert "missing_fields" in data
        assert len(data["missing_fields"]) > 0

    def test_create_full_verified(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/trading-partners",
            json={
                "name": "Full Partner Corp",
                "partner_type": "MANUFACTURER",
                "status": "active",
                "gln": "0123456789012",
                "contact_email": "contact@fullpartner.com",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["verification_status"] == "verified"
        assert data["missing_fields"] == []

    def test_create_missing_name_returns_422(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/trading-partners",
            json={"partner_type": "MANUFACTURER"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_create_invalid_partner_type_returns_422(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/trading-partners",
            json={"name": "Bad Type", "partner_type": "HACKER"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_create_invalid_status_returns_422(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/trading-partners",
            json={"name": "Bad Status", "status": "approved"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_create_malformed_payload_returns_422(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/trading-partners",
            content=b"{ not valid json [",
            headers={**auth_headers, "Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_create_requires_auth(self, client: TestClient):
        resp = client.post(
            "/api/trading-partners",
            json={"name": "Unauthed Partner"},
        )
        assert resp.status_code == 401


# ============= List =============

class TestListTradingPartners:

    def test_list_returns_200(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/trading-partners", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    def test_list_requires_auth(self, client: TestClient):
        resp = client.get("/api/trading-partners")
        assert resp.status_code == 401

    def test_list_search_filter(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/trading-partners?search=Full+Partner+Corp", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        names = [i["name"] for i in data["items"]]
        assert any("Full Partner Corp" in n for n in names)

    def test_list_partner_type_filter(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/trading-partners?partner_type=MANUFACTURER", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["partner_type"] == "MANUFACTURER"


# ============= Get Detail =============

class TestGetTradingPartner:

    @pytest.fixture(scope="class")
    def created_id(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/trading-partners",
            json={"name": "Detail Test Partner", "partner_type": "DISPENSER", "dea_number": "AB1234567", "contact_phone": "555-000-1234"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_get_existing(self, client: TestClient, auth_headers: dict, created_id: int):
        resp = client.get(f"/api/trading-partners/{created_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == created_id
        assert data["name"] == "Detail Test Partner"
        assert data["dea_number"] == "AB1234567"

    def test_get_nonexistent_returns_404(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/trading-partners/99999999", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_requires_auth(self, client: TestClient, created_id: int):
        resp = client.get(f"/api/trading-partners/{created_id}")
        assert resp.status_code == 401


# ============= Update =============

class TestUpdateTradingPartner:

    @pytest.fixture(scope="class")
    def partner_id(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/trading-partners",
            json={"name": "Update Test Partner", "status": "pending_review"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_patch_name(self, client: TestClient, auth_headers: dict, partner_id: int):
        resp = client.patch(
            f"/api/trading-partners/{partner_id}",
            json={"name": "Updated Partner Name"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Partner Name"

    def test_patch_adds_identifier_and_becomes_more_complete(self, client: TestClient, auth_headers: dict, partner_id: int):
        resp = client.patch(
            f"/api/trading-partners/{partner_id}",
            json={
                "partner_type": "REPACKAGER",
                "gln": "1234567890123",
                "contact_email": "ops@repackager.com",
                "status": "active",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["gln"] == "1234567890123"
        assert data["verification_status"] == "verified"
        assert data["missing_fields"] == []

    def test_patch_nonexistent_returns_404(self, client: TestClient, auth_headers: dict):
        resp = client.patch(
            "/api/trading-partners/99999999",
            json={"name": "Ghost"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_patch_invalid_partner_type_returns_422(self, client: TestClient, auth_headers: dict, partner_id: int):
        resp = client.patch(
            f"/api/trading-partners/{partner_id}",
            json={"partner_type": "INVALID"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_patch_requires_operator(self, client: TestClient, viewer_headers: dict, partner_id: int):
        resp = client.patch(
            f"/api/trading-partners/{partner_id}",
            json={"name": "Viewer Should Fail"},
            headers=viewer_headers,
        )
        assert resp.status_code == 403


# ============= Delete =============

class TestDeleteTradingPartner:

    @pytest.fixture(scope="class")
    def deletable_id(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/trading-partners",
            json={"name": "To Be Deleted"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_delete_existing(self, client: TestClient, auth_headers: dict, deletable_id: int):
        resp = client.delete(f"/api/trading-partners/{deletable_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    def test_deleted_no_longer_accessible(self, client: TestClient, auth_headers: dict, deletable_id: int):
        resp = client.get(f"/api/trading-partners/{deletable_id}", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_nonexistent_returns_404(self, client: TestClient, auth_headers: dict):
        resp = client.delete("/api/trading-partners/99999999", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_requires_operator(self, client: TestClient, viewer_headers: dict, auth_headers: dict):
        create = client.post(
            "/api/trading-partners",
            json={"name": "Viewer Delete Test"},
            headers=auth_headers,
        )
        pid = create.json()["id"]
        resp = client.delete(f"/api/trading-partners/{pid}", headers=viewer_headers)
        assert resp.status_code == 403
        client.delete(f"/api/trading-partners/{pid}", headers=auth_headers)


# ============= Readiness =============

class TestReadiness:

    def test_readiness_returns_200(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/trading-partners/readiness", headers=auth_headers)
        assert resp.status_code == 200

    def test_readiness_shape(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/trading-partners/readiness", headers=auth_headers)
        data = resp.json()
        assert "total_trading_partners" in data
        assert "verified_partners" in data
        assert "incomplete_partners" in data
        assert "readiness_percentage" in data
        assert 0 <= data["readiness_percentage"] <= 100

    def test_readiness_consistency(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/trading-partners/readiness", headers=auth_headers)
        data = resp.json()
        assert data["verified_partners"] + data["incomplete_partners"] == data["total_trading_partners"]

    def test_readiness_requires_auth(self, client: TestClient):
        resp = client.get("/api/trading-partners/readiness")
        assert resp.status_code == 401
