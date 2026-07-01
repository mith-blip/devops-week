import app

def test_health():
    # Flask's test client lets us hit routes without a running server
    client = app.app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"

def test_home():
    client = app.app.test_client()
    response = client.get("/")
    assert response.status_code == 500