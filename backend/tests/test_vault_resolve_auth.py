"""
Auth tests for /vault/resolve.

The live exploit this closes: /vault/resolve used to accept any caller-supplied
session_id with no credential at all and hand back decrypted Aadhaar/PAN/UPI in
plaintext. Encrypting the store did nothing about it -- the endpoint decrypted
happily for whoever asked. A session_id is an identifier, not a secret: it shows
up in logs, in client code and in the /vault/mask response.

A session now carries a bearer secret, minted on first write and returned to its
creator, which must be presented as X-Vault-Token.
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

PHONE = "9876543210"
AADHAAR = "3675 9834 6016"
TEXT = f"My phone is {PHONE} and Aadhaar is {AADHAAR}"


def _mask(session_id):
    resp = client.post("/vault/mask", json={"text": TEXT, "session_id": session_id})
    assert resp.status_code == 200
    body = resp.json()
    return body["masked_text"], body["session_token"]


def test_mask_issues_a_session_token():
    _, token = _mask("auth-issue")
    assert token
    assert len(token) >= 32, "session token is too short to resist guessing"


def test_tokens_differ_per_session():
    _, t1 = _mask("auth-a")
    _, t2 = _mask("auth-b")
    assert t1 != t2


def test_resolve_without_token_is_rejected():
    """The exploit, verbatim: knowing the session_id must not be enough."""
    masked, _ = _mask("auth-no-token")
    resp = client.post(
        "/vault/resolve", json={"session_id": "auth-no-token", "masked_text": masked}
    )
    assert resp.status_code == 401
    assert PHONE not in resp.text
    assert AADHAAR not in resp.text


def test_resolve_with_wrong_token_is_rejected():
    masked, _ = _mask("auth-wrong-token")
    resp = client.post(
        "/vault/resolve",
        json={"session_id": "auth-wrong-token", "masked_text": masked},
        headers={"X-Vault-Token": "not-the-right-token"},
    )
    assert resp.status_code == 401
    assert PHONE not in resp.text


def test_another_sessions_token_does_not_work():
    """Holding a valid token for session A must not unlock session B."""
    masked_a, _ = _mask("auth-victim")
    _, token_b = _mask("auth-attacker")

    resp = client.post(
        "/vault/resolve",
        json={"session_id": "auth-victim", "masked_text": masked_a},
        headers={"X-Vault-Token": token_b},
    )
    assert resp.status_code == 401
    assert PHONE not in resp.text
    assert AADHAAR not in resp.text


def test_unknown_session_is_indistinguishable_from_wrong_token():
    """Same status and detail either way, so session ids cannot be enumerated."""
    masked, _ = _mask("auth-known")

    unknown = client.post(
        "/vault/resolve",
        json={"session_id": "session-that-never-existed", "masked_text": masked},
        headers={"X-Vault-Token": "anything"},
    )
    wrong = client.post(
        "/vault/resolve",
        json={"session_id": "auth-known", "masked_text": masked},
        headers={"X-Vault-Token": "anything"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_correct_token_still_resolves():
    """The legitimate path is unbroken."""
    masked, token = _mask("auth-happy")
    resp = client.post(
        "/vault/resolve",
        json={"session_id": "auth-happy", "masked_text": masked},
        headers={"X-Vault-Token": token},
    )
    assert resp.status_code == 200
    text = resp.json()["text"]
    assert PHONE in text
    assert AADHAAR in text
    assert "<PHONE_IN_" not in text


def test_analyze_content_session_is_also_protected():
    """The retrieval rail vaults too; its sessions need the same credential."""
    session = "auth-retrieval"
    resp = client.post(
        "/analyze-content",
        json={"content": TEXT, "source": "document", "session_id": session},
    )
    body = resp.json()
    masked = body["redacted_text"]
    token = body["session_token"]
    assert token

    denied = client.post(
        "/vault/resolve", json={"session_id": session, "masked_text": masked}
    )
    assert denied.status_code == 401

    allowed = client.post(
        "/vault/resolve",
        json={"session_id": session, "masked_text": masked},
        headers={"X-Vault-Token": token},
    )
    assert allowed.status_code == 200
    assert PHONE in allowed.json()["text"]


def test_analyze_content_without_session_issues_no_token():
    """No vaulting means no credential to leak."""
    resp = client.post("/analyze-content", json={"content": TEXT, "source": "document"})
    assert resp.json()["session_token"] is None
