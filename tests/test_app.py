def test_dashboard_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Pet Quality-of-Life Tracker" in response.data
