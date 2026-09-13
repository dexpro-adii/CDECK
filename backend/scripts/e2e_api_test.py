"""
e2e_api_test.py — E2E validation script.
Two tests:
  A) Output rail PII detection and redaction on leaked Aadhaar + PAN
  B) Normal clean message via HTTP call to /analyze
"""
import json, os, sys
import urllib.request, urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from detectors.output_scanner import scan_output

BASE = "http://127.0.0.1:8000"

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

# ── Test A: Output rail PII detection and redaction ─────────────────────────
print(DIV)
print("TEST A — Output rail scanning response with leaked Aadhaar + PAN")
mock_llm_output = (
    "Based on your query, the account holder's Aadhaar is "
    "3675 9834 6016 and their PAN is ZZZPQ9999R."
)
data_a = scan_output(mock_llm_output)
print("output_flagged           :", data_a["output_flagged"])
print("output_pii_found         :", json.dumps([{"type": e.type, "value": e.value} for e in data_a["output_pii_found"]], indent=2))
print("output_redacted_response :", repr(data_a["output_redacted_response"]))
assert data_a["output_flagged"] is True, "FAIL: output_flagged should be True"
assert "3675 9834 6016" not in data_a["output_redacted_response"], "FAIL: raw Aadhaar leaked in output_redacted_response"
assert "[REDACTED_AADHAAR]" in data_a["output_redacted_response"], "FAIL: REDACTED token missing"
assert "[REDACTED_PAN]" in data_a["output_redacted_response"], "FAIL: REDACTED token missing"
print("\n✓ PASS: Output rail caught and redacted leaked Aadhaar and PAN")

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
