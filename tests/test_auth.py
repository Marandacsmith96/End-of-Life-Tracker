from app import create_app


def _locked_app(tmp_path):
    d = tmp_path / "data"
    return create_app({"TESTING": True, "DATA_DIR": d, "DATABASE": d / "t.sqlite", "PHOTO_DIR": d / "p",
                       "PASSCODE": "open sesame"})


def test_no_passcode_means_no_lock(client):
    assert client.get("/unlock").status_code == 302
    assert client.get("/").status_code == 200


def test_passcode_gates_every_page(tmp_path):
    c = _locked_app(tmp_path).test_client()
    r = c.get("/")
    assert r.status_code == 302 and "/unlock" in r.headers["Location"]
    assert c.get("/static/style.css").status_code == 200  # assets stay reachable
    assert c.post("/unlock", data={"passcode": "wrong"}).status_code == 401
    r = c.post("/unlock?next=/pets", data={"passcode": "open sesame"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/pets")
    assert c.get("/").status_code == 200
    c.post("/lock")
    assert c.get("/").status_code == 302
