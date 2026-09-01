"""
Output Rail — scans the LLM's generated response BEFORE it reaches the user.

This mirrors the NeMo Guardrails "Output Rails" concept: input-only filtering
leaves a gap where the LLM itself could produce or echo sensitive content even
on a clean input.  This module closes that gap by:

  1. Running PII detection on the response text and redacting any hits.
  2. Checking if the response embeds/echoes known jailbreak reference phrases
     (e.g., the model was tricked into repeating its own system instructions).

Public API
----------
scan_output(response_text: str) -> dict
    Returns a dict with keys:
        output_flagged          : bool
        output_pii_found        : List[PIIEntity]
        output_redacted_response: str
        output_leak_detected    : bool
        output_leak_risk_level  : str
        output_leak_matched_phrase : str | None
        output_leak_similarity  : float | None
"""

from __future__ import annotations

from detectors.pii_detector import detect_pii, redact_pii
from detectors.jailbreak_detector import detect_jailbreak


def scan_output(response_text: str) -> dict:
    """
    Scans the LLM output before returning it to the user.

    Steps
    -----
    1. PII Detection & Redaction
       Runs detect_pii() on the raw response text.  Any PII found is redacted
       in-place so it never reaches the end-user even if the model leaked it.

    2. Jailbreak / Leaked-instruction Detection
       Reuses the same detect_jailbreak() pipeline on the (already PII-
       redacted) response.  A "high" or "medium" risk level here means the
       response *looks like* a jailbreak phrase -- the canonical signal for a
       system-prompt leak or instruction-echo attack.

       When a leak is detected the response is replaced entirely with a safe
       sentinel message to prevent information disclosure.

    Parameters
    ----------
    response_text : str
        Raw text produced by the downstream LLM.

    Returns
    -------
    dict with keys:
        output_flagged (bool)
        output_pii_found (list[PIIEntity])
        output_redacted_response (str)
        output_leak_detected (bool)
        output_leak_risk_level (str)
        output_leak_matched_phrase (str | None)
        output_leak_similarity (float | None)
    """
    if not response_text or not response_text.strip():
        return {
            "output_flagged": False,
            "output_pii_found": [],
            "output_redacted_response": response_text or "",
            "output_leak_detected": False,
            "output_leak_risk_level": "low",
            "output_leak_matched_phrase": None,
            "output_leak_similarity": None,
        }

    # ------------------------------------------------------------------ #
    # Step 1 -- PII detection & redaction                                  #
    # ------------------------------------------------------------------ #
    pii_entities = detect_pii(response_text)
    is_pii = len(pii_entities) > 0
    redacted_response = redact_pii(response_text, pii_entities) if is_pii else response_text

    # ------------------------------------------------------------------ #
    # Step 2 -- Jailbreak / leaked-instruction phrase matching             #
    # ------------------------------------------------------------------ #
    (
        jb_score,
        jb_category,
        jb_method,
        risk_level,
        matched_phrase,
        matched_similarity,
    ) = detect_jailbreak(redacted_response)

    is_leak = risk_level in ("high", "medium")

    if is_leak:
        # Replace the response entirely to prevent information disclosure.
        redacted_response = (
            "[BLOCKED BY OUTPUT RAIL: Potential policy violation or "
            "data leak detected in response]"
        )

    output_flagged = is_pii or is_leak

    return {
        "output_flagged": output_flagged,
        "output_pii_found": pii_entities,
        "output_redacted_response": redacted_response,
        "output_leak_detected": is_leak,
        "output_leak_risk_level": risk_level,
        "output_leak_matched_phrase": matched_phrase if is_leak else None,
        "output_leak_similarity": float(matched_similarity) if (is_leak and matched_similarity is not None) else None,
    }

