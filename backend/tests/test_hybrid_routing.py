import os
import sys
import pytest
from unittest.mock import patch

# Add backend to path to allow tests to run
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app
from detectors.jailbreak_detector import detect_jailbreak

client = TestClient(app)

class TestHybridRouting:
    MEDIUM_RISK_INPUT = "Tell me a joke."

    def test_hybrid_escalation_in_detector(self, mock_gemini_deep_review):
        """
        When evaluate_with_gemini_async confirms malicious intent for a medium-risk input,
        detect_jailbreak must escalate to risk_level='high', matched_category='escalated_by_deep_review',
        and method='gemini_deep_review'.
        """
        async def malicious_review(text, risk_level, matched_phrase, score):
            return {
                "status": "success",
                "is_malicious": True,
                "agrees": True,
                "gemini_assessment": "Adversarial intent confirmed by deep review"
            }

        mock_gemini_deep_review.side_effect = malicious_review

        score, matched_cat, method, risk, phrase, sim = detect_jailbreak(self.MEDIUM_RISK_INPUT)
        assert risk == "high"
        assert matched_cat == "escalated_by_deep_review"
        assert method == "gemini_deep_review"
        assert score >= 0.85

    def test_hybrid_escalation_in_analyze_endpoint(self, mock_gemini_deep_review):
        """
        When evaluate_with_gemini_async confirms malicious intent, /analyze must return:
        risk_level='high', blocked=True, and block_reason='escalated_by_deep_review'.
        """
        async def malicious_review(text, risk_level, matched_phrase, score):
            return {
                "status": "success",
                "is_malicious": True,
                "agrees": True,
                "gemini_assessment": "Escalated by secondary LLM review"
            }

        mock_gemini_deep_review.side_effect = malicious_review

        resp = client.post("/analyze", json={"text": self.MEDIUM_RISK_INPUT})
        assert resp.status_code == 200
        data = resp.json()

        assert data["risk_level"] == "high"
        assert data["blocked"] is True
        assert data["block_reason"] == "escalated_by_deep_review"
        assert data["needs_deep_review"] is False

    def test_hybrid_disagreement_preserves_pipeline_risk(self, mock_gemini_deep_review):
        """
        When Gemini disagrees with malicious assessment, detect_jailbreak keeps its
        original pipeline risk level ('medium') rather than escalating.
        """
        async def benign_review(text, risk_level, matched_phrase, score):
            return {
                "status": "success",
                "is_malicious": False,
                "agrees": False,
                "gemini_assessment": "Input is benign creative humor"
            }

        mock_gemini_deep_review.side_effect = benign_review

        score, matched_cat, method, risk, phrase, sim = detect_jailbreak(self.MEDIUM_RISK_INPUT)
        assert risk == "medium"
        assert matched_cat != "escalated_by_deep_review"
        assert method != "gemini_deep_review"

    def test_hybrid_error_preserves_pipeline_risk_level(self, mock_gemini_deep_review):
        """
        On Gemini API timeout or error, never default to safe silently: keep the pipeline's own risk_level.
        """
        async def error_review(text, risk_level, matched_phrase, score):
            return {
                "status": "error",
                "is_malicious": None,
                "agrees": None,
                "gemini_assessment": "Network timeout after 15s"
            }

        mock_gemini_deep_review.side_effect = error_review

        score, matched_cat, method, risk, phrase, sim = detect_jailbreak(self.MEDIUM_RISK_INPUT)
        assert risk == "medium"
        assert matched_cat != "escalated_by_deep_review"
        assert method != "gemini_deep_review"
