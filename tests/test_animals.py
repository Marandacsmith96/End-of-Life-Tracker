import io
from datetime import date

from PIL import Image

from app import models


def _add(client, name="Mochi", species="cat", **extra):
    data = {"name": name, "species": species, **extra}
    return client.post("/animals/new", data=data, follow_redirects=True)


def test_dashboard_shows_empty_state(client):
    response = client.get("/")
    assert b"Start by adding the pet" in response.data


def test_add_animal_and_it_becomes_current(client, app):
    response = _add(client, breed="Tabby", birth_date="2012-05-01")
    assert response.status_code == 200
    assert b"Mochi added" in response.data
    with app.app_context():
        animals = models.list_animals()
    assert len(animals) == 1
    assert animals[0].breed == "Tabby"
    assert animals[0].birth_date == date(2012, 5, 1)
    assert b"Tracking <a" in client.get("/").data


def test_name_is_required(client, app):
    response = client.post("/animals/new", data={"name": "  ", "species": "dog"})
    assert response.status_code == 400
    assert b"give your pet a name" in response.data
    with app.app_context():
        assert models.list_animals() == []


def test_species_must_be_cat_or_dog(client):
    response = client.post("/animals/new", data={"name": "Nemo", "species": "fish"})
    assert response.status_code == 400
    assert b"choose cat or dog" in response.data


def test_birth_date_cannot_be_in_future(client):
    response = client.post(
        "/animals/new", data={"name": "Rex", "species": "dog", "birth_date": "2999-01-01"}
    )
    assert response.status_code == 400
    assert b"cannot be in the future" in response.data


def test_edit_animal(client, app):
    _add(client)
    response = client.post(
        "/animals/1/edit",
        data={"name": "Mochi Jr", "species": "cat", "breed": "", "birth_date": ""},
        follow_redirects=True,
    )
    assert b"Saved." in response.data
    with app.app_context():
        assert models.get_animal(1).name == "Mochi Jr"


def test_archive_hides_from_active_list_and_clears_selection(client, app):
    _add(client)
    response = client.post("/animals/1/archive", follow_redirects=True)
    assert b"has been archived" in response.data
    assert b"Tracking <a" not in response.data
    assert b"Archived pets (1)" in response.data
    with app.app_context():
        assert models.list_animals() == []
        assert models.get_animal(1).archived is True


def test_unarchive_restores_animal(client, app):
    _add(client)
    client.post("/animals/1/archive")
    response = client.post("/animals/1/unarchive", follow_redirects=True)
    assert b"is active again" in response.data
    with app.app_context():
        assert models.get_animal(1).archived is False


def test_select_switches_current_animal(client):
    _add(client, name="Mochi")
    _add(client, name="Rex", species="dog")  # adding makes Rex current
    assert b"Tracking <a" in client.get("/").data
    response = client.post("/animals/1/select", follow_redirects=True)
    assert b"Now tracking Mochi" in response.data


def test_unknown_animal_is_404(client):
    assert client.get("/animals/999").status_code == 404


def _fake_image(fmt="JPEG", size=(1600, 1200), mode="RGB"):
    buf = io.BytesIO()
    Image.new(mode, size, color=(120, 160, 90) if mode == "RGB" else (120, 160, 90, 128)).save(
        buf, format=fmt
    )
    buf.seek(0)
    return buf


def test_photo_upload_resizes_and_serves(client, app):
    _add(client)
    response = client.post(
        "/animals/1/photo",
        data={"photo": (_fake_image(), "big.jpg")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Photo updated" in response.data
    with app.app_context():
        path = models.get_animal(1).photo_path
        saved = app.config["PHOTO_DIR"] / path
    assert path == "animals/1.jpg"
    with Image.open(saved) as img:
        assert max(img.size) <= 800
    served = client.get(f"/photos/{path}")
    assert served.status_code == 200
    assert served.mimetype == "image/jpeg"


def test_photo_with_transparency_is_saved_as_png(client, app):
    _add(client)
    client.post(
        "/animals/1/photo",
        data={"photo": (_fake_image("PNG", (300, 300), "RGBA"), "clear.png")},
        content_type="multipart/form-data",
    )
    with app.app_context():
        assert models.get_animal(1).photo_path == "animals/1.png"


def test_replacing_photo_removes_old_file(client, app):
    _add(client)
    client.post(
        "/animals/1/photo",
        data={"photo": (_fake_image(), "a.jpg")},
        content_type="multipart/form-data",
    )
    client.post(
        "/animals/1/photo",
        data={"photo": (_fake_image("PNG", (300, 300), "RGBA"), "b.png")},
        content_type="multipart/form-data",
    )
    folder = app.config["PHOTO_DIR"] / "animals"
    assert sorted(p.name for p in folder.iterdir()) == ["1.png"]


def test_non_image_upload_is_rejected(client, app):
    _add(client)
    response = client.post(
        "/animals/1/photo",
        data={"photo": (io.BytesIO(b"not an image"), "notes.jpg")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"does not look like an image" in response.data
    with app.app_context():
        assert models.get_animal(1).photo_path is None


def test_delete_photo(client, app):
    _add(client)
    client.post(
        "/animals/1/photo",
        data={"photo": (_fake_image(), "a.jpg")},
        content_type="multipart/form-data",
    )
    response = client.post("/animals/1/photo/delete", follow_redirects=True)
    assert b"Photo removed" in response.data
    with app.app_context():
        assert models.get_animal(1).photo_path is None
    assert not (app.config["PHOTO_DIR"] / "animals" / "1.jpg").exists()


def test_age_text():
    today = date.today()
    animal = models.Animal(1, "X", "cat", None, None, None, False)
    assert animal.age_text is None
    animal.birth_date = date(today.year - 3, today.month, today.day)
    assert animal.age_text == "3 years"
