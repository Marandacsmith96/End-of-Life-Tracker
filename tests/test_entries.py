import io
from datetime import date, timedelta

from PIL import Image

from app import entries

TODAY = date.today()


def _add_pet(client, name="Mochi", species="cat"):
    client.post("/animals/new", data={"name": name, "species": species})


def _entry_data(**overrides):
    data = {
        "entry_date": TODAY.isoformat(),
        "hurt": 7, "hunger": 6, "hydration": 8, "hygiene": 9,
        "happiness": 5, "mobility": 4, "good_days": 6,
        "weight": "4.2", "weight_unit": "kg", "appetite": "low",
        "notes": "Slept most of the day.",
    }
    data.update(overrides)
    return data


def test_log_page_defaults_to_today(client):
    _add_pet(client)
    response = client.get("/animals/1/log")
    assert response.status_code == 200
    assert TODAY.isoformat().encode() in response.data
    assert b"Save entry" in response.data


def test_save_entry(client, app):
    _add_pet(client)
    response = client.post("/animals/1/log", data=_entry_data(), follow_redirects=True)
    assert b"Saved Mochi" in response.data
    with app.app_context():
        entry = entries.get_entry_for_date(1, TODAY)
    assert entry is not None
    assert entry.total == 45
    assert entry.weight == 4.2
    assert entry.weight_unit == "kg"
    assert entry.appetite == "low"
    assert entry.notes == "Slept most of the day."


def test_saving_same_day_twice_updates_instead_of_duplicating(client, app):
    _add_pet(client)
    client.post("/animals/1/log", data=_entry_data())
    client.post("/animals/1/log", data=_entry_data(hurt=2, notes="Worse today"))
    with app.app_context():
        all_entries = entries.list_entries(1)
    assert len(all_entries) == 1
    assert all_entries[0].hurt == 2
    assert all_entries[0].notes == "Worse today"


def test_log_page_prefills_existing_entry(client):
    _add_pet(client)
    client.post("/animals/1/log", data=_entry_data(notes="Prefill me"))
    response = client.get(f"/animals/1/log?date={TODAY.isoformat()}")
    assert b"Prefill me" in response.data
    assert b"Update entry" in response.data


def test_future_date_rejected(client, app):
    _add_pet(client)
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    response = client.post("/animals/1/log", data=_entry_data(entry_date=tomorrow))
    assert response.status_code == 400
    assert b"has not happened yet" in response.data
    with app.app_context():
        assert entries.list_entries(1) == []


def test_score_out_of_range_rejected(client):
    _add_pet(client)
    response = client.post("/animals/1/log", data=_entry_data(mobility=11))
    assert response.status_code == 400
    assert b"Mobility must be a whole number from 0 to 10" in response.data


def test_bad_weight_rejected(client):
    _add_pet(client)
    response = client.post("/animals/1/log", data=_entry_data(weight="heavy"))
    assert response.status_code == 400
    assert b"Weight must be a number" in response.data


def test_optional_fields_can_be_blank(client, app):
    _add_pet(client)
    client.post("/animals/1/log", data=_entry_data(weight="", appetite="", notes=""))
    with app.app_context():
        entry = entries.get_entry_for_date(1, TODAY)
    assert entry.weight is None
    assert entry.weight_unit is None
    assert entry.appetite is None
    assert entry.notes is None


def test_archived_pet_cannot_be_logged(client):
    _add_pet(client)
    client.post("/animals/1/archive")
    response = client.get("/animals/1/log", follow_redirects=True)
    assert b"is archived" in response.data


def test_entries_appear_on_pet_page(client):
    _add_pet(client)
    client.post("/animals/1/log", data=_entry_data())
    response = client.get("/animals/1")
    assert b"Edit today" in response.data
    assert b">45<" in response.data
    assert b"Slept most of the day." in response.data


def test_delete_entry(client, app):
    _add_pet(client)
    client.post("/animals/1/log", data=_entry_data())
    with app.app_context():
        entry_id = entries.get_entry_for_date(1, TODAY).id
    response = client.post(f"/entries/{entry_id}/delete", follow_redirects=True)
    assert b"Entry deleted" in response.data
    with app.app_context():
        assert entries.get_entry(entry_id) is None


def test_list_entries_filters_by_date_range(client, app):
    _add_pet(client)
    for days_ago in (0, 1, 5, 10):
        day = (TODAY - timedelta(days=days_ago)).isoformat()
        client.post("/animals/1/log", data=_entry_data(entry_date=day))
    with app.app_context():
        window = entries.list_entries(1, start=TODAY - timedelta(days=6), end=TODAY)
        oldest_first = entries.list_entries(1, newest_first=False)
    assert [e.entry_date for e in window] == [TODAY, TODAY - timedelta(1), TODAY - timedelta(5)]
    assert oldest_first[0].entry_date == TODAY - timedelta(days=10)


# --- medications -------------------------------------------------------------

def test_add_and_toggle_medication(client, app):
    _add_pet(client)
    response = client.post(
        "/animals/1/medications",
        data={"name": "Gabapentin", "dose": "50 mg", "schedule": "twice a day"},
        follow_redirects=True,
    )
    assert b"Gabapentin added" in response.data
    client.post("/medications/1/toggle")
    with app.app_context():
        assert entries.get_medication(1).active is False
        assert entries.list_medications(1, active_only=True) == []


def test_medication_name_required(client):
    _add_pet(client)
    response = client.post("/animals/1/medications", data={"name": ""})
    assert response.status_code == 400


def test_entry_records_which_medications_were_given(client, app):
    _add_pet(client)
    client.post("/animals/1/medications", data={"name": "Gabapentin"})
    client.post("/animals/1/medications", data={"name": "Prednisolone"})
    client.post("/animals/1/log", data={**_entry_data(), "given": ["1"]})
    with app.app_context():
        entry = entries.get_entry_for_date(1, TODAY)
        assert entries.medications_given(entry.id) == {1}
        assert entries.medications_given_names(entry.id) == ["Gabapentin"]
    # Updating the day with none checked clears it.
    client.post("/animals/1/log", data=_entry_data())
    with app.app_context():
        assert entries.medications_given(entry.id) == set()
    response = client.get("/animals/1/log")
    assert b"Gabapentin" in response.data


def test_delete_medication_removes_it_from_form(client):
    _add_pet(client)
    client.post("/animals/1/medications", data={"name": "Gabapentin"})
    client.post("/medications/1/delete", follow_redirects=True)  # consumes the flash
    assert b"Gabapentin" not in client.get("/animals/1/log").data


# --- photos ------------------------------------------------------------------

def _jpeg(size=(1200, 900)):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 120, 80)).save(buf, format="JPEG")
    buf.seek(0)
    return buf


def test_entry_photos_upload_and_delete(client, app):
    _add_pet(client)
    response = client.post(
        "/animals/1/log",
        data={**_entry_data(), "photos": [(_jpeg(), "a.jpg"), (_jpeg(), "b.jpg")]},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"2 photos added" in response.data
    with app.app_context():
        entry = entries.get_entry_for_date(1, TODAY)
        photos = entries.list_entry_photos(entry.id)
    assert len(photos) == 2
    for photo in photos:
        path = app.config["PHOTO_DIR"] / photo.file_path
        assert path.exists()
        with Image.open(path) as img:
            assert max(img.size) <= 800
    page = client.get("/animals/1/log")
    assert page.data.count(b"Photo from this day") == 2

    client.post(f"/entries/photos/{photos[0].id}/delete")
    with app.app_context():
        assert len(entries.list_entry_photos(entry.id)) == 1
    assert not (app.config["PHOTO_DIR"] / photos[0].file_path).exists()


def test_bad_entry_photo_is_skipped_but_entry_saves(client, app):
    _add_pet(client)
    response = client.post(
        "/animals/1/log",
        data={**_entry_data(), "photos": [(io.BytesIO(b"nope"), "x.jpg")]},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"does not look like an image" in response.data
    assert b"Saved Mochi" in response.data
    with app.app_context():
        entry = entries.get_entry_for_date(1, TODAY)
        assert entries.list_entry_photos(entry.id) == []


def test_deleting_entry_removes_photo_files(client, app):
    _add_pet(client)
    client.post(
        "/animals/1/log",
        data={**_entry_data(), "photos": [(_jpeg(), "a.jpg")]},
        content_type="multipart/form-data",
    )
    with app.app_context():
        entry = entries.get_entry_for_date(1, TODAY)
        path = app.config["PHOTO_DIR"] / entries.list_entry_photos(entry.id)[0].file_path
    assert path.exists()
    client.post(f"/entries/{entry.id}/delete")
    assert not path.exists()
