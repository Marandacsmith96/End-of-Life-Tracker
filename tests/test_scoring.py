from app import scoring


def test_total_sums_seven_categories():
    scores = {k: 5 for k in scoring.CATEGORY_KEYS}
    assert scoring.total_score(scores) == 35
    scores["hurt"] = 10
    assert scoring.total_score(scores) == 40


def test_max_total_is_70():
    assert scoring.MAX_TOTAL == 70
    assert scoring.total_score({k: 10 for k in scoring.CATEGORY_KEYS}) == 70


def test_is_valid_score():
    assert scoring.is_valid_score("0")
    assert scoring.is_valid_score(10)
    assert not scoring.is_valid_score("11")
    assert not scoring.is_valid_score("-1")
    assert not scoring.is_valid_score("five")
    assert not scoring.is_valid_score(None)


def test_describe_total_never_gives_a_verdict():
    for total in (0, 35, 36, 50, 70):
        text = scoring.describe_total(total)
        assert "euthan" not in text.lower()
    assert "vet" in scoring.describe_total(30)
    assert "comfortable" in scoring.describe_total(60)
