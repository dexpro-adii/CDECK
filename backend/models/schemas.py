from pydantic import BaseModel
from typing import List, Optional, Literal, Dict, Any

class AnalyzeRequest(BaseModel):
    text: str
    session_id: Optional[str] = "default_session"

class PIIEntity(BaseModel):
    type: str
    value: str
    start: int
    end: int

class AnalyzeResponse(BaseModel):
    blocked: bool
    block_reason: Optional[str] = None
    jailbreak_score: float
    risk_level: str
    matched_phrase: Optional[str] = None
    matched_phrase_similarity: Optional[float] = None
    pii_found: List[PIIEntity]
    redacted_text: str
    forwarded_response: str
    escalated: Optional[bool] = False
    escalation_reason: Optional[str] = None
    needs_deep_review: Optional[bool] = False
    output_flagged: Optional[bool] = False
    output_pii_found: Optional[List[PIIEntity]] = []
    output_redacted_response: Optional[str] = None

class DeepReviewRequest(BaseModel):
    text: str
    risk_level: str
    matched_phrase: Optional[str] = None
    jailbreak_score: float

class DeepReviewResponse(BaseModel):
    status: Literal["success", "timeout", "error"]
    is_malicious: Optional[bool] = None
    agrees: Optional[bool] = None
    gemini_assessment: Optional[str] = None

class AnalyzeContentRequest(BaseModel):
    content: str
    source: Literal["webpage", "document", "tool_output"]

class AnalyzeContentResponse(AnalyzeResponse):
    source: str

class CheckToolCallRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]

class CheckToolCallResponse(BaseModel):
    decision: str
    risk: str
    pii_found: bool
    reason: str

class VaultMaskRequest(BaseModel):
    text: str
    session_id: str

class VaultToken(BaseModel):
    placeholder: str
    type: str

class VaultMaskResponse(BaseModel):
    masked_text: str
    tokens: List[VaultToken]

class VaultResolveRequest(BaseModel):
    session_id: str
    masked_text: str

class VaultResolveResponse(BaseModel):
    text: str

class ExplainVerdictRequest(BaseModel):
    prompt_text: str
    jailbreak_score: float
    risk_level: str
    category: Optional[str] = None
    matched_phrase: Optional[str] = None
    matched_phrase_similarity: Optional[float] = None

class ExplainVerdictResponse(BaseModel):
    explanation: str
