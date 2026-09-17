from app import scoring


def test_total_and_mean():
    scores = {k: 5 for k in scoring.CATEGORY_KEYS}
    assert scoring.total_score(scores) == 35
    assert scoring.mean_score(scores) == 5.0
    assert scoring.mean_score({"hurt": 8, "hunger": None}) == 8.0
    assert scoring.mean_score({"hurt": None}) is None


def test_is_valid_score():
    assert scoring.is_valid_score("0") and scoring.is_valid_score(10)
    assert not scoring.is_valid_score("11") and not scoring.is_valid_score(None) and not scoring.is_valid_score("x")


def test_scale_is_cited_and_has_guidance():
    assert "Villalobos" in scoring.ATTRIBUTION
    assert len(scoring.CATEGORIES) == 7
    for key, label, guidance, low, high in scoring.CATEGORIES:
        assert guidance.endswith("?") and low and high
        assert "{name}" in scoring.QUESTIONS[key]
