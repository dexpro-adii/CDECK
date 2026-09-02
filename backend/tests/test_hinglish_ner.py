"""
Regression tests for Hinglish PERSON false positives.

Presidio's PERSON recogniser runs an English spaCy model, so romanised Hindi
tokens come back as proper nouns. Before the fix, every one of these sentences
produced at least one bogus PERSON span -- e.g. "Bhai mera phone number update
karna hai" yielded PERSON spans "Bhai mera" and "karna hai".

The fix trims Hinglish function words off the edges of PERSON spans and drops
spans with nothing name-like left. These tests pin both directions: the noise
stays gone, and genuine names are still detected.
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest

from detectors.pii_detector import (
    _looks_code_mixed, detect_pii, redact_text,
)

# Every one of these mistagged before the fix.
HINGLISH_NO_NAMES = [
    "Bhai mera phone number update karna hai",
    "Thoda help chahiye account ke liye",
    "Yeh scheme ke rules kya hain, thoda samjha do",
    "Mujhe apna account balance check karna hai",
    "Bhai UPI se payment kaise karte hain?",
    "Kya main apna registered email address change kar sakta hoon?",
    "Aapka order kab tak deliver hoga bhai?",
    "Achha theek hai, main baad me call karta hoon",
    "Arre yaar yeh kaam nahi ho raha hai",
    "Bank me KYC update karne ke liye kya chahiye?",
    "Paisa kab tak aayega bhai, thoda batao",
]


@pytest.mark.parametrize("text", HINGLISH_NO_NAMES)
def test_hinglish_filler_is_not_a_person(text):
    persons = [e.value for e in detect_pii(text) if e.type == "PERSON"]
    assert persons == [], f"Hinglish filler mistagged as PERSON: {persons} in {text!r}"


def test_real_name_inside_hinglish_survives():
    """The trim must not throw away the actual name it is wrapped around."""
    text = "Mera naam Rahul Sharma hai aur number 9876543210 hai"
    entities = detect_pii(text)

    persons = [e.value for e in entities if e.type == "PERSON"]
    assert "Rahul Sharma" in persons, f"real name lost, got {persons}"
    # the surrounding filler must not be part of the span
    assert not any("naam" in p or "hai" in p for p in persons), persons
    # and the phone number is still caught
    assert any(e.type == "PHONE_IN" for e in entities)


def test_person_offsets_stay_consistent_after_trim():
    """A trimmed span must still point at its own text, so redaction is correct."""
    text = "Mera naam Rahul Sharma hai aur number 9876543210 hai"
    for e in detect_pii(text):
        assert text[e.start:e.end] == e.value, (
            f"offset drift on {e.type}: span={text[e.start:e.end]!r} value={e.value!r}"
        )

    redacted = redact_text(text, detect_pii(text))
    assert "Rahul Sharma" not in redacted
    assert "[REDACTED_PERSON]" in redacted


def test_english_names_unaffected():
    """The stoplist must not disturb ordinary English detection."""
    text = "My name is John Doe and my number is +91 9876543210."
    persons = [e.value for e in detect_pii(text) if e.type == "PERSON"]
    assert "John Doe" in persons, persons

    text2 = "Please contact Priya Verma regarding the loan application."
    persons2 = [e.value for e in detect_pii(text2) if e.type == "PERSON"]
    assert any("Priya" in p for p in persons2), persons2


def test_domain_acronyms_are_not_names():
    """UPI / KYC / IFSC are not people."""
    for text in ["Bhai UPI se payment kaise karte hain?",
                 "Bank me KYC update karne ke liye kya chahiye?"]:
        persons = [e.value for e in detect_pii(text) if e.type == "PERSON"]
        assert persons == [], persons


def test_code_mixed_detection():
    assert _looks_code_mixed("Bhai mera phone number update karna hai") is True
    assert _looks_code_mixed("Please reset my password.") is False


def test_indian_identifiers_still_detected_in_hinglish():
    """The stoplist touches PERSON only -- the regex recognisers are untouched."""
    text = "Bhai mera Aadhaar 1234 5678 9012 hai aur PAN ABCDE1234F hai"
    found = {e.type for e in detect_pii(text)}
    assert "AADHAAR" in found, found
    assert "PAN" in found, found
