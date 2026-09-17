def test_landing_when_no_pets(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"See the pattern, not just the day." in response.data
    assert b"Villalobos" in response.data
    assert b"does not provide veterinary diagnosis" in response.data  # persistent disclaimer


def test_no_gamification_copy(client):
    body = client.get("/").data.lower()
    for banned in (b"streak", b"badge", b"\xf0\x9f\x90\xbe", b"oops", b"furry friend"):
        assert banned not in body
