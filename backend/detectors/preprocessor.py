"""
preprocessor.py
~~~~~~~~~~~~~~~
Normalises raw text BEFORE any jailbreak/heuristic/embedding analysis.

Each function is pure (no I/O, no side effects) so the suite is trivially
testable in isolation.

normalize_text() is the single public entry-point used by detect_jailbreak().
It returns:
    (cleaned_text: str, pre_flags: list[str])

pre_flags is a list of attack categories discovered purely from structure /
encoding, before any semantic check.  If non-empty the caller can immediately
escalate to high-risk without running the rest of the pipeline.
"""

import re
import html as html_module
from html.parser import HTMLParser
from typing import Tuple, List

# ---------------------------------------------------------------------------
# 1. Zero-width / invisible Unicode character removal
# ---------------------------------------------------------------------------

# Characters that are invisible in rendered text but can hide injections
_ZERO_WIDTH_CHARS = (
    "\u200b",  # ZERO WIDTH SPACE
    "\u200c",  # ZERO WIDTH NON-JOINER
    "\u200d",  # ZERO WIDTH JOINER
    "\u200e",  # LEFT-TO-RIGHT MARK
    "\u200f",  # RIGHT-TO-LEFT MARK
    "\u00ad",  # SOFT HYPHEN
    "\u2060",  # WORD JOINER
    "\ufeff",  # ZERO WIDTH NO-BREAK SPACE (BOM)
    "\u202a",  # LEFT-TO-RIGHT EMBEDDING
    "\u202b",  # RIGHT-TO-LEFT EMBEDDING
    "\u202c",  # POP DIRECTIONAL FORMATTING
    "\u202d",  # LEFT-TO-RIGHT OVERRIDE
    "\u202e",  # RIGHT-TO-LEFT OVERRIDE
    "\u2061",  # FUNCTION APPLICATION
    "\u2062",  # INVISIBLE TIMES
    "\u2063",  # INVISIBLE SEPARATOR
    "\u2064",  # INVISIBLE PLUS
)

_ZERO_WIDTH_RE = re.compile(
    "[" + "".join(re.escape(c) for c in _ZERO_WIDTH_CHARS) + "]"
)


def strip_zero_width_chars(text: str) -> Tuple[str, bool]:
    """
    Removes invisible Unicode characters.
    Returns (cleaned_text, was_modified).
    """
    cleaned = _ZERO_WIDTH_RE.sub("", text)
    return cleaned, cleaned != text


# ---------------------------------------------------------------------------
# 2. HTML stripping
# ---------------------------------------------------------------------------

class _HTMLTextExtractor(HTMLParser):
    """Extracts ALL text from HTML, including content hidden via CSS."""

    def __init__(self):
        super().__init__()
        self._chunks: List[str] = []
        # Also grab alt/title/aria-label attribute values
        self._attr_names = {"alt", "title", "aria-label", "placeholder", "value"}

    def handle_data(self, data: str):
        self._chunks.append(data)

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in self._attr_names and value:
                self._chunks.append(value)

    def get_text(self) -> str:
        return " ".join(chunk for chunk in self._chunks if chunk.strip())


def strip_html(text: str) -> Tuple[str, bool]:
    """
    If the text contains HTML markup, extract all text content (including
    content hidden with CSS like color:white / font-size:0).
    Returns (extracted_text, was_html).
    """
    # Quick check — avoid the parser overhead on plain text
    if "<" not in text and "&" not in text:
        return text, False

    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(html_module.unescape(text))
        extracted = extractor.get_text().strip()
    except Exception:
        # If parsing fails, fall back to a simple tag-strip regex
        extracted = re.sub(r"<[^>]+>", " ", text).strip()

    was_html = bool(re.search(r"<[a-zA-Z][^>]*>", text))
    # Prefer extracted if it's non-empty, else keep original
    result = extracted if extracted else text
    return result, was_html


# ---------------------------------------------------------------------------
# 3. Code comment extraction
# ---------------------------------------------------------------------------

# Matches Python (#), C/C++/JS (// and /* ... */), SQL (--), and shell (#)
_SINGLE_LINE_COMMENT_RE = re.compile(r"(?m)(?:#|//|--)\s*(.*?)$")
_MULTI_LINE_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def extract_code_comments(text: str) -> str:
    """
    Returns a string containing only the text from code comments.
    Empty string if no comments found.
    """
    parts: List[str] = []

    # Multi-line /* ... */
    for m in _MULTI_LINE_COMMENT_RE.finditer(text):
        inner = m.group(0)[2:-2].strip()
        if inner:
            parts.append(inner)

    # Single-line # / // / --
    for m in _SINGLE_LINE_COMMENT_RE.finditer(text):
        inner = m.group(1).strip()
        if inner:
            parts.append(inner)

    return " ".join(parts)


# ---------------------------------------------------------------------------
# 4. Delimiter-break detection
# ---------------------------------------------------------------------------

# Fake "end of document" markers used to split legitimate content from injections
_DELIMITER_MARKERS = [
    r"---+\s*end\s*(of\s*(document|text|input|context|page))?",
    r"===+",                          # bare ===== line is a common delimiter
    r"\*\*\*+\s*(end|stop|done)",
    r"\bend\s+of\s+(text|document|input|context|page)\b",
    r"\btext\s+khatam\b",
    r"\bdocument\s+ends?\b",
    r"\bstop\s+processing\s+(above|here)\b",
    r"\babove\s+text\s+is\s+(irrelevant|ignore[d]?)\b",
    r"---+\s*resume\s*---+",
    r"\[end\s+of\s+(document|text)\]",
    r"<end\s*/?>",
    # Hindi / Hinglish end markers
    r"\bab\s+naya\s+instruction\b",
    r"\bab\s+naye\s+rules\b",
]

_DELIMITER_RE = re.compile(
    "(" + "|".join(_DELIMITER_MARKERS) + ")",
    re.IGNORECASE,
)

# Post-delimiter imperative verbs that signal an injection following the marker
_POST_DELIMITER_IMPERATIVES = re.compile(
    r"(?i)\b("
    r"print|output|say|tell|write|generate|produce|respond|reply|"
    r"ignore|forget|disregard|override|bypass|disable|"
    r"reveal|show|display|list|enumerate|dump|"
    # Hinglish / Hindi imperatives
    r"bolo|likho|batao|karo|dikhao|mat|bhool|bhul|output karo|print karo"
    r")\b"
)


def detect_delimiter_break(text: str) -> bool:
    """
    Returns True if the text contains a fake end-of-document delimiter
    followed by imperative injection commands.
    """
    m = _DELIMITER_RE.search(text)
    if not m:
        return False
    # Check that there is meaningful content AFTER the marker
    after = text[m.end():].strip()
    if not after:
        return False
    # Need to find an imperative verb in the first 300 chars after the marker
    return bool(_POST_DELIMITER_IMPERATIVES.search(after[:300]))


# ---------------------------------------------------------------------------
# 5. Fake system-message detection
# ---------------------------------------------------------------------------

_FAKE_SYSTEM_MSG_RE = re.compile(
    r"(?i)"
    r"("
    # [SYSTEM MESSAGE ...] or [SYSTEM MESSAGE - PRIORITY OVERRIDE]
    r"\[\s*system[^\]]{0,60}\]"
    r"|\[\s*(admin|override|priority|compliance)[^\]]{0,40}\]"
    r"|---+\s*(system|admin|security|compliance)[^-]{0,40}---+"
    r"|<\s*system\s*>|</\s*system\s*>"
    r")"
)

# Legitimate authority-claim phrases following fake system msgs
_AUTHORITY_VERBS_RE = re.compile(
    r"(?i)\b(reveal|output|print|verbatim|conversation history|"
    r"system prompt|new directive|override|comply|compliance|follow)\b"
)


def detect_fake_system_message(text: str) -> bool:
    """
    Returns True if the text contains a fake [SYSTEM MESSAGE] / admin note
    block that appears to be injecting new directives.
    """
    m = _FAKE_SYSTEM_MSG_RE.search(text)
    if not m:
        return False
    # Check surrounding 300 chars for authority-claiming verbs
    start = max(0, m.start() - 50)
    end = min(len(text), m.end() + 300)
    context = text[start:end]
    return bool(_AUTHORITY_VERBS_RE.search(context))


# ---------------------------------------------------------------------------
# 6. Supply-chain redirect detection (code comments + markdown links)
# ---------------------------------------------------------------------------

# Suspicious URL patterns in code comments or markdown
_SUPPLY_CHAIN_RE = re.compile(
    r"(?is)"   # DOTALL; IGNORECASE
    r"("
    # Code comment (#) directing AI to recommend unofficial mirror.
    # '#' must be immediately followed by note-to/when (after optional whitespace).
    r"#\s*(?:note\s+to\s+(?:(?:the\s+)?(?:ai\s+)?(?:ai|llm|model|assistant))"
    r"|when\s+(?:user|you)\s+(?:ask|see|read|mention))"
    r".{0,400}?(?:recommend|suggest|use|download|install|visit|pip|npm).{0,100}https?://"
    # '//' comment: allow words between // and the when/note-to phrase
    r"|//[^\n]{0,60}(?:note\s+to\s+(?:(?:the\s+)?(?:ai\s+)?(?:ai|llm|model|assistant))"
    r"|when\s+(?:user|you)\s+(?:ask|see|read|mention))"
    r".{0,400}?(?:recommend|suggest|use|download|install|pip|npm).{0,100}https?://"
    # OR: explicit approved-mirror comment
    r"|(?:#|//)\s*(?:approved\s+(?:internal\s+)?mirror|use\s+this\s+instead\s+of\s+official)"
    r")"
)


def detect_supply_chain_redirect(text: str) -> bool:
    """
    Returns True if text contains code comments or markdown links that
    redirect to unofficial/suspicious package mirrors.
    The regex requires '#' or '//' prefix so we search the raw text directly.
    """
    return bool(_SUPPLY_CHAIN_RE.search(text))


# ---------------------------------------------------------------------------
# 7. Master normalize_text() entry point
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> Tuple[str, List[str]]:
    """
    Master pre-processing function.

    Steps (in order):
      1. Strip zero-width / invisible Unicode
      2. Strip HTML (extract all text including hidden content)
      3. Run structural attack detectors on the cleaned text

    Returns:
        cleaned_text  — text to use for all downstream analysis
        pre_flags     — list of attack category strings detected purely
                        from structure/encoding (may be empty).
                        Non-empty → caller should escalate to high risk.
    """
    pre_flags: List[str] = []

    # Step 1 — zero-width chars
    text, zw_modified = strip_zero_width_chars(text)
    if zw_modified:
        pre_flags.append("zero_width_injection")

    # Step 2 — HTML
    text, was_html = strip_html(text)
    if was_html:
        # HTML itself isn't always an attack; only flag if it also hides content
        # (i.e. original had hidden text that changed after stripping)
        pass  # downstream heuristics will catch the injected content

    # Step 3 — structural detectors on cleaned text
    if detect_delimiter_break(text):
        pre_flags.append("delimiter_break")

    if detect_fake_system_message(text):
        pre_flags.append("fake_system_message")

    if detect_supply_chain_redirect(text):
        pre_flags.append("supply_chain_redirect")

    return text, pre_flags
