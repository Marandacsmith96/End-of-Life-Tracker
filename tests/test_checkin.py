import io
from datetime import date, timedelta

from PIL import Image

from app import entries, markers

TODAY = date.today()
KEYS = ("hurt", "hunger", "hydration", "hygiene", "happiness", "mobility", "good_days")


def _pet(client, with_markers=True):
    client.post("/animals/new", data={"name": "Maggie", "species": "dog"})
    if with_markers:
        client.post("/animals/1/markers", data={"labels": ["Greets me", "Finishes dinner", "Wants a walk"]})


def _full(**overrides):
    data = {"entry_date": TODAY.isoformat(), "day_status": "mixed", "scores_included": "1",
            **{k: 6 for k in KEYS}, "markers_included": "1", "meds_included": "1", "notes": "Slept a lot."}
    data.update(overrides)
    return data


def test_quick_checkin_saves_status_and_markers(client, app):
    _pet(client)
    response = client.post("/animals/1/checkin/quick",
                           data={"entry_date": TODAY.isoformat(), "day_status": "good", "markers_included": "1",
                                 "markers": ["1", "3"]})
    assert response.status_code == 200
    assert b"Done" in response.data and b"Add full quality-of-life scores" in response.data
    with app.app_context():
        e = entries.get_entry_for_date(1, TODAY)
        assert e.day_status == "good" and e.mean is None and not e.has_scores
        assert markers.responses_for_entry(e.id) == {1: True, 2: False, 3: True}


def test_quick_checkin_requires_a_day_status(client):
    _pet(client)
    assert client.post("/animals/1/checkin/quick", data={"entry_date": TODAY.isoformat()}).status_code == 400


def test_full_checkin_saves_everything(client, app):
    _pet(client)
    response = client.post("/animals/1/checkin", data=_full(markers=["2"], weight="24.5", weight_unit="kg",
                                                              appetite="low", mobility=3), follow_redirects=True)
    assert b"Saved Maggie" in response.data
    with app.app_context():
        e = entries.get_entry_for_date(1, TODAY)
        assert e.day_status == "mixed" and e.has_scores and e.mobility == 3
        assert round(e.mean, 2) == round((6 * 6 + 3) / 7, 2)
        assert e.weight == 24.5 and e.appetite == "low" and e.notes == "Slept a lot."
        assert markers.responses_for_entry(e.id)[2] is True and markers.responses_for_entry(e.id)[1] is False


def test_scores_can_be_skipped_and_added_later_without_losing_status(client, app):
    _pet(client)
    client.post("/animals/1/checkin", data=_full(scores_included="0"))
    with app.app_context():
        e = entries.get_entry_for_date(1, TODAY)
        assert e.day_status == "mixed" and not e.has_scores
    # Later: add scores through the full form without re-sending the status.
    client.post("/animals/1/checkin", data={"entry_date": TODAY.isoformat(), "scores_included": "1", **{k: 7 for k in KEYS}})
    with app.app_context():
        e = entries.get_entry_for_date(1, TODAY)
        assert e.day_status == "mixed" and e.has_scores and e.mean == 7.0
        assert e.notes == "Slept a lot."  # untouched


def test_quick_checkin_does_not_wipe_earlier_scores(client, app):
    _pet(client)
    client.post("/animals/1/checkin", data=_full())
    client.post("/animals/1/checkin/quick", data={"entry_date": TODAY.isoformat(), "day_status": "bad"})
    with app.app_context():
        e = entries.get_entry_for_date(1, TODAY)
        assert e.day_status == "bad" and e.has_scores


def test_validation(client):
    _pet(client)
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    assert client.post("/animals/1/checkin", data=_full(entry_date=tomorrow)).status_code == 400
    assert client.post("/animals/1/checkin", data=_full(mobility=11)).status_code == 400
    assert client.post("/animals/1/checkin", data=_full(weight="heavy")).status_code == 400
    assert client.post("/animals/1/checkin", data=_full(day_status="great")).status_code == 400


def test_checkin_page_asks_the_first_question_first(client):
    _pet(client)
    page = client.get("/animals/1/checkin").data.decode()
    assert "Was today a good day or a bad day for Maggie?" in page
    assert page.index("Was today a good day") < page.index("What did Maggie do today?") < page.index("How comfortable did Maggie seem today?")
    assert "Anything different today?" in page
    assert "Medication change, vet visit" in page


def test_archived_pet_cannot_check_in(client):
    _pet(client)
    client.post("/animals/1/archive")
    assert b"is archived" in client.get("/animals/1/checkin", follow_redirects=True).data


def test_delete_entry_and_photos(client, app):
    _pet(client)
    buf = io.BytesIO(); Image.new("RGB", (900, 600), (1, 2, 3)).save(buf, format="JPEG"); buf.seek(0)
    client.post("/animals/1/checkin", data={**_full(), "photos": [(buf, "a.jpg")]}, content_type="multipart/form-data")
    with app.app_context():
        e = entries.get_entry_for_date(1, TODAY)
        path = app.config["PHOTO_DIR"] / entries.list_entry_photos(e.id)[0].file_path
    assert path.exists()
    response = client.post(f"/entries/{e.id}/delete", follow_redirects=True)
    assert b"Check-in removed" in response.data
    assert not path.exists()


def test_medications(client, app):
    _pet(client)
    client.post("/animals/1/medications", data={"name": "Gabapentin", "dose": "100 mg", "start_date": "2026-01-01"})
    assert client.post("/animals/1/medications", data={"name": ""}).status_code == 400
    client.post("/animals/1/checkin", data=_full(given=["1"]))
    with app.app_context():
        e = entries.get_entry_for_date(1, TODAY)
        assert entries.medications_given_names(e.id) == ["Gabapentin"]
    client.post("/medications/1/toggle")
    with app.app_context():
        m = entries.get_medication(1)
        assert m.active is False and m.end_date == TODAY
