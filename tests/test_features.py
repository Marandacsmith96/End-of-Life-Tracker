"""Markers setup, baseline, events, caregiver, calendar, vet prep, and dashboard copy."""
from datetime import date, timedelta

from app import baseline, caregiver, entries, events, markers, safety


def _generated(html: str) -> str:
    """Page text without the fixed disclaimer, which must mention euthanasia to rule it out."""
    return html.replace(safety.DISCLAIMER, "").replace(safety.DISCLAIMER.replace("'", "&#39;"), "")

TODAY = date.today()
KEYS = ("hurt", "hunger", "hydration", "hygiene", "happiness", "mobility", "good_days")


def _pet(client):
    client.post("/animals/new", data={"name": "Maggie", "species": "dog"})


def _log(client, days_ago, status="good", each=None, **extra):
    data = {"entry_date": (TODAY - timedelta(days=days_ago)).isoformat(), "day_status": status, **extra}
    if each is not None:
        data.update(scores_included="1", **{k: each for k in KEYS})
    client.post("/animals/1/checkin", data=data)


def test_marker_setup_limits(client, app):
    _pet(client)
    assert client.post("/animals/1/markers", data={"labels": ["One", "Two"]}).status_code == 400
    assert client.post("/animals/1/markers", data={"labels": list("ABCDEF")}).status_code == 400
    response = client.post("/animals/1/markers?onboarding=1", data={"labels": ["Greets me", "greets me", "Dinner", "Walk", ""]},
                           follow_redirects=True)
    assert b"A reference point from before" in response.data  # onboarding continues to baseline
    with app.app_context():
        assert [m.label for m in markers.list_markers(1)] == ["Greets me", "Dinner", "Walk"]
    # Removing one keeps its history (deactivated, not deleted).
    client.post("/animals/1/markers", data={"labels": ["Greets me", "Dinner", "Naps in the sun"]})
    with app.app_context():
        assert [m.label for m in markers.list_markers(1)] == ["Greets me", "Dinner", "Naps in the sun"]
        assert [m.label for m in markers.list_markers(1, active_only=False) if not m.active] == ["Walk"]


def test_baseline_save_skip_and_display(client, app):
    _pet(client)
    response = client.post("/animals/1/baseline?onboarding=1", data={"skip": "1"}, follow_redirects=True)
    assert b"You're ready." in response.data
    client.post("/animals/1/baseline", data={"approximate_date": "2026-03-01", "hurt": 8, "hunger": "", "hydration": 9,
                                              "hygiene": 9, "happiness": 9, "mobility": 8, "good_days": 9,
                                              "good_day_pattern": "mostly_good", "marker_frequency": "most_days"})
    with app.app_context():
        b = baseline.get_baseline(1)
        assert b.hunger is None and b.mobility == 8 and b.good_day_pattern == "mostly_good"
        assert b.label == "Owner-estimated baseline — approximately March 2026"
    _log(client, 0, each=6)
    page = client.get("/animals/1/today").data.decode()
    assert "Owner-estimated baseline" in page
    assert client.post("/animals/1/baseline", data={"hurt": "12"}).status_code == 400


def test_events_crud_and_chart_markers(client, app):
    _pet(client)
    assert client.post("/animals/1/events/new", data={"event_date": "2999-01-01", "type": "vet_visit"}).status_code == 400
    client.post("/animals/1/events/new", data={"event_date": (TODAY - timedelta(days=3)).isoformat(),
                                               "type": "pain_medication_started", "title": "Started gabapentin"})
    client.post("/animals/1/events/new", data={"event_date": (TODAY - timedelta(days=10)).isoformat(), "type": "vet_visit", "title": ""})
    with app.app_context():
        evs = events.list_events(1)
        assert [e.title for e in evs] == ["Started gabapentin", "Veterinary appointment"]
        assert events.last_vet_visit(1).event_date == TODAY - timedelta(days=10)
    _log(client, 0, each=6)
    page = client.get("/animals/1/trends?range=30").data.decode()
    assert "Started gabapentin" in page
    client.post(f"/events/{evs[0].id}/edit", data={"event_date": evs[0].event_date.isoformat(), "type": "other", "title": "Renamed"})
    client.post(f"/events/{evs[1].id}/delete")
    with app.app_context():
        assert [e.title for e in events.list_events(1)] == ["Renamed"]


def test_caregiver_checkin_is_separate(client, app):
    _pet(client)
    _log(client, 0, each=5)
    page = client.get("/animals/1/today").data
    assert b"How are you doing?" in page  # due: nothing recorded yet
    response = client.post("/animals/1/caregiver", data={"status": "exhausted", "note": "Up all night"}, follow_redirects=True)
    assert b"kept separate" in response.data.lower() or b"separately" in response.data
    with app.app_context():
        c = caregiver.latest(1)
        assert c.status == "exhausted" and not caregiver.is_due(1)
        # The animal's scores are untouched.
        e = entries.get_entry_for_date(1, TODAY)
        assert e.mean == 5.0
    page = client.get("/animals/1/today").data
    assert b'class="card block caregiver-card"' not in page
    assert client.post("/animals/1/caregiver", data={"status": "nope"}).status_code == 400


def test_calendar_page(client):
    _pet(client)
    _log(client, 0, "good"); _log(client, 1, "bad"); _log(client, 2, "mixed")
    page = client.get("/animals/1/calendar").data.decode()
    assert "Good and bad days" in page
    assert 'class="glyph good"' in page and 'class="glyph bad"' in page and 'class="glyph mixed"' in page
    assert "Last 30 days" in page
    prev = (TODAY.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    assert client.get(f"/animals/1/calendar?month={prev}").status_code == 200
    assert client.get("/animals/1/calendar?month=garbage").status_code == 200


def test_dashboard_counts_and_copy(client):
    _pet(client)
    for d in range(6):
        _log(client, d, "good" if d % 3 else "bad", each=6)
    page = client.get("/animals/1/today").data.decode()
    assert "Maggie's quality of life" in page
    assert "good days" in page and "not logged" in page
    assert "Limited data" in page or "enough information" in page
    assert "does not provide veterinary diagnosis" in page
    for banned in ("streak", "badge", "Oops", "missed", "It's time", "euthan"):
        assert banned not in _generated(page), banned


def test_dashboard_prompts_only_when_today_missing(client):
    _pet(client)
    page = client.get("/animals/1/today").data
    assert b"No check-in recorded today" in page and b"Quick check-in" in page
    _log(client, 0, "good")
    page = client.get("/animals/1/today").data
    assert b"No check-in recorded today" not in page and b"Edit today" in page


def test_vet_prep_page(client):
    _pet(client)
    client.post("/animals/1/markers", data={"labels": ["Greets me", "Dinner", "Walk"]})
    for d in range(30, 60):
        _log(client, d, "good", each=8, markers_included="1", markers=["1", "2", "3"])
    for d in range(0, 30):
        _log(client, d, "bad" if d % 2 else "mixed", each=5, mobility=3, markers_included="1", markers=["2"])
    page = client.get("/animals/1/vet").data.decode()
    assert "Prepare for my vet visit" in page
    assert "Things you may want to discuss with your veterinarian" in page
    assert "Mobility" in page and "Lower by" in page
    assert safety.MAX_GUIDANCE not in page or "veterinarian" in page
    for banned in ("euthan", "It's time", "recommend"):
        assert banned not in _generated(page), banned
    since = (TODAY - timedelta(days=10)).isoformat()
    assert client.get(f"/animals/1/vet?since={since}").status_code == 200


def test_shortcuts_resolve_current_pet(client):
    _pet(client)
    for path in ("/today", "/trends", "/calendar", "/vet"):
        r = client.get(path)
        assert r.status_code == 302 and "/animals/1/" in r.headers["Location"]
    assert client.get("/more").status_code == 200


def test_old_history_url_redirects(client):
    _pet(client)
    r = client.get("/animals/1/history")
    assert r.status_code == 302 and r.headers["Location"].endswith("/animals/1/trends")
