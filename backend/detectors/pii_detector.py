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


# ---------------------------------------------------------------------------
# Hinglish PERSON false positives
#
# The Presidio PERSON recogniser runs an English spaCy model. Romanised Hindi
# tokens are out of vocabulary and get tagged PROPN, so "Bhai mera phone number
# update karna hai" comes back with PERSON spans "Bhai mera" and "karna hai".
# Every Hinglish sentence we tried produced at least one spurious name.
#
# A full multilingual retrain is the real fix; this is the cheap, low-risk one:
# strip known Hinglish function words from the edges of each PERSON span and
# drop the span if nothing name-like survives. It can only ever remove or
# shrink a PERSON hit, never invent one, and it leaves the regex-based Indian
# identifier recognisers (Aadhaar/PAN/UPI/IFSC/phone/PIN) untouched.
# ---------------------------------------------------------------------------
HINGLISH_STOPWORDS = {
    # pronouns / possessives
    "main", "mai", "mera", "meri", "mere", "hum", "hamara", "hamari",
    "tu", "tum", "tera", "teri", "tere", "aap", "aapka", "aapki", "aapke",
    "tumhara", "tumhari", "tumhare", "apna", "apni", "apne", "khud",
    "yeh", "ye", "woh", "wo", "iska", "uska", "inka", "unka", "is", "us",
    # question words
    "kya", "kyu", "kyun", "kaise", "kaisa", "kaisi", "kaun", "kab", "kahan",
    "kitna", "kitne", "kitni", "konsa", "kaunsa",
    # verbs / auxiliaries
    "hai", "hain", "ho", "hoga", "hogi", "honge", "hota", "hoti", "hote",
    "tha", "thi", "the", "raha", "rahi", "rahe", "gaya", "gayi", "gaye",
    "kar", "karo", "karna", "karne", "karta", "karti", "karte", "kiya", "kare",
    "karunga", "karta hoon", "hoon", "hu", "hun",
    "sakta", "sakti", "sakte", "chahiye", "chahta", "chahti", "chahte",
    "batao", "bata", "bolo", "bol", "dekho", "dekh", "samjha", "samjho",
    "aaya", "aayega", "aayegi", "jaa", "ja", "jao", "jaana", "lena", "lo",
    "de", "do", "dena", "diya", "milega", "mila", "lagta", "lagega",
    "bhej", "bheja", "bhejo", "bhejna", "nikal", "nikalo", "nikalna",
    "daal", "daalo", "daalna", "dalna", "laga", "lagao", "lagana",
    # postpositions / conjunctions / particles
    "ka", "ki", "ke", "ko", "se", "me", "mein", "par", "pe", "tak", "liye",
    "lie", "aur", "ya", "nahi", "nahin", "na", "mat", "bhi", "to", "toh",
    "hi", "sirf", "bas", "bss", "agar", "lekin", "magar", "jab", "tab",
    "phir", "fir", "abhi", "ab", "baad", "pehle", "kuch", "koi", "sab",
    "saare", "sara", "sari", "jo", "jis", "wale", "wala", "wali",
    # interjections / fillers
    "bhai", "yaar", "arre", "are", "achha", "accha", "acha", "theek", "thik",
    "thoda", "thodi", "zyada", "jyada", "matlab", "waise", "chalo",
    # very common nouns that are not names
    "naam", "paisa", "paise", "kaam", "baat", "din", "log", "logo",
}

# Domain acronyms spaCy also mistakes for proper nouns.
NON_NAME_ACRONYMS = {
    "upi", "kyc", "pan", "ifsc", "otp", "gst", "cibil", "emi", "neft",
    "imps", "rtgs", "atm", "id", "sms", "api", "pin", "aadhaar", "aadhar",
}

_TOKEN_RE = re.compile(r"\S+")


def _is_droppable_token(token: str) -> bool:
    bare = token.strip(".,!?;:'\"()[]{}").lower()
    if not bare:
        return True
    if bare in HINGLISH_STOPWORDS:
        return True
    if bare in NON_NAME_ACRONYMS:
        return True
    return False


def _looks_code_mixed(text: str) -> bool:
    """Two or more distinct Hinglish markers means we treat the text as Hinglish."""
    seen = {m.group().strip(".,!?;:'\"()[]{}").lower() for m in _TOKEN_RE.finditer(text)}
    return len(seen & HINGLISH_STOPWORDS) >= 2


def _clean_person_span(text: str, start: int, end: int, code_mixed: bool):
    """
    Trim Hinglish filler from the edges of a PERSON span.

    Returns (new_start, new_end) or None when nothing name-like is left.
    """
    tokens = [(m.start() + start, m.end() + start) for m in _TOKEN_RE.finditer(text[start:end])]
    if not tokens:
        return None

    # A span made up entirely of filler is never a name -- drop it regardless
    # of whether the surrounding sentence looked code-mixed.
    if all(_is_droppable_token(text[s:e]) for s, e in tokens):
        return None

    if not code_mixed:
        return start, end

    lo, hi = 0, len(tokens) - 1
    while lo <= hi and _is_droppable_token(text[tokens[lo][0]:tokens[lo][1]]):
        lo += 1
    while hi >= lo and _is_droppable_token(text[tokens[hi][0]:tokens[hi][1]]):
        hi -= 1
    if lo > hi:
        return None
    return tokens[lo][0], tokens[hi][1]


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
    
    code_mixed = _looks_code_mixed(text)

    entities = []
    for result in results:
        # Standardize email type name if needed
        entity_type = result.entity_type
        if entity_type == "EMAIL_ADDRESS":
            entity_type = "EMAIL"

        start, end = result.start, result.end

        # Hinglish filler routinely comes back as a PERSON span; trim it, and
        # drop the hit entirely when no name-like token survives.
        if entity_type == "PERSON":
            cleaned = _clean_person_span(text, start, end, code_mixed)
            if cleaned is None:
                continue
            start, end = cleaned

        entities.append(
            PIIEntity(
                type=entity_type,
                value=text[start:end],
                start=start,
                end=end
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
