"""
normalizer.py
~~~~~~~~~~~~~
High-throughput, DoS-bounded multi-modal text normalization layer.
Executed BEFORE all heuristics, embeddings, and classifiers.

Transforms handled:
  1. Unicode NFKC normalization, zero-width stripping, whitespace collapse.
  2. Cyrillic and Greek homoglyph mapping to Latin ASCII.
  3. Leetspeak decoding (1->i, 0->o, 3->e, 4->a, 5->s, 7->t, @->a, $->s)
     applied ONLY to tokens mixing alphanumeric characters so standard numbers survive.
  4. Spaced-letter collapse ("i g n o r e" -> "ignore") when 4+ consecutive
     single-character tokens appear.
  5. Base64 payload decoding (for valid base64 segments >= 16 chars decoding to printable UTF-8).
  6. ROT13 decoding candidate generation.
  7. Hinglish phonetic/spelling canonicalization via data/hinglish_canonical.json.
  8. DoS-bounds: MAX_INPUT_LENGTH (50k chars) and MAX_RECURSION_DEPTH (2).
"""

import os
import re
import json
import codecs
import base64
import unicodedata
from typing import List, Tuple, Dict, Any, Optional

MAX_INPUT_LENGTH = 50_000
MAX_RECURSION_DEPTH = 2

# -----------------------------------------------------------------------------
# 1. Zero-width and Invisible Unicode Characters
# -----------------------------------------------------------------------------
_ZERO_WIDTH_CHARS = (
    "\u200b", "\u200c", "\u200d", "\u200e", "\u200f",
    "\u00ad", "\u2060", "\ufeff", "\u202a", "\u202b",
    "\u202c", "\u202d", "\u202e", "\u2061", "\u2062",
    "\u2063", "\u2064",
)
_ZERO_WIDTH_RE = re.compile("[" + "".join(re.escape(c) for c in _ZERO_WIDTH_CHARS) + "]")

# -----------------------------------------------------------------------------
# 2. Cyrillic and Greek Homoglyph Map
# -----------------------------------------------------------------------------
HOMOGLYPH_MAP: Dict[str, str] = {
    # Cyrillic lowercase
    'а': 'a', 'в': 'b', 'е': 'e', 'ѕ': 's', 'і': 'i', 'ј': 'j', 'к': 'k',
    'о': 'o', 'р': 'p', 'с': 'c', 'т': 't', 'у': 'y', 'х': 'x', 'ԁ': 'd',
    'ԛ': 'q', 'п': 'n', 'г': 'r', 'м': 'm', 'н': 'h',
    # Cyrillic uppercase
    'А': 'A', 'В': 'B', 'Е': 'E', 'Ѕ': 'S', 'І': 'I', 'Ј': 'J', 'К': 'K',
    'О': 'O', 'Р': 'P', 'С': 'C', 'Т': 'T', 'У': 'Y', 'Х': 'X', 'М': 'M',
    'Н': 'H', 'Т': 'T',
    # Greek lowercase
    'α': 'a', 'β': 'b', 'γ': 'y', 'ε': 'e', 'ζ': 'z', 'η': 'n', 'ι': 'i',
    'κ': 'k', 'μ': 'u', 'ν': 'v', 'ο': 'o', 'ρ': 'p', 'τ': 't', 'υ': 'u',
    'χ': 'x',
    # Greek uppercase
    'Α': 'A', 'Β': 'B', 'Γ': 'r', 'Ε': 'E', 'Ζ': 'Z', 'Η': 'H', 'Ι': 'I',
    'Κ': 'K', 'Μ': 'M', 'Ν': 'N', 'Ο': 'O', 'Ρ': 'P', 'Τ': 'T', 'Υ': 'Y',
    'Χ': 'X',
}
_HOMOGLYPH_TRANS = str.maketrans(HOMOGLYPH_MAP)

# -----------------------------------------------------------------------------
# 3. Leetspeak Translation
# -----------------------------------------------------------------------------
LEET_MAP: Dict[str, str] = {
    '1': 'i',
    '0': 'o',
    '3': 'e',
    '4': 'a',
    '5': 's',
    '7': 't',
    '@': 'a',
    '$': 's',
}
_LEET_TRANS = str.maketrans(LEET_MAP)
_DIGIT_OR_LEET_CHARS = set(LEET_MAP.keys())

# -----------------------------------------------------------------------------
# 4. Hinglish Spelling Dictionary
# -----------------------------------------------------------------------------
_HINGLISH_CANONICAL: Dict[str, str] = {}
_DICT_PATH = os.path.join(os.path.dirname(__file__), 'data', 'hinglish_canonical.json')
if os.path.exists(_DICT_PATH):
    try:
        with open(_DICT_PATH, 'r', encoding='utf-8') as f:
            _HINGLISH_CANONICAL = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load hinglish_canonical.json: {e}")


_COMMON_VOCAB = {
    "the", "and", "you", "that", "was", "for", "are", "with", "his", "they",
    "this", "have", "from", "one", "had", "word", "but", "not", "what", "all",
    "were", "when", "your", "can", "said", "there", "use", "each", "which", "she",
    "do", "how", "their", "if", "will", "up", "other", "about", "out", "many",
    "then", "them", "these", "so", "some", "her", "would", "make", "like", "him",
    "into", "time", "has", "look", "two", "more", "write", "go", "see", "number",
    "no", "way", "could", "people", "my", "than", "first", "water", "been", "call",
    "who", "oil", "its", "now", "find", "long", "down", "day", "did", "get",
    "come", "made", "may", "part", "ignore", "rules", "system", "prompt", "bypass",
    "override", "forget", "password", "secret", "reveal", "instructions", "admin",
    "mode", "developer", "policy", "safety", "unrestricted", "jailbreak"
}

def strip_zero_width(text: str) -> str:
    """Removes all zero-width and invisible control characters."""
    return _ZERO_WIDTH_RE.sub("", text)


def normalize_unicode_and_homoglyphs(text: str) -> str:
    """
    Applies NFKC normalization, removes zero-width characters, maps Cyrillic/Greek
    homoglyphs to Latin, and collapses duplicate whitespace.
    """
    if len(text) > MAX_INPUT_LENGTH:
        text = text[:MAX_INPUT_LENGTH]

    # 1. NFKC
    norm = unicodedata.normalize('NFKC', text)

    # 2. Zero-width
    norm = strip_zero_width(norm)

    # 3. Homoglyph mapping
    norm = norm.translate(_HOMOGLYPH_TRANS)

    # 4. Whitespace collapse
    norm = re.sub(r'[ \t\r\f\v]+', ' ', norm)
    norm = re.sub(r'\n{3,}', '\n\n', norm).strip()

    return norm


def decode_leetspeak(text: str) -> str:
    """
    Translates leetspeak characters (1->i, 0->o, 3->e, 4->a, 5->s, 7->t, @->a, $->s)
    ONLY in tokens that mix letters and leet digits/symbols.
    Pure numeric tokens (e.g. '100', '2024') are preserved.
    """
    tokens = re.split(r'(\s+)', text)
    result = []

    for tok in tokens:
        if not tok or tok.isspace():
            result.append(tok)
            continue

        has_letter = any(c.isalpha() for c in tok)
        has_leet = any(c in _DIGIT_OR_LEET_CHARS for c in tok)

        # Only decode if the token mixes alphabetic characters with leet digits/symbols
        if has_letter and has_leet:
            result.append(tok.translate(_LEET_TRANS))
        else:
            result.append(tok)

    return "".join(result)


def collapse_spaced_letters(text: str) -> str:
    """
    Collapses sequences of 4 or more consecutive single-character tokens.
    Respects multiple spaces or newlines as word boundaries between spaced words.
    Example: 'i g n o r e   t h e   r u l e s' -> 'ignore the rules'.
    """
    tokens = re.split(r'(\s+)', text)
    out_tokens = []
    i = 0
    n = len(tokens)

    while i < n:
        tok = tokens[i]
        if len(tok) == 1 and tok.isalpha():
            chain = [tok]
            j = i + 1
            while j + 1 < n:
                sep = tokens[j]
                nxt = tokens[j + 1]
                # If separator contains 2 or more spaces or newline, it's a word boundary
                if len(sep) >= 2 or '\n' in sep:
                    break
                if len(nxt) == 1 and nxt.isalpha():
                    chain.append(nxt)
                    j += 2
                else:
                    break

            if len(chain) >= 4:
                out_tokens.append("".join(chain))
                i = j
                continue

        out_tokens.append(tok)
        i += 1

    return "".join(out_tokens)


def decode_base64_candidates(text: str) -> Optional[str]:
    """
    Searches for valid base64 substrings of length >= 16.
    If a segment decodes to mostly printable UTF-8 (>= 85% printable),
    replaces it with the decoded plaintext.
    Returns the decoded text, or None if no valid base64 payload was found.
    """
    # Match candidate base64 strings: length >= 16, consisting of valid base64 chars
    b64_pattern = re.compile(r'(?:[A-Za-z0-9+/]{4}){4,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?')
    found_any = False
    
    def replace_b64(match):
        nonlocal found_any
        s = match.group(0).strip()
        if len(s) < 16:
            return s
        try:
            raw = base64.b64decode(s, validate=True)
            decoded = raw.decode('utf-8', errors='replace')
            # Check printable percentage
            printable_count = sum(1 for c in decoded if c.isprintable() or c in '\n\r\t ')
            if len(decoded) > 0 and (printable_count / len(decoded)) >= 0.85 and any(c.isalpha() for c in decoded):
                found_any = True
                return " " + decoded + " "
        except Exception:
            pass
        return s

    replaced = b64_pattern.sub(replace_b64, text)
    if found_any:
        # Collapse whitespace after replacement
        return re.sub(r'\s+', ' ', replaced).strip()
    return None


def decode_rot13(text: str) -> str:
    """Applies ROT-13 decryption to the text."""
    try:
        return codecs.decode(text, 'rot_13')
    except Exception:
        return text


def canonicalize_hinglish(text: str) -> str:
    """
    Normalizes common Hinglish spelling variants using the canonical lookup dictionary.
    Preserves case capitalization pattern where applicable.
    """
    if not _HINGLISH_CANONICAL:
        return text

    def replace_word(m):
        w = m.group(0)
        w_lower = w.lower()
        if w_lower in _HINGLISH_CANONICAL:
            canon = _HINGLISH_CANONICAL[w_lower]
            if w.isupper():
                return canon.upper()
            elif w[0].isupper():
                return canon.capitalize()
            return canon
        return w

    return re.sub(r'\b[A-Za-z]+\b', replace_word, text)


class Normalizer:
    """
    Orchestrates the generation of normalized candidates for a prompt.
    Returns the original alongside all transformed candidates for parallel scoring.
    """

    @classmethod
    def generate_variants(cls, raw_text: str, depth: int = 1) -> List[Dict[str, Any]]:
        """
        Generates distinct candidates from raw text.
        Bounded by MAX_INPUT_LENGTH and MAX_RECURSION_DEPTH.
        """
        if len(raw_text) > MAX_INPUT_LENGTH:
            raw_text = raw_text[:MAX_INPUT_LENGTH]

        raw_unicode = unicodedata.normalize('NFKC', raw_text)
        raw_unicode = strip_zero_width(raw_unicode)
        raw_unicode = raw_unicode.translate(_HOMOGLYPH_TRANS)

        base_clean = re.sub(r'[ \t\r\f\v]+', ' ', raw_unicode)
        base_clean = re.sub(r'\n{3,}', '\n\n', base_clean).strip()

        candidates: List[Dict[str, Any]] = [
            {"text": base_clean, "transformation": "none", "description": "Normalized base text"}
        ]

        seen_texts = {base_clean}

        # 1. Spaced-letter collapse
        spaced_raw = collapse_spaced_letters(raw_unicode)
        spaced = re.sub(r'[ \t\r\f\v]+', ' ', spaced_raw).strip()
        if spaced and spaced not in seen_texts:
            seen_texts.add(spaced)
            candidates.append({
                "text": spaced,
                "transformation": "spaced_collapse",
                "description": "Collapsed spaced letters"
            })

        # 2. Leetspeak decode
        leet = decode_leetspeak(base_clean)
        if leet not in seen_texts:
            seen_texts.add(leet)
            candidates.append({
                "text": leet,
                "transformation": "leetspeak_decode",
                "description": "Decoded alphanumeric leetspeak"
            })

        # 3. Base64 decode
        b64 = decode_base64_candidates(base_clean)
        if b64 and b64 not in seen_texts:
            seen_texts.add(b64)
            candidates.append({
                "text": b64,
                "transformation": "base64_decode",
                "description": "Decoded Base64 payload"
            })

        # 4. Hinglish canonicalization
        hinglish = canonicalize_hinglish(base_clean)
        if hinglish not in seen_texts:
            seen_texts.add(hinglish)
            candidates.append({
                "text": hinglish,
                "transformation": "hinglish_canonical",
                "description": "Canonicalized Hinglish spelling variants"
            })

        # 5. Composite normalization: Spaced + Leet + Hinglish
        composite_raw = canonicalize_hinglish(decode_leetspeak(collapse_spaced_letters(raw_unicode)))
        composite = re.sub(r'[ \t\r\f\v]+', ' ', composite_raw).strip()
        if composite and composite not in seen_texts:
            seen_texts.add(composite)
            candidates.append({
                "text": composite,
                "transformation": "composite_normalization",
                "description": "Combined spaced collapse, leetspeak, and Hinglish canonicalization"
            })

        # 6. ROT13 candidate
        rot13 = decode_rot13(base_clean)
        if rot13 not in seen_texts and any(c.isalpha() for c in base_clean):
            # Only consider ROT13 if the decoded text forms recognizable vocabulary
            # that was absent in the ciphertext input. This prevents turning normal
            # plain-text prompts into gibberish that fools the linear classifier.
            orig_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', base_clean.lower()))
            rot13_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', rot13.lower()))
            new_vocab = (rot13_words & _COMMON_VOCAB) - orig_words
            if len(new_vocab) >= 2:
                seen_texts.add(rot13)
                candidates.append({
                    "text": rot13,
                    "transformation": "rot13_decode",
                    "description": "Decoded ROT-13 cipher"
                })

        return candidates
