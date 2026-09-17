"""The HHHHHMM Quality of Life Scale (Villalobos).

Seven domains, each scored 0 (worst) to 10 (best). This tracker incorporates the
scale as one framework for organizing owner observations; it is not itself a
validated clinical instrument. Nothing here touches the database.
"""

ATTRIBUTION = (
    "This tracker incorporates the HHHHHMM Quality of Life Scale developed by "
    "Dr. Alice Villalobos as one framework for organizing owner observations."
)

# key, label, one-line guidance, 0 anchor, 10 anchor
CATEGORIES = (
    ("hurt", "Hurt", "How comfortable did your pet seem today?",
     "severe or uncontrolled discomfort", "comfortable; pain appears well controlled"),
    ("hunger", "Hunger", "How well did your pet eat today?",
     "would not eat", "normal healthy appetite"),
    ("hydration", "Hydration", "How well hydrated did your pet seem?",
     "not drinking; signs of dehydration", "drinking normally"),
    ("hygiene", "Hygiene", "Could your pet stay clean, dry, and comfortable?",
     "soiled or unable to stay clean", "clean, dry, and comfortable"),
    ("happiness", "Happiness",
     "Did your pet show interest in family, surroundings, routines, or things they usually enjoy?",
     "withdrawn; no interest", "engaged and interested"),
    ("mobility", "Mobility", "How easily could your pet move around?",
     "unable to move without help", "moves around freely"),
    ("good_days", "More good days than bad",
     "Looking at the recent pattern, are good days still outweighing bad days?",
     "bad days clearly outnumber good", "good days clearly outnumber bad"),
)

# Asked one at a time in the daily check-in. {name} is the pet's name.
QUESTIONS = {
    "hurt": "How comfortable did {name} seem today?",
    "hunger": "How well did {name} eat today?",
    "hydration": "How well hydrated did {name} seem?",
    "hygiene": "Could {name} stay clean, dry, and comfortable?",
    "happiness": "Did {name} show interest in family, surroundings, or things they usually enjoy?",
    "mobility": "How easily could {name} move around?",
    "good_days": "Looking at the recent pattern, are {name}'s good days still outweighing bad days?",
}

CATEGORY_KEYS = tuple(c[0] for c in CATEGORIES)
CATEGORY_LABELS = {c[0]: c[1] for c in CATEGORIES}
CATEGORY_GUIDANCE = {c[0]: c[2] for c in CATEGORIES}
CATEGORY_ANCHORS = {c[0]: (c[3], c[4]) for c in CATEGORIES}
MIN_SCORE = 0
MAX_SCORE = 10
MAX_TOTAL = MAX_SCORE * len(CATEGORIES)  # 70
# The scale's published reference: totals above 35 are described as acceptable.
# Shown only as a reference marker, never as a verdict.
ACCEPTABLE_TOTAL = 35
ACCEPTABLE_MEAN = ACCEPTABLE_TOTAL / len(CATEGORIES)  # 5.0

APPETITE_OPTIONS = (
    ("none", "Not eating"),
    ("low", "Eating less than usual"),
    ("normal", "Eating normally"),
    ("high", "Eating more than usual"),
)
APPETITE_LABELS = dict(APPETITE_OPTIONS)
WEIGHT_UNITS = ("kg", "lb")


def total_score(scores: dict) -> int:
    """Sum the seven category scores (all must be present)."""
    return sum(int(scores[key]) for key in CATEGORY_KEYS)


def mean_score(scores: dict) -> float | None:
    """Mean of whichever categories were scored, or None if none were."""
    values = [int(v) for v in scores.values() if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def is_valid_score(value) -> bool:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return False
    return MIN_SCORE <= number <= MAX_SCORE
