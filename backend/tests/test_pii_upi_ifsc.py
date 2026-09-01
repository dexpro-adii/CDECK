"""
tests/test_pii_upi_ifsc.py
==========================
Pytest suite for the two new PII recognizer types:
  - UPI_ID  (username@<known-bank-handle>)
  - IFSC_CODE (4 alpha + '0' + 6 alphanumeric)

Five required cases
-------------------
1. UPI ID alone
2. IFSC code alone
3. Sentence mixing both with a person name
4. Hinglish sentence containing a UPI ID
5. Control: a REGULAR email address must NOT be flagged as UPI
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from detectors.pii_detector import detect_pii, redact_text

# ---------------------------------------------------------------------------
# Case 1 — UPI ID alone
# ---------------------------------------------------------------------------
class TestUPIAlone:
    UPI_SAMPLES = [
        "9876543210@ybl",
        "rahul.sharma@okaxis",
        "user123@paytm",
        "mohan_das@oksbi",
        "priya.verma@okhdfcbank",
    ]

    @pytest.mark.parametrize("upi", UPI_SAMPLES)
    def test_upi_detected(self, upi):
        results = detect_pii(upi)
        print(f"\nINPUT : {upi!r}")
        print(f"FOUND : {[(r.type, r.value) for r in results]}")
        assert any(r.type == "UPI_ID" for r in results), (
            f"Expected UPI_ID in results for {upi!r}, got: {[r.type for r in results]}"
        )

    @pytest.mark.parametrize("upi", UPI_SAMPLES)
    def test_upi_redacted(self, upi):
        results = detect_pii(upi)
        redacted = redact_text(upi, results)
        print(f"\nINPUT    : {upi!r}")
        print(f"REDACTED : {redacted!r}")
        assert "[REDACTED_UPI_ID]" in redacted
        assert upi not in redacted


# ---------------------------------------------------------------------------
# Case 2 — IFSC code alone
# ---------------------------------------------------------------------------
class TestIFSCAlone:
    IFSC_SAMPLES = [
        "HDFC0001234",
        "SBIN0000123",
        "ICIC0006789",
        "UTIB0004567",
        "KKBK0001122",
    ]

    @pytest.mark.parametrize("ifsc", IFSC_SAMPLES)
    def test_ifsc_detected(self, ifsc):
        results = detect_pii(ifsc)
        print(f"\nINPUT : {ifsc!r}")
        print(f"FOUND : {[(r.type, r.value) for r in results]}")
        assert any(r.type == "IFSC_CODE" for r in results), (
            f"Expected IFSC_CODE in results for {ifsc!r}, got: {[r.type for r in results]}"
        )

    @pytest.mark.parametrize("ifsc", IFSC_SAMPLES)
    def test_ifsc_redacted(self, ifsc):
        results = detect_pii(ifsc)
        redacted = redact_text(ifsc, results)
        print(f"\nINPUT    : {ifsc!r}")
        print(f"REDACTED : {redacted!r}")
        assert "[REDACTED_IFSC_CODE]" in redacted
        assert ifsc not in redacted


# ---------------------------------------------------------------------------
# Case 3 — Sentence mixing UPI + IFSC + person name
# ---------------------------------------------------------------------------
def test_mixed_upi_ifsc_name():
    text = (
        "Please transfer funds from Rahul Sharma's account. "
        "His UPI is rahul.sharma@okaxis and the destination IFSC is HDFC0001234."
    )
    results = detect_pii(text)
    types = [r.type for r in results]
    values = {r.type: r.value for r in results}

    print(f"\nINPUT  : {text!r}")
    print(f"FOUND  :")
    for r in results:
        print(f"  type={r.type!r}  value={r.value!r}  span=[{r.start}:{r.end}]")

    assert "UPI_ID" in types, f"UPI_ID not detected; types={types}"
    assert "IFSC_CODE" in types, f"IFSC_CODE not detected; types={types}"
    assert "PERSON" in types, f"PERSON not detected; types={types}"

    redacted = redact_text(text, results)
    print(f"REDACTED: {redacted!r}")
    assert "[REDACTED_UPI_ID]" in redacted
    assert "[REDACTED_IFSC_CODE]" in redacted
    assert "rahul.sharma@okaxis" not in redacted
    assert "HDFC0001234" not in redacted


# ---------------------------------------------------------------------------
# Case 4 — Hinglish sentence with UPI ID
# ---------------------------------------------------------------------------
def test_hinglish_upi():
    text = (
        "bhai mujhe 500 rupay bhej de, mera UPI hai 9876543210@ybl, "
        "abhi transfer kar do."
    )
    results = detect_pii(text)
    types = [r.type for r in results]

    print(f"\nINPUT : {text!r}")
    print(f"FOUND : {[(r.type, r.value) for r in results]}")

    assert "UPI_ID" in types, f"UPI_ID not detected in Hinglish context; types={types}"

    redacted = redact_text(text, results)
    print(f"REDACTED: {redacted!r}")
    assert "[REDACTED_UPI_ID]" in redacted
    assert "9876543210@ybl" not in redacted


# ---------------------------------------------------------------------------
# Case 5 — Control: regular email address must NOT be flagged as UPI
# ---------------------------------------------------------------------------
class TestEmailNotUPI:
    REGULAR_EMAILS = [
        "user@gmail.com",
        "contact@example.com",
        "test@yahoo.co.in",
        "info@company.org",
        "admin@hotmail.com",
    ]

    @pytest.mark.parametrize("email", REGULAR_EMAILS)
    def test_email_not_flagged_as_upi(self, email):
        results = detect_pii(email)
        upi_hits = [r for r in results if r.type == "UPI_ID"]

        print(f"\nINPUT     : {email!r}")
        print(f"ALL FOUND : {[(r.type, r.value) for r in results]}")
        print(f"UPI hits  : {upi_hits}")

        assert upi_hits == [], (
            f"Regular email {email!r} was incorrectly flagged as UPI_ID"
        )
