import os
import asyncio
from typing import Optional
from dotenv import load_dotenv

# Load environment variables on module import
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)
if "GOOGLE_API_KEY" in os.environ and "GEMINI_API_KEY" not in os.environ:
    os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]

from fastapi import FastAPI, Header, HTTPException
try:
    from ollama import AsyncClient
except ImportError:
    AsyncClient = None
from fastapi.middleware.cors import CORSMiddleware
from models.schemas import (AnalyzeRequest, AnalyzeResponse, AnalyzeContentRequest, 
                            AnalyzeContentResponse, CheckToolCallRequest, CheckToolCallResponse, 
                            VaultMaskRequest, VaultMaskResponse, VaultToken, 
                            VaultResolveRequest, VaultResolveResponse,
                            ExplainVerdictRequest, ExplainVerdictResponse,
                            DeepReviewRequest, DeepReviewResponse)
from tool_security import TOOL_RISK_MAP
from detectors.pii_detector import detect_pii, redact_pii
from detectors.jailbreak_detector import detect_jailbreak, is_code_mixed, evaluate_with_gemini_async
from detectors.output_scanner import scan_output
from vault import SessionVault
from collections import defaultdict, deque
import re as _re

# Regex to extract a planted trigger keyword from text like:
# "Remember the word: PERSIST" / "Trigger keyword: ACTIVATE"
_TRIGGER_PLANT_RE = _re.compile(
    r"(?i)(?:remember\s+the\s+(?:word|phrase|keyword|code\s*word)|trigger\s+(?:word|phrase|keyword))[\s:\-]+([A-Z][A-Z0-9_]{2,20})"
)

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")

# In-memory session tracking: session_id -> deque(maxlen=10) of risk_levels
session_history = defaultdict(lambda: deque(maxlen=10))

# Cross-turn trigger word memory: session_id -> set of uppercase trigger words
# e.g. {"default_session": {"PERSIST", "ACTIVATE"}}
session_trigger_words: dict = defaultdict(set)

app = FastAPI(title="PromptKavach API")

# Configure CORS with explicit origins for local dev
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # Ensure environment variables are loaded
    load_dotenv(dotenv_path)
    if "GOOGLE_API_KEY" in os.environ and "GEMINI_API_KEY" not in os.environ:
        os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]
        
    if AsyncClient is not None:
        print(f"Warming up Ollama model ({OLLAMA_MODEL})...")
        try:
            client = AsyncClient()
            await asyncio.wait_for(
                client.generate(model=OLLAMA_MODEL, prompt='Hello', options={"num_predict": 1}),
                timeout=2.0
            )
            print("Ollama model warmed up successfully.")
        except Exception as e:
            print(f"Warning: Failed to warm up Ollama model: {e}")

# Session PII vault. Values are held encrypted with a TTL -- see vault.py and
# the "Vault key custody" section of the README for the threat model and the
# gaps this does NOT close.
vault = SessionVault()


def mask_with_vault(text, session_id, pii_entities):
    """
    Replaces each PII entity with a reversible vault placeholder (<TYPE_n>) and
    records the original value under session_id so /vault/resolve can restore it.

    Shared by /vault/mask and the retrieval rail (/analyze-content) so both use
    one masking implementation.
    """
    priority = {"AADHAAR": 10, "PAN": 10, "PHONE_IN": 10, "PIN_CODE": 10}
    sorted_entities = sorted(
        pii_entities,
        key=lambda x: (x.start, x.end - x.start, priority.get(x.type, 0)),
        reverse=True
    )

    masked_text = text
    last_start = len(text) + 1
    tokens = []

    for entity in sorted_entities:
        if entity.end > last_start:
            continue

        placeholder = vault.next_placeholder(session_id, entity.type)
        vault.store(session_id, placeholder, entity.value)
        tokens.append(VaultToken(placeholder=placeholder, type=entity.type))

        masked_text = masked_text[:entity.start] + placeholder + masked_text[entity.end:]
        last_start = entity.start

    return masked_text, tokens

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_prompt(request: AnalyzeRequest):
    text = request.text
    session_id = request.session_id or "default_session"
    
    # 1. Jailbreak Detection
    jailbreak_score, jb_category, jb_method, risk_level, matched_phrase, matched_phrase_similarity = detect_jailbreak(text)
    
    needs_deep_review = is_code_mixed(text)
    
    is_jailbreak = risk_level == "high"
    
    # 2. PII Detection
    pii_entities = detect_pii(text)
    is_pii = len(pii_entities) > 0
    
    # 3. Redaction
    redacted_text = redact_pii(text, pii_entities)
    
    # 4. Forwarding (Mocked)
    forwarded_response = "This is a mocked LLM response for: " + redacted_text

    
    # Logic to block
    blocked = False
    block_reason = None
    
    # 5. Session-based Behavior Tracking
    history = session_history[session_id]
    history.append(risk_level)

    suspicious_count = sum(1 for r in history if r in ["medium", "high"])
    escalated = suspicious_count >= 3
    escalation_reason = "Repeated suspicious activity detected in this session" if escalated else None

    # 6. Cross-turn trigger word tracking
    # Phase A — planting: did this message register a trigger word?
    plant_match = _TRIGGER_PLANT_RE.search(text)
    if plant_match:
        trigger_word = plant_match.group(1).upper()
        session_trigger_words[session_id].add(trigger_word)
        # The planting message itself is already an attack; ensure it is blocked
        if not blocked:
            is_jailbreak = True
            blocked = True
            block_reason = "cross_turn_trigger_planted"
            forwarded_response = ""
            output_flagged = False
            output_pii_found = []
            output_redacted_response = ""

    # Phase B — activation: does this message contain a previously planted trigger?
    if not blocked:
        for trigger in session_trigger_words[session_id]:
            if trigger in text.upper():
                is_jailbreak = True
                blocked = True
                block_reason = "cross_turn_trigger_activated"
                forwarded_response = ""
                output_flagged = False
                output_pii_found = []
                output_redacted_response = ""
                escalation_reason = f"Cross-turn trigger '{trigger}' activated from earlier session message"
                break
    
    if is_jailbreak:
        blocked = True
        if jb_category == "escalated_by_deep_review" or jb_method == "gemini_deep_review":
            block_reason = "escalated_by_deep_review"
        else:
            block_reason = "jailbreak_detected"
        forwarded_response = ""
        output_flagged = False
        output_pii_found = []
        output_redacted_response = ""
    else:
        # 6. Output Rail: scan the generated response
        out = scan_output(forwarded_response)
        output_flagged = out["output_flagged"]
        output_pii_found = out["output_pii_found"]
        output_redacted_response = out["output_redacted_response"]
        
        if out.get("output_leak_detected") or (output_redacted_response and output_redacted_response.startswith("[BLOCKED BY OUTPUT RAIL")):
            blocked = True
            block_reason = "output_rail_blocked"
        
    return AnalyzeResponse(
        blocked=blocked,
        block_reason=block_reason,
        jailbreak_score=jailbreak_score,
        risk_level=risk_level,
        matched_phrase=matched_phrase,
        matched_phrase_similarity=matched_phrase_similarity,
        pii_found=pii_entities,
        redacted_text=redacted_text,
        forwarded_response=output_redacted_response if not blocked else "",
        escalated=escalated,
        escalation_reason=escalation_reason,
        needs_deep_review=needs_deep_review,
        output_flagged=output_flagged,
        output_pii_found=output_pii_found,
        output_redacted_response=output_redacted_response
    )

@app.post("/deep-review", response_model=DeepReviewResponse)
async def deep_review(request: DeepReviewRequest):
    result = await evaluate_with_gemini_async(
        request.text, 
        request.risk_level, 
        request.matched_phrase or "", 
        request.jailbreak_score
    )
    return DeepReviewResponse(**result)

@app.post("/analyze-content", response_model=AnalyzeContentResponse)
async def analyze_content(request: AnalyzeContentRequest):
    jailbreak_score, jb_category, jb_method, risk_level, matched_phrase, matched_phrase_similarity = detect_jailbreak(request.content)
    is_jailbreak = risk_level == "high"

    blocked = False
    block_reason = None
    if is_jailbreak:
        blocked = True
        block_reason = "jailbreak_detected"

    # PII rail: retrieved content reaches the model's context just like user
    # input does, so it gets the same treatment as the input rail. With a
    # session_id the values are vaulted (reversible); without one they are
    # redacted outright, which is the safer default for untrusted sources.
    pii_entities = detect_pii(request.content)
    session_token = None
    if request.session_id:
        safe_text, _ = mask_with_vault(request.content, request.session_id, pii_entities)
        session_token = vault.session_token(request.session_id)
    else:
        safe_text = redact_pii(request.content, pii_entities)

    return AnalyzeContentResponse(
        blocked=blocked,
        block_reason=block_reason,
        jailbreak_score=jailbreak_score,
        risk_level=risk_level,
        matched_phrase=matched_phrase,
        matched_phrase_similarity=matched_phrase_similarity,
        pii_found=pii_entities,
        redacted_text=safe_text,
        forwarded_response="",
        escalated=False,
        escalation_reason=None,
        source=request.source,
        session_token=session_token
    )

@app.post("/check-tool-call", response_model=CheckToolCallResponse)
async def check_tool_call(request: CheckToolCallRequest):
    risk = TOOL_RISK_MAP.get(request.tool_name, "MEDIUM")
    
    args_str = " ".join([str(v) for v in request.arguments.values()])
    
    pii_entities = detect_pii(args_str)
    pii_found = len(pii_entities) > 0
    
    if risk == "CRITICAL":
        decision = "ASK_USER"
        reason = "Critical risk tool calls always require user confirmation"
    elif risk == "HIGH":
        if pii_found:
            decision = "BLOCK"
            reason = "High risk tool call containing PII"
        else:
            decision = "ASK_USER"
            reason = "High risk tool call requires user confirmation"
    else: # LOW / MEDIUM
        if pii_found:
            decision = "ASK_USER"
            reason = "Tool call containing PII requires user confirmation"
        else:
            decision = "ALLOW"
            reason = "Safe tool call"
            
    return CheckToolCallResponse(
        decision=decision,
        risk=risk,
        pii_found=pii_found,
        reason=reason
    )

@app.post("/vault/mask", response_model=VaultMaskResponse)
async def vault_mask(request: VaultMaskRequest):
    pii_entities = detect_pii(request.text)
    masked_text, tokens = mask_with_vault(request.text, request.session_id, pii_entities)
    return VaultMaskResponse(
        masked_text=masked_text,
        tokens=tokens,
        session_token=vault.session_token(request.session_id),
    )

@app.post("/vault/resolve", response_model=VaultResolveResponse)
async def vault_resolve(
    request: VaultResolveRequest,
    x_vault_token: Optional[str] = Header(default=None),
):
    """
    Restores vaulted PII for the session that owns it.

    This endpoint hands back plaintext Aadhaar/PAN/UPI values, so a session_id
    is treated as an identifier, never as a credential. The caller must present
    the bearer secret issued when the session was created (returned as
    `session_token` by /vault/mask and /analyze-content).

    Unknown session and wrong token both return the same 401, so the response
    cannot be used to enumerate live session ids.
    """
    if not vault.verify(request.session_id, x_vault_token):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid X-Vault-Token for this session.",
        )

    text = vault.resolve_text(request.session_id, request.masked_text)
    return VaultResolveResponse(text=text)

@app.post("/explain-verdict", response_model=ExplainVerdictResponse)
async def explain_verdict(request: ExplainVerdictRequest):
    fallback_explanation = f"System matched pattern '{request.category}' with {request.jailbreak_score:.2f} confidence resulting in {request.risk_level.upper()} risk."
    
    if AsyncClient is None:
        return ExplainVerdictResponse(explanation=fallback_explanation)
    
    prompt = f"""You are a security analyst explaining an automated prompt injection/jailbreak detection verdict.
The decision is ALREADY FINAL. Do not evaluate it or override it. Your only job is to explain the decision clearly in 1-2 sentences.

Verdict details:
- Input prompt: "{request.prompt_text}"
- Risk Level: {request.risk_level.upper()}
- Score: {request.jailbreak_score:.2f}
- Matched Category: {request.category}
- Matched Phrase: {request.matched_phrase}

Why was this verdict reached based on these details? Explain it to a user in 1-2 concise, human-readable sentences."""

    try:
        client = AsyncClient()
        response = await asyncio.wait_for(
            client.generate(model=OLLAMA_MODEL, prompt=prompt, options={"num_predict": 200}),
            timeout=15.0
        )
        explanation = response['response'].strip()
        if not explanation:
            explanation = fallback_explanation
        return ExplainVerdictResponse(explanation=explanation)
    except Exception as e:
        # Fallback on timeout or Ollama not running
        return ExplainVerdictResponse(explanation=fallback_explanation)
