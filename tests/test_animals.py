import io
from datetime import date

from PIL import Image

from app import models


def _add(client, name="Mochi", species="cat", **extra):
    return client.post("/animals/new", data={"name": name, "species": species, **extra}, follow_redirects=True)


def test_add_animal_goes_to_marker_setup_and_becomes_current(client, app):
    response = _add(client, breed="Tabby", birth_date="2012-05-01", sex="female", diagnoses="CKD")
    assert response.status_code == 200
    assert b"What does a good day look like for Mochi?" in response.data
    with app.app_context():
        animals = models.list_animals()
    assert len(animals) == 1 and animals[0].breed == "Tabby" and animals[0].birth_date == date(2012, 5, 1)
    assert animals[0].sex == "female" and animals[0].diagnoses == "CKD"


def test_validation(client, app):
    assert client.post("/animals/new", data={"name": "  ", "species": "dog"}).status_code == 400
    assert client.post("/animals/new", data={"name": "Nemo", "species": "fish"}).status_code == 400
    assert client.post("/animals/new", data={"name": "Rex", "species": "dog", "birth_date": "2999-01-01"}).status_code == 400
    with app.app_context():
        assert models.list_animals() == []


def test_edit_animal(client, app):
    _add(client)
    response = client.post("/animals/1/edit", data={"name": "Mochi Jr", "species": "cat"}, follow_redirects=True)
    assert b"Saved." in response.data
    with app.app_context():
        assert models.get_animal(1).name == "Mochi Jr"


def test_archive_and_restore(client, app):
    _add(client)
    response = client.post("/animals/1/archive", follow_redirects=True)
    assert b"has been archived" in response.data
    with app.app_context():
        assert models.get_animal(1).status == "archived" and models.list_animals() == []
    response = client.post("/animals/1/unarchive", follow_redirects=True)
    assert b"is active again" in response.data


def test_passing_flow_is_gentle_and_keeps_everything(client, app):
    _add(client)
    client.post("/animals/1/checkin/quick", data={"entry_date": date.today().isoformat(), "day_status": "good"})
    page = client.get("/animals/1/passed")
    assert b"sorry you're saying goodbye" in page.data
    for banned in (b"Delete pet", b"Close account", b"Terminate"):
        assert banned not in page.data
    response = client.post("/animals/1/passed", data={"passed_date": date.today().isoformat()}, follow_redirects=True)
    assert b"In memory of Mochi" in response.data
    assert b"Keep their profile and history" in response.data
    with app.app_context():
        a = models.get_animal(1)
        assert a.status == "passed" and a.reminder == "off" and a.passed_date == date.today()
    today = client.get("/animals/1/today")
    assert b"In memory of Mochi" in today.data
    assert b"No check-in recorded today" not in today.data
    assert client.get("/animals/1/checkin", follow_redirects=True).status_code == 200
    with app.app_context():
        from app import entries
        assert len(entries.list_entries(1)) == 1  # nothing deleted


def test_remove_requires_typing_the_name(client, app):
    _add(client)
    assert client.post("/animals/1/remove", data={"confirm_name": "nope"}).status_code == 400
    response = client.post("/animals/1/remove", data={"confirm_name": "mochi"}, follow_redirects=True)
    assert b"have been removed" in response.data
    with app.app_context():
        assert models.get_animal(1) is None


def test_reminder_setting(client, app):
    _add(client)
    client.post("/animals/1/reminder", data={"reminder": "off"})
    with app.app_context():
        assert models.get_animal(1).reminder == "off"
    page = client.get("/animals/1/trends")
    assert b"No check-in recorded today" not in page.data
    client.post("/animals/1/reminder", data={"reminder": "daily"})
    page = client.get("/animals/1/trends")
    assert b"No check-in recorded today" in page.data


def _fake_image(fmt="JPEG", size=(1600, 1200), mode="RGB"):
    buf = io.BytesIO()
    Image.new(mode, size, color=(120, 160, 90) if mode == "RGB" else (120, 160, 90, 128)).save(buf, format=fmt)
    buf.seek(0)
    return buf


def test_photo_upload_resizes_and_serves(client, app):
    _add(client)
    response = client.post("/animals/1/photo", data={"photo": (_fake_image(), "big.jpg")},
                           content_type="multipart/form-data", follow_redirects=True)
    assert b"Photo updated" in response.data
    with app.app_context():
        path = models.get_animal(1).photo_path
        saved = app.config["PHOTO_DIR"] / path
    assert path == "animals/1.jpg"
    with Image.open(saved) as img:
        assert max(img.size) <= 800
    assert client.get(f"/photos/{path}").mimetype == "image/jpeg"
    client.post("/animals/1/photo/delete")
    assert not saved.exists()


def test_non_image_upload_is_rejected(client, app):
    _add(client)
    response = client.post("/animals/1/photo", data={"photo": (io.BytesIO(b"nope"), "x.jpg")},
                           content_type="multipart/form-data", follow_redirects=True)
    assert b"does not look like an image" in response.data


def test_age_text_and_initials():
    today = date.today()
    animal = models.Animal(1, "Xena", "cat", None, None, None, None, None, "active", None, "daily")
    assert animal.age_text is None and animal.initials == "X"
    animal.birth_date = date(today.year - 3, today.month, today.day)
    assert animal.age_text == "3 years"
