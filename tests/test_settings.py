import io
import zipfile

from app import models


def _add_pet(client, name="Mochi"):
    client.post("/animals/new", data={"name": name, "species": "cat"})


def test_settings_page(client):
    response = client.get("/settings")
    assert response.status_code == 200
    assert b"Download backup" in response.data


def test_backup_contains_database_and_photos(client, app):
    _add_pet(client)
    (app.config["PHOTO_DIR"] / "animals").mkdir(parents=True)
    (app.config["PHOTO_DIR"] / "animals" / "1.jpg").write_bytes(b"jpegdata")
    response = client.get("/settings/backup.zip")
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(response.data))
    assert "tracker.sqlite" in zf.namelist()
    assert "photos/animals/1.jpg" in zf.namelist()


def test_restore_replaces_data(client, app):
    _add_pet(client, "Mochi")
    backup = client.get("/settings/backup.zip").data
    _add_pet(client, "Rex")
    with app.app_context():
        assert len(models.list_animals()) == 2
    response = client.post(
        "/settings/restore",
        data={"backup": (io.BytesIO(backup), "backup.zip"), "confirm": "yes"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Backup restored. 1 pet loaded." in response.data
    with app.app_context():
        names = [a.name for a in models.list_animals()]
    assert names == ["Mochi"]


def test_restore_requires_confirmation(client, app):
    _add_pet(client)
    backup = client.get("/settings/backup.zip").data
    _add_pet(client, "Rex")
    response = client.post(
        "/settings/restore",
        data={"backup": (io.BytesIO(backup), "backup.zip")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"tick the box" in response.data
    with app.app_context():
        assert len(models.list_animals()) == 2


def test_restore_rejects_bad_files(client, app):
    _add_pet(client)
    for payload, message in (
        (b"not a zip", b"not a zip backup"),
        (_zip({"readme.txt": b"hi"}), b"does not contain a tracker database"),
        (_zip({"tracker.sqlite": b"garbage"}), b"not readable"),
        (_zip({"tracker.sqlite": b"x", "../evil": b"x"}), b"unsafe paths"),
    ):
        response = client.post(
            "/settings/restore",
            data={"backup": (io.BytesIO(payload), "b.zip"), "confirm": "yes"},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert message in response.data, message
    with app.app_context():
        assert len(models.list_animals()) == 1


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_secret_key_is_generated_and_reused(app):
    key_file = app.config["DATA_DIR"] / "secret_key"
    assert key_file.exists()
    assert len(app.config["SECRET_KEY"]) == 64
    from app import create_app
    again = create_app({"TESTING": True, "DATA_DIR": app.config["DATA_DIR"],
                        "DATABASE": app.config["DATABASE"], "PHOTO_DIR": app.config["PHOTO_DIR"]})
    assert again.config["SECRET_KEY"] == app.config["SECRET_KEY"]
