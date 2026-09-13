from typing import List
from models.schemas import PIIEntity
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern, EntityRecognizer, RecognizerResult
import re

# Initialize engines
analyzer = AnalyzerEngine()

# ---------------------------------------------------------------------------
# Verhoeff Checksum for Aadhaar Validation
# ---------------------------------------------------------------------------
# Dihedral group D5 multiplication table
_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

# Permutation table
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def validate_verhoeff(num_str: str) -> bool:
    """
    Validates a 12-digit number using the Verhoeff checksum algorithm as used in Aadhaar.
    """
    digits = re.sub(r"\D", "", num_str)
    if len(digits) != 12:
        return False
    c = 0
    for i, item in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(item)]]
    return c == 0


# Custom Pattern Recognizers for Indian Context
aadhaar_pattern = Pattern(
    name="aadhaar_pattern",
    regex=r"\b\d{4}\s?\d{4}\s?\d{4}\b",
    score=1.0
)


class AadhaarRecognizer(PatternRecognizer):
    """
    Recognizer for Indian Aadhaar numbers (12 digits, optional spaces between 4-digit groups)
    with Verhoeff checksum validation to filter out arbitrary 4-4-4 digit numbers.
    """
    def __init__(self):
        super().__init__(
            supported_entity="AADHAAR",
            patterns=[aadhaar_pattern],
            name="aadhaar_recognizer",
        )

    def validate_result(self, pattern_text: str) -> bool:
        return validate_verhoeff(pattern_text)


aadhaar_recognizer = AadhaarRecognizer()

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


class PinCodeRecognizer(EntityRecognizer):
    """
    Recognizer for Indian PIN codes (6-digit postal codes).
    Requires a keyword prefix (pin, pincode, postal code, zip code, delivery to)
    or suffix context to prevent false positives on order numbers, OTPs, amounts, etc.
    """
    def __init__(self):
        super().__init__(
            supported_entities=["PIN_CODE"],
            name="pin_code_recognizer",
        )
        self.patterns = [
            # Prefix context e.g. "pin code 110001", "delivery to 400001", "pincode: 110001"
            re.compile(
                r"(?i:\b(?:pin(?:\s*(?:code|no\.?|number))?|pincode|postal\s*code|zip(?:\s*code)?|delivery\s+to|deliver\s+to)\b[\s\-:#=]*(?:is\s+)?)([1-9]\d{5})\b"
            ),
            # Suffix context e.g. "110001 pin code", "400001 pincode"
            re.compile(
                r"\b([1-9]\d{5})\b[\s\-:#=]*(?i:\b(?:pincode|pin(?:\s*code)?|postal\s*code|zip(?:\s*code)?)\b)"
            ),
        ]

    def load(self):
        pass

    def analyze(self, text, entities, nlp_artifacts=None):
        results = []
        if "PIN_CODE" not in entities:
            return results
        seen_spans = set()
        for pat in self.patterns:
            for m in pat.finditer(text):
                start, end = m.span(1)
                if (start, end) not in seen_spans:
                    seen_spans.add((start, end))
                    results.append(
                        RecognizerResult(
                            entity_type="PIN_CODE",
                            start=start,
                            end=end,
                            score=1.0,
                        )
                    )
        return results


pin_recognizer = PinCodeRecognizer()

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
