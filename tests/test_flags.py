from datetime import date, timedelta

from app import flags
from app.entries import Entry

TODAY = date(2026, 9, 17)
KEYS = ("hurt", "hunger", "hydration", "hygiene", "happiness", "mobility", "good_days")


def _entry(days_ago, each=6, weight=None, unit=None, appetite=None, **scores):
    values = {k: each for k in KEYS}
    values.update(scores)
    return Entry(id=days_ago, animal_id=1, entry_date=TODAY - timedelta(days=days_ago),
                 weight=weight, weight_unit=unit, appetite=appetite, notes=None, **values)


def test_no_entries_no_flags():
    assert flags.evaluate([], today=TODAY) == []


def test_healthy_run_has_no_flags():
    entries = [_entry(i, each=7, weight=10, unit="kg", appetite="normal") for i in range(40)]
    assert flags.evaluate(entries, today=TODAY) == []


def test_low_total_needs_three_entries_in_a_row():
    two_low = [_entry(0, each=4), _entry(1, each=4), _entry(2, each=7)]
    assert flags.low_total(two_low) is None
    three_low = [_entry(0, each=5), _entry(1, each=4), _entry(2, each=5), _entry(3, each=8)]
    flag = flags.low_total(three_low)
    assert flag is not None
    assert flag.level == "watch"
    assert "35, 28, 35" in flag.detail
    assert "vet" in flag.detail


def test_low_total_uses_at_or_below_35():
    assert flags.low_total([_entry(i, each=5) for i in range(3)]) is not None  # 35
    assert flags.low_total([_entry(i, each=5, hurt=6) for i in range(3)]) is None  # 36


def test_low_category():
    entries = [_entry(i, mobility=2) for i in range(3)]
    found = flags.low_categories(entries)
    assert [f.key for f in found] == ["low_mobility"]
    assert "Mobility" in found[0].title
    entries[1].mobility = 4
    assert flags.low_categories(entries) == []


def test_weight_drop_compares_to_about_a_month_earlier():
    entries = [_entry(0, weight=9.0, unit="kg"), _entry(30, weight=10.0, unit="kg")]
    flag = flags.weight_drop(entries)
    assert flag is not None
    assert "10%" in flag.title
    assert "10 kg" in flag.detail and "9 kg" in flag.detail


def test_weight_drop_ignores_small_changes_and_missing_baseline():
    assert flags.weight_drop([_entry(0, weight=9.6, unit="kg"), _entry(30, weight=10.0, unit="kg")]) is None
    assert flags.weight_drop([_entry(0, weight=8.0, unit="kg"), _entry(5, weight=10.0, unit="kg")]) is None
    assert flags.weight_drop([_entry(0, weight=8.0, unit="kg")]) is None


def test_weight_drop_converts_units():
    # 22 lb is about 10 kg; 8.5 kg is a 15% drop.
    entries = [_entry(0, weight=8.5, unit="kg"), _entry(28, weight=22.0, unit="lb")]
    assert flags.weight_drop(entries) is not None


def test_no_appetite_two_entries():
    assert flags.no_appetite([_entry(0, appetite="none"), _entry(1, appetite="low")]) is None
    flag = flags.no_appetite([_entry(0, appetite="none"), _entry(1, appetite="none")])
    assert flag is not None and flag.key == "no_appetite"


def test_missed_entries_reminder():
    assert flags.missed_entries([_entry(2)], today=TODAY) is None
    flag = flags.missed_entries([_entry(3)], today=TODAY)
    assert flag is not None
    assert flag.level == "reminder"
    assert not flag.is_health
    assert "3 days" in flag.title


def test_evaluate_puts_health_flags_before_reminders():
    entries = [_entry(4, each=3), _entry(5, each=3), _entry(6, each=3)]
    found = flags.evaluate(entries, today=TODAY)
    keys = [f.key for f in found]
    assert keys[0] == "low_total"
    assert keys[-1] == "missed_entries"
    assert all("euthan" not in (f.title + f.detail).lower() for f in found)


# --- in the pages ------------------------------------------------------------

def _log(client, days_ago, each, **extra):
    day = (date.today() - timedelta(days=days_ago)).isoformat()
    data = {"entry_date": day, **{k: each for k in KEYS}, **extra}
    client.post("/animals/1/log", data=data)


def test_pet_page_and_dashboard_show_flags(client):
    client.post("/animals/new", data={"name": "Mochi", "species": "cat"})
    for i in range(3):
        _log(client, i, 4, appetite="none")
    page = client.get("/animals/1").data
    assert b"Total score at or below 35" in page
    assert b"Not eating on the last 2 entries" in page
    assert b"not a diagnosis" in page
    assert b"No entry for" not in page
    dashboard = client.get("/").data
    assert b"2 patterns to watch" in dashboard
    history = client.get("/animals/1/history").data
    assert b"Total score at or below 35" in history


def test_pet_page_without_flags_shows_nothing(client):
    client.post("/animals/new", data={"name": "Mochi", "species": "cat"})
    _log(client, 0, 8)
    page = client.get("/animals/1").data
    assert b"Things to watch" not in page
    assert b"badge watch" not in client.get("/").data
