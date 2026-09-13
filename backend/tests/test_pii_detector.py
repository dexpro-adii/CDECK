import pytest
import os
import sys

# Add backend to path to allow tests to run
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from detectors.pii_detector import detect_pii, redact_text

def test_clean_sentence():
    text = "Hello, what is the weather today in Delhi?"
    results = detect_pii(text)
    assert len(results) == 0

def test_aadhaar_alone():
    text = "1234 5678 9012"
    results = detect_pii(text)
    assert len(results) > 0
    assert any(r.type == "AADHAAR" for r in results)
    
    redacted = redact_text(text, results)
    assert redacted == "[REDACTED_AADHAAR]"

def test_aadhaar_compact():
    text = "123456789012"
    results = detect_pii(text)
    assert any(r.type == "AADHAAR" for r in results)

def test_pan_alone():
    text = "ABCDE1234F"
    results = detect_pii(text)
    assert len(results) > 0
    assert any(r.type == "PAN" for r in results)
    
    redacted = redact_text(text, results)
    assert redacted == "[REDACTED_PAN]"

def test_phone_name_mixed():
    text = "My name is John Doe and my number is +91 9876543210."
    results = detect_pii(text)
    assert len(results) >= 2
    types = [r.type for r in results]
    assert "PERSON" in types
    assert "PHONE_IN" in types

def test_hinglish_aadhaar():
    text = "mera aadhaar number 1234 5678 9012 hai, please check."
    results = detect_pii(text)
    assert len(results) > 0
    assert any(r.type == "AADHAAR" for r in results)
    
    redacted = redact_text(text, results)
    assert "[REDACTED_AADHAAR]" in redacted
    assert "1234 5678 9012" not in redacted

def test_email():
    text = "Contact me at test@example.com"
    results = detect_pii(text)
    assert any(r.type == "EMAIL" for r in results)
    redacted = redact_text(text, results)
    assert "[REDACTED_EMAIL]" in redacted

def test_pin_code():
    text = "My pin code is 110001."
    results = detect_pii(text)
    assert any(r.type == "PIN_CODE" for r in results)
    
    text2 = "delivery to 400001 today"
    results2 = detect_pii(text2)
    assert any(r.type == "PIN_CODE" for r in results2)

def test_multiple_pii_redaction():
    text = "John has PAN ABCDE1234F and his phone is 9876543210."
    results = detect_pii(text)
    redacted = redact_text(text, results)
    assert "[REDACTED_PERSON]" in redacted
    assert "[REDACTED_PAN]" in redacted
    assert "[REDACTED_PHONE_IN]" in redacted
    assert "ABCDE1234F" not in redacted
    assert "9876543210" not in redacted


def test_order_id_not_pin_code():
    """Order numbers like #123456 must NOT be flagged as PIN_CODE."""
    text = "My order #123456"
    results = detect_pii(text)
    assert not any(r.type in ("PIN_CODE", "AADHAAR") for r in results)


def test_otp_not_pin_code():
    """6-digit OTPs must NOT be flagged as PIN_CODE."""
    text = "My OTP is 483920"
    results = detect_pii(text)
    assert not any(r.type in ("PIN_CODE", "AADHAAR") for r in results)


def test_amount_not_pin_code():
    """6-digit currency amounts must NOT be flagged as PIN_CODE."""
    text = "Transaction amount was 100000 rupees"
    results = detect_pii(text)
    assert not any(r.type in ("PIN_CODE", "AADHAAR") for r in results)


def test_year_range_not_aadhaar():
    """4-4-4 year sequences must NOT be flagged as AADHAAR due to Verhoeff check."""
    text = "The year range 2020 2021 2022"
    results = detect_pii(text)
    assert not any(r.type in ("PIN_CODE", "AADHAAR") for r in results)


def test_real_aadhaar_verhoeff():
    """Valid 12-digit Aadhaar numbers with correct Verhoeff checksum must match."""
    text = "My Aadhaar is 3675 9834 6016."
    results = detect_pii(text)
    assert any(r.type == "AADHAAR" for r in results)
    redacted = redact_text(text, results)
    assert "[REDACTED_AADHAAR]" in redacted
    assert "3675 9834 6016" not in redacted

