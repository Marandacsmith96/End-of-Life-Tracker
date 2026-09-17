import pytest

from app import safety


@pytest.mark.parametrize("text", [
    "It's time.",
    "You should euthanize your pet.",
    "Your pet should be put down.",
    "Your pet no longer has an acceptable quality of life.",
    "Euthanasia is recommended.",
    "Your score means you need to make a decision.",
    "Your pet is dying.",
    "Your pet is suffering.",
    "We recommend scheduling an appointment.",
])
def test_forbidden_statements_are_caught(text):
    assert not safety.is_safe(text)
    with pytest.raises(safety.SafetyViolation):
        safety.guard(text)


@pytest.mark.parametrize("text", [
    "Recent scores have been relatively stable.",
    "Scores have generally trended lower over the past three weeks.",
    "Mobility has been lower than Maggie's earlier baseline recently.",
    "There is not enough information yet to identify a clear pattern.",
    safety.MAX_GUIDANCE,
    safety.EMERGENCY,
    safety.REPORT_NOTE,
])
def test_allowed_statements_pass(text):
    assert safety.guard(text) == text


def test_disclaimer_is_static_copy_not_generated_text():
    # The disclaimer must name euthanasia to say the app never recommends it.
    # It is fixed copy, never produced by the insight engine, so it is not guarded.
    assert "does not provide" in safety.DISCLAIMER


def test_guard_is_case_insensitive():
    assert not safety.is_safe("IT'S TIME")
