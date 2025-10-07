def test_latest_endpoint(app_client):
    resp = app_client.get('/api/latest/AAPL')
    # Accept 200 or 503 (unavailable) depending on external API
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        data = resp.get_json()
        assert 'symbol' in data and data['symbol'] == 'AAPL'
        assert 'open' in data and 'close' in data
