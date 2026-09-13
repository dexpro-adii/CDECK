import pytest
from unittest.mock import patch

@pytest.fixture(autouse=True)
def mock_gemini_deep_review():
    """
    Prevents unit tests from hanging on external live Google Gemini network calls or hitting API rate limits.
    """
    async def fake_evaluate_with_gemini(text, risk_level, matched_phrase, score):
        # In unit tests, treat 'dan' or 'unrestricted' or obvious jailbreaks as confirmed malicious
        text_lower = text.lower()
        is_mal = any(k in text_lower for k in ["dan", "unrestricted", "evil", "bypass"])
        return {
            "status": "success",
            "agrees": is_mal,
            "is_malicious": is_mal,
            "gemini_assessment": f"Mock Gemini review: is_malicious={is_mal}"
        }

    with patch("detectors.jailbreak_detector.evaluate_with_gemini_async", side_effect=fake_evaluate_with_gemini) as m:
        yield m
