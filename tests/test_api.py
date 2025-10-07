import json


def test_health(app_client):
    resp = app_client.get('/health')
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'ok'


def _login(client):
    return client.post('/api/auth/login', json={'username': 'u', 'password': 'p'})


def test_auth_and_instruments(app_client):
    tok = _login(app_client)
    assert tok.status_code == 200
    token = tok.get_json()['access_token']

    resp = app_client.get('/api/instruments', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'stocks' in data


def test_historical_and_forecast(monkeypatch, app_client):
    tok = _login(app_client)
    token = tok.get_json()['access_token']

    # historical
    h = app_client.get('/api/historical/AAPL', headers={'Authorization': f'Bearer {token}'})
    assert h.status_code in (200, 503)

    # forecast
    f = app_client.post('/api/forecast', headers={'Authorization': f'Bearer {token}'}, json={'symbol': 'AAPL', 'horizon': 3, 'model_type': 'baseline'})
    assert f.status_code == 200
    fj = f.get_json()
    assert fj.get('status') in ('queued', 'completed')


