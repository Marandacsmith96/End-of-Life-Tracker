"""The HHHHHMM quality-of-life scale (Villalobos).

Seven categories, each scored 0 (worst) to 10 (best). A total above 35 is
generally read as an acceptable quality of life, but only a vet who knows
the animal can interpret it. This module holds the scale definition and pure
helper functions; nothing here touches the database.
"""

CATEGORIES = (
    ("hurt", "Hurt", "Pain is controlled and breathing is easy."),
    ("hunger", "Hunger", "Eating enough, with hand-feeding or coaxing if needed."),
    ("hydration", "Hydration", "Drinking enough; not dehydrated."),
    ("hygiene", "Hygiene", "Clean, brushed, no soiling or pressure sores."),
    ("happiness", "Happiness", "Shows interest, responds to family, seems content."),
    ("mobility", "Mobility", "Gets up and moves around without too much help."),
    ("good_days", "More good days than bad", "Overall, good days outnumber bad ones."),
)

CATEGORY_KEYS = tuple(key for key, _, _ in CATEGORIES)
CATEGORY_LABELS = {key: label for key, label, _ in CATEGORIES}
MIN_SCORE = 0
MAX_SCORE = 10
MAX_TOTAL = MAX_SCORE * len(CATEGORIES)  # 70
ACCEPTABLE_TOTAL = 35  # the scale's commonly cited threshold

APPETITE_OPTIONS = (
    ("none", "Not eating"),
    ("low", "Eating less than usual"),
    ("normal", "Eating normally"),
    ("high", "Eating more than usual"),
)
APPETITE_LABELS = dict(APPETITE_OPTIONS)
WEIGHT_UNITS = ("kg", "lb")


def total_score(scores: dict) -> int:
    """Sum the seven category scores."""
    return sum(int(scores[key]) for key in CATEGORY_KEYS)


def is_valid_score(value) -> bool:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return False
    return MIN_SCORE <= number <= MAX_SCORE


def describe_total(total: int) -> str:
    """Plain-language reading of a total, phrased for the owner, not as a verdict."""
    if total >= 50:
        return "Scores are in a comfortable range."
    if total > ACCEPTABLE_TOTAL:
        return "Scores are above the scale's usual threshold, but worth watching."
    return "Scores are at or below the scale's usual threshold. Consider talking with your vet."
