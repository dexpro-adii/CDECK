"""
Enhanced Output Rail for CDECK (PromptKavach).

Checks BEFORE any LLM response reaches the user:
  1. PII detection & redaction (Aadhaar, PAN, IFSC, UPI, phone, email, etc.)
  2. Secret / credential leakage:
     - API keys: OpenAI sk-, AWS AKIA, GitHub ghp_, Google AIza, HF hf_
     - JWT tokens
     - Connection strings (postgres://, mysql://, mongodb://)
     - Private keys (PEM headers)
     - Generic high-entropy tokens (Shannon entropy >= 4.5 for long secrets)
  3. Canary token detection:
     - A canary token can be planted in the system prompt; if the LLM echoes it
       the response is immediately blocked.
  4. Jailbreak / instruction-echo detection (existing pipeline).
  5. Blocked-request compliance escalation:
     - If the incoming request was flagged/blocked but the model still attempted
       to respond helpfully, the output rail escalates immediately.

All actions are configurable: "redact", "block", or "warn".
"""
from __future__ import annotations

import re
import math
import os
from typing import Dict, Any, Optional

from detectors.pii_detector import detect_pii, redact_pii
from detectors.jailbreak_detector import detect_jailbreak

# ---------------------------------------------------------------------------
# Canary Token
# ---------------------------------------------------------------------------
# The canary is a random nonce injected into the system prompt. If it appears
# in the model's output, the system prompt has been leaked.
_CANARY_TOKEN: Optional[str] = None
_CANARY_PATTERN: Optional[re.Pattern] = None

def set_canary_token(token: str) -> None:
    """Plant a new canary token (call once at startup or on rotation)."""
    global _CANARY_TOKEN, _CANARY_PATTERN
    _CANARY_TOKEN = token
    # Escape the token and match it case-insensitively
    _CANARY_PATTERN = re.compile(re.escape(token), re.IGNORECASE)

def _check_canary(text: str) -> bool:
    """Returns True if the canary token appears in the output (system prompt leak)."""
    if _CANARY_PATTERN is None:
        return False
    return bool(_CANARY_PATTERN.search(text))

# ---------------------------------------------------------------------------
# Secret / Credential Patterns
# ---------------------------------------------------------------------------
_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    # OpenAI API key
    ("openai_api_key",      re.compile(r'\bsk-[A-Za-z0-9]{20,}\b')),
    # OpenAI Project key
    ("openai_proj_key",     re.compile(r'\bsk-proj-[A-Za-z0-9_-]{20,}\b')),
    # AWS Access Key ID
    ("aws_access_key",      re.compile(r'\bAKIA[A-Z0-9]{16}\b')),
    # AWS Secret Access Key (40 chars hex/base36)
    ("aws_secret_key",      re.compile(r'(?:aws_secret|AWS_SECRET)[_\s=:]+[A-Za-z0-9/+]{40}\b', re.IGNORECASE)),
    # GitHub PAT
    ("github_pat",          re.compile(r'\bghp_[A-Za-z0-9]{36,}\b')),
    # Google API key
    ("google_api_key",      re.compile(r'\bAIza[A-Za-z0-9_-]{35}\b')),
    # Hugging Face token
    ("hf_token",            re.compile(r'\bhf_[A-Za-z0-9]{36,}\b')),
    # JWT (3 base64url segments)
    ("jwt_token",           re.compile(r'\beyJ[A-Za-z0-9_=-]+\.eyJ[A-Za-z0-9_=-]+\.[A-Za-z0-9_=.-]+\b')),
    # PEM private key header
    ("pem_private_key",     re.compile(r'-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----')),
    # Database connection strings
    ("db_conn_postgres",    re.compile(r'\bpostgres(?:ql)?://[^\s"\'<>]+\b', re.IGNORECASE)),
    ("db_conn_mysql",       re.compile(r'\bmysql://[^\s"\'<>]+\b', re.IGNORECASE)),
    ("db_conn_mongodb",     re.compile(r'\bmongodb(?:\+srv)?://[^\s"\'<>]+\b', re.IGNORECASE)),
    # Generic bearer token assignment
    ("bearer_token",        re.compile(r'(?:bearer|token|secret|password|passwd|api[-_]?key)\s*[:=]\s*["\']?[A-Za-z0-9+/._-]{20,}["\']?', re.IGNORECASE)),
]

# Documentation false-positive allow patterns (exact placeholder strings)
_SECRET_ALLOWLIST_RE = re.compile(
    r'(?:sk-xxxx|AKIA_EXAMPLE|YOUR_API_KEY|<YOUR_TOKEN>|example_token|'
    r'xxx+|placeholder|dummy|fake|test_key|REPLACE_ME)',
    re.IGNORECASE
)

def _check_secrets(text: str) -> list[dict[str, str]]:
    """
    Returns a list of dicts with keys: type, match, start, end.
    Skips documentation placeholder patterns.
    """
    hits = []
    for secret_type, pattern in _SECRET_PATTERNS:
        for m in pattern.finditer(text):
            snippet = m.group()
            if _SECRET_ALLOWLIST_RE.search(snippet):
                continue
            hits.append({
                "type": secret_type,
                "match": snippet[:60] + ("..." if len(snippet) > 60 else ""),
                "start": m.start(),
                "end": m.end()
            })
    return hits

# ---------------------------------------------------------------------------
# Shannon Entropy Check for generic high-entropy secrets
# ---------------------------------------------------------------------------
_HIGH_ENTROPY_RE = re.compile(r'[A-Za-z0-9+/._=-]{32,}')

def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    n = len(s)
    return -sum((f/n) * math.log2(f/n) for f in freq.values())

def _check_high_entropy_tokens(text: str) -> list[dict[str, str]]:
    """Detects generic high-entropy credential tokens (>= 32 chars, entropy >= 4.5)."""
    hits = []
    for m in _HIGH_ENTROPY_RE.finditer(text):
        token = m.group()
        if _SECRET_ALLOWLIST_RE.search(token):
            continue
        entropy = _shannon_entropy(token)
        if entropy >= 4.5:
            hits.append({
                "type": "high_entropy_token",
                "match": token[:60] + ("..." if len(token) > 60 else ""),
                "start": m.start(),
                "end": m.end(),
                "entropy": round(entropy, 3)
            })
    return hits

# ---------------------------------------------------------------------------
# Main scan_output API
# ---------------------------------------------------------------------------
def scan_output(
    response_text: str,
    input_was_blocked: bool = False,
    action: str = "block"  # "block" | "redact" | "warn"
) -> Dict[str, Any]:
    """
    Scans the LLM's generated response before it reaches the user.

    Parameters
    ----------
    response_text : str
        Raw text from the downstream LLM.
    input_was_blocked : bool
        Set True if the corresponding input was flagged/blocked. A compliant-
        looking response when the input was blocked is immediately escalated.
    action : str
        "block"  — replace the entire response with a sentinel message.
        "redact" — redact only the sensitive portions in-place.
        "warn"   — allow the response through but mark output_flagged=True.

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
        secrets_detected (list[dict])
        canary_leaked (bool)
        compliance_escalated (bool)
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
            "secrets_detected": [],
            "canary_leaked": False,
            "compliance_escalated": False,
        }

    redacted_response = response_text
    output_pii_found = []
    secrets_detected = []
    canary_leaked = False
    compliance_escalated = False
    is_leak = False
    risk_level = "low"
    matched_phrase = None
    matched_similarity = None

    # ------------------------------------------------------------------ #
    # 1. Canary token check                                                 #
    # ------------------------------------------------------------------ #
    canary_leaked = _check_canary(response_text)
    if canary_leaked:
        is_leak = True
        risk_level = "high"
        matched_phrase = "canary_token_echo"

    # ------------------------------------------------------------------ #
    # 2. Secret / credential detection                                      #
    # ------------------------------------------------------------------ #
    secrets_detected = _check_secrets(response_text)
    entropy_hits = _check_high_entropy_tokens(response_text)
    # Don't double-count positions already matched by named patterns
    matched_positions = {h["start"] for h in secrets_detected}
    for eh in entropy_hits:
        if eh["start"] not in matched_positions:
            secrets_detected.append(eh)

    if secrets_detected:
        is_leak = True
        risk_level = "high"
        if not matched_phrase:
            matched_phrase = f"secret:{secrets_detected[0]['type']}"

    # ------------------------------------------------------------------ #
    # 3. PII detection & redaction                                          #
    # ------------------------------------------------------------------ #
    pii_entities = detect_pii(response_text)
    output_pii_found = pii_entities
    if pii_entities:
        if action in ("block", "redact"):
            redacted_response = redact_pii(response_text, pii_entities)

    # ------------------------------------------------------------------ #
    # 4. Jailbreak / instruction-echo detection                             #
    # ------------------------------------------------------------------ #
    if not canary_leaked and not secrets_detected:
        jb_res = detect_jailbreak(redacted_response, enable_hybrid=False)
        jb_risk = jb_res.risk_level
        if jb_risk in ("high", "medium"):
            is_leak = True
            risk_level = jb_risk
            matched_phrase = jb_res.matched_phrase
            matched_similarity = jb_res.matched_phrase_similarity

    # ------------------------------------------------------------------ #
    # 5. Blocked-request compliance escalation                              #
    # ------------------------------------------------------------------ #
    if input_was_blocked and response_text.strip() and not is_leak:
        # Model responded substantively despite input being blocked — escalate
        # Only trigger if the response is non-trivial (> 30 chars)
        if len(response_text.strip()) > 30:
            compliance_escalated = True
            is_leak = True
            risk_level = "high"
            matched_phrase = "compliance_violation_on_blocked_input"

    # ------------------------------------------------------------------ #
    # 6. Apply action                                                       #
    # ------------------------------------------------------------------ #
    if is_leak and action == "block":
        kind = "canary leak" if canary_leaked else ("credential exposure" if secrets_detected else "policy violation")
        redacted_response = (
            f"[BLOCKED BY OUTPUT RAIL: {kind.title()} detected in model response]"
        )
    elif is_leak and action == "redact":
        # Already redacted PII above. Mask secrets in-place.
        for secret in secrets_detected:
            redacted_response = redacted_response.replace(
                secret["match"].rstrip("..."),
                f"[REDACTED_{secret['type'].upper()}]"
            )

    output_flagged = bool(output_pii_found) or is_leak

    return {
        "output_flagged": output_flagged,
        "output_pii_found": output_pii_found,
        "output_redacted_response": redacted_response,
        "output_leak_detected": is_leak,
        "output_leak_risk_level": risk_level,
        "output_leak_matched_phrase": matched_phrase if is_leak else None,
        "output_leak_similarity": float(matched_similarity) if (is_leak and matched_similarity is not None) else None,
        "secrets_detected": [{"type": s["type"], "match": s["match"]} for s in secrets_detected],
        "canary_leaked": canary_leaked,
        "compliance_escalated": compliance_escalated,
    }
