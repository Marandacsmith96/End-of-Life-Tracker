"""Centralized content safety layer.

Every generated sentence that reaches the owner (insights, trend summaries,
vet-visit prep, PDF text) passes through ``guard`` so that nothing the app
produces can read as a verdict about the animal's life. The rules are simple
string patterns on purpose: they are easy to audit and easy to extend.
"""
import re

DISCLAIMER = (
    "This tool helps you record and discuss changes in your pet's quality of life. "
    "It does not provide veterinary diagnosis, medical advice, or a recommendation "
    "about euthanasia. Treatment and end-of-life decisions should be made with your "
    "veterinarian."
)
REPORT_NOTE = (
    "This report summarizes observations entered by the pet's caregiver and is intended "
    "to support discussion with a veterinarian."
)
# The strongest guidance the app is allowed to give.
MAX_GUIDANCE = "You may want to share these changes with your veterinarian."
EMERGENCY = (
    "If you're concerned about a sudden or severe change in your pet's condition, contact "
    "your veterinarian or an emergency veterinary clinic."
)

# Patterns that must never appear in generated text (case-insensitive).
FORBIDDEN = [
    r"\bit'?s time\b",
    r"\beuthan",                       # euthanasia, euthanize, euthanised...
    r"\bput (him|her|them|it|your pet|\w+) (down|to sleep)\b",
    r"\bput down\b",
    r"\bno longer has an acceptable quality\b",
    r"\bacceptable quality of life\b",
    r"\bneeds? to make a decision\b",
    r"\bmake a decision\b",
    r"\bis dying\b",
    r"\bis suffering\b",
    r"\bshould (schedule|consider ending|end)\b",
    r"\byou should\b",
    r"\bwe recommend\b",
    r"\brecommend(ed|s)?\b",
    r"\bdiagnos(is|ed|e)\b(?! or)",    # the disclaimer's "diagnosis or" is allowed
    r"\bterminal\b",
    r"\bgive up\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN]


class SafetyViolation(ValueError):
    """Raised when generated text matches a forbidden pattern."""


def violations(text: str) -> list[str]:
    """Return the forbidden patterns that ``text`` matches (empty when clean)."""
    return [p.pattern for p in _COMPILED if p.search(text)]


def is_safe(text: str) -> bool:
    return not violations(text)


def guard(text: str) -> str:
    """Return ``text`` unchanged, or raise if it breaks the rules.

    Raising (rather than silently dropping the sentence) is deliberate: a
    violation is a bug in the insight engine and should fail loudly in tests.
    """
    found = violations(text)
    if found:
        raise SafetyViolation(f"Generated text breaks safety rules {found}: {text!r}")
    return text
