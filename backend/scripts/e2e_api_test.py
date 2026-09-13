"""
e2e_api_test.py — real HTTP calls to the live uvicorn server.
Three tests:
  A) PII-in-output (aadhaar_test marker triggers fake Aadhaar in mock response)
  B) Normal clean message (no flags)
Run after uvicorn is serving on http://127.0.0.1:8100
"""
import json, sys
import urllib.request, urllib.error

BASE = "http://127.0.0.1:8100"

def post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, json.loads(resp.read())

DIV = "\n" + "=" * 72 + "\n"

# ── Test A: PII in mocked LLM response ─────────────────────────────────────
print(DIV)
print("LIVE E2E TEST A — Input triggers mock response with fake Aadhaar + PAN")
payload_a = {"text": "Please look up account details for aadhaar_test user", "session_id": "e2e-a"}
print("POST /analyze", json.dumps(payload_a))
status_a, data_a = post("/analyze", payload_a)
print(f"\nHTTP {status_a}")
print("blocked                  :", data_a["blocked"])
print("risk_level               :", data_a["risk_level"])
print("output_flagged           :", data_a["output_flagged"])
print("output_pii_found         :", json.dumps(data_a["output_pii_found"], indent=2))
print("output_redacted_response :", repr(data_a["output_redacted_response"]))
print("forwarded_response       :", repr(data_a["forwarded_response"]))
assert data_a["output_flagged"] == True, "FAIL: output_flagged should be True"
assert "3675 9834 6016" not in data_a["forwarded_response"], "FAIL: raw Aadhaar leaked to forwarded_response"
assert "[REDACTED_AADHAAR]" in data_a["output_redacted_response"], "FAIL: REDACTED token missing"
print("\n✓ PASS: Output rail caught and redacted PII before it reached forwarded_response")

# ── Test B: Normal clean message ─────────────────────────────────────────────
print(DIV)
print("LIVE E2E TEST B — Normal clean message (no PII, no jailbreak)")
payload_b = {"text": "What is the capital of India?", "session_id": "e2e-b"}
print("POST /analyze", json.dumps(payload_b))
status_b, data_b = post("/analyze", payload_b)
print(f"\nHTTP {status_b}")
print("blocked                  :", data_b["blocked"])
print("risk_level               :", data_b["risk_level"])
print("output_flagged           :", data_b["output_flagged"])
print("output_pii_found         :", data_b["output_pii_found"])
print("forwarded_response       :", repr(data_b["forwarded_response"]))
assert data_b["output_flagged"] == False, "FAIL: clean response should not be flagged"
assert data_b["output_pii_found"] == [], "FAIL: no PII expected"
assert data_b["blocked"] == False, "FAIL: clean input should not be blocked"
print("\n✓ PASS: Normal clean message passes through output rail unflagged")

print(DIV)
print("All live E2E tests PASSED.")
