from typing import List
from models.schemas import PIIEntity
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
import re

# Initialize engines
analyzer = AnalyzerEngine()

# Custom Pattern Recognizers for Indian Context
aadhaar_pattern = Pattern(
    name="aadhaar_pattern",
    regex=r"\b\d{4}\s?\d{4}\s?\d{4}\b",
    score=1.0
)
aadhaar_recognizer = PatternRecognizer(
    supported_entity="AADHAAR",
    patterns=[aadhaar_pattern]
)

pan_pattern = Pattern(
    name="pan_pattern",
    regex=r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b",
    score=1.0
)
pan_recognizer = PatternRecognizer(
    supported_entity="PAN",
    patterns=[pan_pattern]
)

phone_pattern = Pattern(
    name="indian_phone_pattern",
    regex=r"(?:\+91[\-\s]?)?[6-9]\d{9}\b",
    score=1.0
)
phone_recognizer = PatternRecognizer(
    supported_entity="PHONE_IN",
    patterns=[phone_pattern]
)

pin_pattern = Pattern(
    name="pin_code_pattern",
    regex=r"(?:(?i:pincode|pin)[\-\s:]*)?\b\d{6}\b",
    score=1.0
)
pin_recognizer = PatternRecognizer(
    supported_entity="PIN_CODE",
    patterns=[pin_pattern]
)

# UPI ID — username@<known-bank-handle>
# The handle is restricted to the closed set of RBI-registered UPI handles so
# that regular email addresses (user@gmail.com, user@example.com, etc.) are
# NOT matched.
_UPI_HANDLES = (
    r"okaxis|oksbi|okhdfcbank|okicici|ybl|ibl|axl|apl|paytm|upi"
    r"|sbi|hdfcbank|icici|kotak|indus|barodampay|mahb|utib|cbin"
    r"|cnrb|punb|ubi|idbi|aubank|fbl|rbl|scb|dbs|boi|yesbank"
    r"|pingpay|waaxis|jupiteraxis|naviaxis|freecharge|airtel|jio"
)
upi_pattern = Pattern(
    name="upi_id_pattern",
    regex=rf"\b[\w.\-]{{3,50}}@(?:{_UPI_HANDLES})\b",
    score=1.0
)
upi_recognizer = PatternRecognizer(
    supported_entity="UPI_ID",
    patterns=[upi_pattern]
)

# IFSC Code — 4 uppercase letters + literal '0' + 6 alphanumeric characters
# e.g. HDFC0001234, SBIN0000123
ifsc_pattern = Pattern(
    name="ifsc_pattern",
    regex=r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
    score=1.0
)
ifsc_recognizer = PatternRecognizer(
    supported_entity="IFSC_CODE",
    patterns=[ifsc_pattern]
)

# Add recognizers to analyzer
analyzer.registry.add_recognizer(aadhaar_recognizer)
analyzer.registry.add_recognizer(pan_recognizer)
analyzer.registry.add_recognizer(phone_recognizer)
analyzer.registry.add_recognizer(pin_recognizer)
analyzer.registry.add_recognizer(upi_recognizer)
analyzer.registry.add_recognizer(ifsc_recognizer)


def detect_pii(text: str) -> List[PIIEntity]:
    """
    Detects PII entities in the given text using Presidio.
    """
    if not text:
        return []
    
    # We run the analyzer for English, but it will catch the regexes regardless of language
    results = analyzer.analyze(
        text=text,
        entities=["PERSON", "EMAIL_ADDRESS", "AADHAAR", "PAN", "PHONE_IN", "PIN_CODE", "UPI_ID", "IFSC_CODE"],
        language='en'
    )
    
    entities = []
    for result in results:
        # Standardize email type name if needed
        entity_type = result.entity_type
        if entity_type == "EMAIL_ADDRESS":
            entity_type = "EMAIL"
            
        entities.append(
            PIIEntity(
                type=entity_type,
                value=text[result.start:result.end],
                start=result.start,
                end=result.end
            )
        )
        
    return entities

def redact_text(text: str, pii_entities: List[PIIEntity]) -> str:
    """
    Redacts PII entities from the given text replacing them with [REDACTED_<TYPE>].
    """
    if not text or not pii_entities:
        return text
    
    priority = {"AADHAAR": 10, "PAN": 10, "PHONE_IN": 10, "PIN_CODE": 10, "UPI_ID": 10, "IFSC_CODE": 10}
    
    # Sort entities in reverse order of their start index, then length, then priority
    sorted_entities = sorted(
        pii_entities, 
        key=lambda x: (x.start, x.end - x.start, priority.get(x.type, 0)), 
        reverse=True
    )
    
    redacted = text
    last_start = len(text) + 1
    
    for entity in sorted_entities:
        # Skip overlapping entities
        if entity.end > last_start:
            continue
            
        redacted = redacted[:entity.start] + f"[REDACTED_{entity.type}]" + redacted[entity.end:]
        last_start = entity.start
        
    return redacted

def redact_pii(text: str, pii_entities: List[PIIEntity]) -> str:
    """
    Legacy wrapper for compat with main.py
    """
    return redact_text(text, pii_entities)
