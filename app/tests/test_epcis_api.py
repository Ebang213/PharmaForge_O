"""
API integration tests for DSCSA/EPCIS endpoints.

Tests the HTTP layer using FastAPI TestClient against a real database.
Covers: upload, list, detail, audit packet, auth enforcement, error handling.
"""
import io
import json
import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.db.models import Organization, User
from app.core.security import create_access_token


# ============= Fixture EPCIS content =============

VALID_EPCIS_JSON = json.dumps({
    "epcisBody": {
        "eventList": [
            {
                "type": "ObjectEvent",
                "eventTime": "2024-12-15T10:00:00Z",
                "eventTimeZoneOffset": "-05:00",
                "action": "ADD",
                "bizStep": "urn:epcglobal:cbv:bizstep:commissioning",
                "disposition": "urn:epcglobal:cbv:disp:active",
                "readPoint": {"id": "urn:epc:id:sgln:0614141.00001.0"},
                "bizLocation": {"id": "urn:epc:id:sgln:0614141.00001.0"},
                "epcList": [
                    "urn:epc:id:sgtin:0614141.107346.9901",
                    "urn:epc:id:sgtin:0614141.107346.9902",
                ],
            }
        ]
    }
})

# Events with validation issues (missing eventTime + empty epcList)
INVALID_EPCIS_JSON = json.dumps({
    "epcisBody": {
        "eventList": [
            {
                "type": "ObjectEvent",
                "action": "ADD",
                # Missing eventTime (high severity)
                # Missing epcList (critical severity)
            }
        ]
    }
})

MALFORMED_JSON = b"{ this is not valid json ["

VALID_EPCIS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<EPCISDocument>
  <EPCISBody>
    <EventList>
      <ObjectEvent>
        <eventTime>2024-12-15T10:00:00Z</eventTime>
        <action>ADD</action>
        <bizStep>urn:epcglobal:cbv:bizstep:commissioning</bizStep>
        <epcList>
          <epc>urn:epc:id:sgtin:0614141.107346.9991</epc>
        </epcList>
      </ObjectEvent>
    </EventList>
  </EPCISBody>
</EPCISDocument>
"""


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
    org = db.query(Organization).filter(Organization.slug == "epcis-api-test").first()
    if not org:
        org = Organization(name="EPCIS API Test Org", slug="epcis-api-test")
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


@pytest.fixture(scope="module")
def test_user(db: Session, test_org: Organization):
    user = db.query(User).filter(User.email == "epcis-api-test@pharmaforge.test").first()
    if not user:
        user = User(
            email="epcis-api-test@pharmaforge.test",
            hashed_password="$2b$12$fakehashnotusedfortesting000000",
            full_name="EPCIS API Test User",
            organization_id=test_org.id,
            role="operator",
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
def client():
    with TestClient(app) as c:
        yield c


# ============= Upload endpoint =============

class TestUploadEndpoint:

    def test_upload_valid_json_returns_200(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/dscsa/upload",
            headers=auth_headers,
            files={"file": ("test_valid.json", io.BytesIO(VALID_EPCIS_JSON.encode()), "application/json")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["filename"] == "test_valid.json"
        assert data["event_count"] == 1
        assert data["validation_status"] in ("valid", "chain_break")
        assert isinstance(data["events"], list)
        assert isinstance(data["issues"], list)

    def test_upload_valid_xml_returns_200(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/dscsa/upload",
            headers=auth_headers,
            files={"file": ("test_valid.xml", io.BytesIO(VALID_EPCIS_XML), "application/xml")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["event_count"] == 1
        assert data["validation_status"] in ("valid", "chain_break")

    def test_upload_json_with_validation_issues(self, client: TestClient, auth_headers: dict):
        """EPCIS file missing required fields returns 200 with issues, not a 500."""
        resp = client.post(
            "/api/dscsa/upload",
            headers=auth_headers,
            files={"file": ("invalid.json", io.BytesIO(INVALID_EPCIS_JSON.encode()), "application/json")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["issues"]) > 0
        severities = {i["severity"] for i in data["issues"]}
        assert "critical" in severities

    def test_upload_malformed_json_returns_400_not_500(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/dscsa/upload",
            headers=auth_headers,
            files={"file": ("bad.json", io.BytesIO(MALFORMED_JSON), "application/json")},
        )
        assert resp.status_code == 400, resp.text
        assert "detail" in resp.json()

    def test_upload_wrong_extension_returns_400(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/dscsa/upload",
            headers=auth_headers,
            files={"file": ("data.txt", io.BytesIO(b"data"), "text/plain")},
        )
        assert resp.status_code == 400

    def test_upload_requires_auth(self, client: TestClient):
        resp = client.post(
            "/api/dscsa/upload",
            files={"file": ("test.json", io.BytesIO(VALID_EPCIS_JSON.encode()), "application/json")},
        )
        assert resp.status_code in (401, 403)

    def test_upload_alias_endpoint(self, client: TestClient, auth_headers: dict):
        """/epcis/upload alias works the same as /upload."""
        resp = client.post(
            "/api/dscsa/epcis/upload",
            headers=auth_headers,
            files={"file": ("alias_test.json", io.BytesIO(VALID_EPCIS_JSON.encode()), "application/json")},
        )
        assert resp.status_code == 200


# ============= List endpoint =============

class TestListEndpoint:

    def test_list_returns_array(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/dscsa/uploads", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_fields_present(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/dscsa/uploads", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        if data:
            item = data[0]
            assert "id" in item
            assert "filename" in item
            assert "validation_status" in item
            assert "event_count" in item
            assert "created_at" in item

    def test_list_requires_auth(self, client: TestClient):
        resp = client.get("/api/dscsa/uploads")
        assert resp.status_code in (401, 403)

    def test_list_alias_endpoint(self, client: TestClient, auth_headers: dict):
        r1 = client.get("/api/dscsa/uploads", headers=auth_headers)
        r2 = client.get("/api/dscsa/epcis/uploads", headers=auth_headers)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert len(r1.json()) == len(r2.json())


# ============= Detail endpoint =============

class TestDetailEndpoint:

    @pytest.fixture(scope="class")
    def upload_id(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/dscsa/upload",
            headers=auth_headers,
            files={"file": ("detail_fixture.json", io.BytesIO(VALID_EPCIS_JSON.encode()), "application/json")},
        )
        assert resp.status_code == 200
        return resp.json()["id"]

    def test_get_detail_returns_200(self, client: TestClient, auth_headers: dict, upload_id: int):
        resp = client.get(f"/api/dscsa/uploads/{upload_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == upload_id
        assert isinstance(data["events"], list)
        assert isinstance(data["issues"], list)
        assert data["event_count"] >= 0

    def test_get_detail_has_validated_at(self, client: TestClient, auth_headers: dict, upload_id: int):
        resp = client.get(f"/api/dscsa/uploads/{upload_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert "validated_at" in resp.json()

    def test_get_detail_not_found(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/dscsa/uploads/999999", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_detail_requires_auth(self, client: TestClient, upload_id: int):
        resp = client.get(f"/api/dscsa/uploads/{upload_id}")
        assert resp.status_code in (401, 403)

    def test_detail_alias_endpoint(self, client: TestClient, auth_headers: dict, upload_id: int):
        r1 = client.get(f"/api/dscsa/uploads/{upload_id}", headers=auth_headers)
        r2 = client.get(f"/api/dscsa/epcis/uploads/{upload_id}", headers=auth_headers)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]


# ============= Audit packet endpoint =============

class TestAuditPacketEndpoint:

    @pytest.fixture(scope="class")
    def upload_id(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/dscsa/upload",
            headers=auth_headers,
            files={"file": ("packet_fixture.json", io.BytesIO(VALID_EPCIS_JSON.encode()), "application/json")},
        )
        assert resp.status_code == 200
        return resp.json()["id"]

    def test_audit_packet_returns_200(self, client: TestClient, auth_headers: dict, upload_id: int):
        resp = client.get(f"/api/dscsa/uploads/{upload_id}/audit-packet", headers=auth_headers)
        assert resp.status_code == 200

    def test_audit_packet_structure(self, client: TestClient, auth_headers: dict, upload_id: int):
        resp = client.get(f"/api/dscsa/uploads/{upload_id}/audit-packet", headers=auth_headers)
        data = resp.json()
        assert "generated_at" in data
        assert "upload" in data
        assert "validation_summary" in data
        assert "events" in data
        assert "issues" in data
        assert "audit_log_entries" in data

    def test_audit_packet_upload_fields(self, client: TestClient, auth_headers: dict, upload_id: int):
        resp = client.get(f"/api/dscsa/uploads/{upload_id}/audit-packet", headers=auth_headers)
        upload_section = resp.json()["upload"]
        assert upload_section["id"] == upload_id
        assert "filename" in upload_section
        assert "content_type" in upload_section
        assert "validation_status" in upload_section
        assert "uploaded_at" in upload_section
        assert upload_section["content_type"] is not None

    def test_audit_packet_not_found(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/dscsa/uploads/999999/audit-packet", headers=auth_headers)
        assert resp.status_code == 404

    def test_audit_packet_requires_auth(self, client: TestClient, upload_id: int):
        resp = client.get(f"/api/dscsa/uploads/{upload_id}/audit-packet")
        assert resp.status_code in (401, 403)

    def test_audit_packet_content_disposition_header(self, client: TestClient, auth_headers: dict, upload_id: int):
        resp = client.get(f"/api/dscsa/uploads/{upload_id}/audit-packet", headers=auth_headers)
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert f"audit_packet_{upload_id}.json" in cd


# ============= Health endpoint =============

class TestHealthEndpoint:

    def test_dscsa_health(self, client: TestClient):
        resp = client.get("/api/dscsa/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["module"] == "dscsa"
