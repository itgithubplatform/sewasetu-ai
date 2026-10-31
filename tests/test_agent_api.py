import base64
import sys
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import app as portal
import agent_api
import oauth


@pytest.fixture
def client():
    return portal.app.test_client()


def test_get_db_uses_render_database_url(monkeypatch):
    received = {}

    def fake_connect(dsn, **kwargs):
        received["dsn"] = dsn
        received["kwargs"] = kwargs
        return object()

    monkeypatch.setenv("DATABASE_URL", "postgres://db.example/sewasetu")
    monkeypatch.setattr(portal.psycopg2, "connect", fake_connect)

    portal.get_db()

    assert received["dsn"] == "postgresql://db.example/sewasetu"
    assert received["kwargs"] == {"connect_timeout": 5}


def test_otp_request_reports_sms_gateway_failure(client, monkeypatch):
    class Cursor:
        def execute(self, *_args):
            pass

        def close(self):
            pass

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(portal, "get_db", Connection)
    monkeypatch.setattr(portal, "send_sms", lambda *_args: False)
    with client.session_transaction() as session:
        session["captcha_answer"] = 7

    response = client.post(
        "/apply",
        data={"mobile": "9000000001", "captcha": "7"},
    )

    assert response.status_code == 503
    assert b"could not send an OTP" in response.data


def citizen_claims():
    return {
        "sub": "citizen:9000000001",
        "role": "citizen",
        "scope": "citizen",
    }


def officer_claims():
    return {
        "sub": "officer:admin",
        "role": "officer",
        "scope": "officer",
    }


def application_payload(**overrides):
    payload = {
        "applicant_name": "Kamla Devi",
        "dob": "12/04/1956",
        "village": "Sonari Basti",
        "block": "Sonari",
        "bank_account": "123456789012",
        "ifsc": "SBIN0003077",
        "age_proof_filename": "proof.pdf",
        "age_proof_base64": base64.b64encode(b"synthetic-proof").decode("ascii"),
        "declaration_confirmed": True,
    }
    payload.update(overrides)
    return payload


def test_scheme_information_reports_enabled_block(client, monkeypatch):
    monkeypatch.setenv("MCP_ENABLED_BLOCKS", "Sonari")

    response = client.get("/api/agent/scheme")

    assert response.status_code == 200
    assert response.json["enabled_blocks"] == ["Sonari"]
    assert response.json["monthly_amount_inr"] == 250


def test_application_requires_explicit_declaration(client, monkeypatch):
    monkeypatch.setattr(agent_api, "verify_token", lambda token, audience: citizen_claims())

    response = client.post(
        "/api/agent/citizen/applications",
        headers={"Authorization": "Bearer signed-token"},
        json=application_payload(declaration_confirmed=False),
    )

    assert response.status_code == 400
    assert "declaration" in response.json["error"]


def test_underage_applicant_is_rejected_by_portal_validation(client, monkeypatch):
    monkeypatch.setattr(agent_api, "verify_token", lambda token, audience: citizen_claims())

    response = client.post(
        "/api/agent/citizen/applications",
        headers={"Authorization": "Bearer signed-token"},
        json=application_payload(dob="05/10/1967"),
    )

    assert response.status_code == 400
    assert any("60 years" in error for error in response.json["validation_errors"])


def test_agent_submission_rejects_block_outside_allowlist(client, monkeypatch):
    monkeypatch.setattr(agent_api, "verify_token", lambda token, audience: citizen_claims())
    monkeypatch.setenv("MCP_ENABLED_BLOCKS", "Sonari")

    response = client.post(
        "/api/agent/citizen/applications",
        headers={"Authorization": "Bearer signed-token"},
        json=application_payload(block="Rajapara"),
    )

    assert response.status_code == 400
    assert response.json["enabled_blocks"] == ["Sonari"]


def test_officer_decision_requires_a_reason(client, monkeypatch):
    monkeypatch.setattr(agent_api, "verify_token", lambda token, audience: officer_claims())

    response = client.post(
        "/api/agent/officer/applications/1/decision",
        headers={"Authorization": "Bearer signed-token"},
        json={"decision": "approve", "reason": " "},
    )

    assert response.status_code == 400
    assert "reason is required" in response.json["error"]


def test_citizen_token_cannot_read_officer_queue(client, monkeypatch):
    monkeypatch.setattr(agent_api, "verify_token", lambda token, audience: citizen_claims())

    response = client.get(
        "/api/agent/officer/applications",
        headers={"Authorization": "Bearer signed-token"},
    )

    assert response.status_code == 403


def test_authorization_metadata_matches_mcp_resource_discovery(client):
    metadata = client.get("/.well-known/oauth-authorization-server").json

    assert metadata["issuer"] == oauth.ISSUER
    assert metadata["authorization_endpoint"] == oauth.ISSUER_BASE + "/oauth/authorize"
    assert metadata["token_endpoint"] == oauth.ISSUER_BASE + "/oauth/token"


@pytest.mark.parametrize(
    "issuer",
    ["http://localhost:8000", "http://localhost:8000/"],
)
def test_portal_verifies_current_and_legacy_issuer(monkeypatch, issuer):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(oauth, "signing_key", lambda: ("test", private_key))
    token = jwt.encode(
        {
            "iss": issuer,
            "sub": "citizen:9000000001",
            "aud": "http://localhost:8001/mcp",
            "scope": "citizen",
            "role": "citizen",
            "exp": int(time.time()) + 60,
        },
        private_key,
        algorithm="RS256",
    )

    claims = oauth.verify_token(token, "http://localhost:8001/mcp")

    assert claims["iss"] == issuer
