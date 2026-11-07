import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import faithful_tours
import server


@pytest.fixture
def client(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Source feed browsing must not call a service or invent social proof')

    monkeypatch.setattr(server, 'load_api_key', forbidden)
    monkeypatch.setattr(server, 'get_or_init_listing_social', forbidden)
    monkeypatch.setattr(server, 'poll_and_download_gmi_request', forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    with TestClient(server.app) as client:
        yield client


@pytest.fixture
def manifest():
    return json.loads((faithful_tours.TOURS / 'manifest.json').read_text())


def test_source_feed_keeps_property_identity_price_order_and_coverage(client, manifest):
    response = client.get('/api/feed/94404')
    assert response.status_code == 200
    result = response.json()
    assert [row['id'] for row in result['listings']] == [row['id'] for row in manifest['listings']]
    assert [row['price_num'] for row in result['listings']] == sorted(
        [row['price'] for row in manifest['listings']], reverse=True
    )
    for row, original in zip(result['listings'], manifest['listings'], strict=True):
        assert row['source_backed'] is True
        assert row['address'] == original['address']
        assert row['zip_code'] == '94404'
        assert row['price'] == f"${original['price']:,.0f}"
        assert row['title'] == original['address'].split(',')[0]
        assert row['city'] == original['address'].split(',')[1].strip()
        assert (row['beds'], row['baths'], row['sqft']) == (
            original['beds'], original['baths'], original['sqft']
        )
    for field in ('summary', 'selection', 'requested_count'):
        assert result[field] == manifest[field]


def test_source_feed_has_only_its_own_original_photos_and_no_demo_video(client, manifest):
    rows = client.get('/api/feed/94404').json()['listings']
    for row, original in zip(rows, manifest['listings'], strict=True):
        assert row['photos'] == original['photos']
        assert row['model'] == original['model']
        assert row['rooms'] == [{
            'id': 'photo-0',
            'image_url': '/api/faithful/assets/' + Path(original['photos'][0]['path']).name,
            'on_screen_hook': original['address'].split(',')[0],
            'short_name': 'Original photo',
        }]
        assert row['preview_clip_url'] is None
        assert row['full_tour_url'] is None
        assert row['video_duration_label'] == 'Original photos'
        assert row['research_url'] == f"/94404?embed=1&view=model#{original['id']}"
    assert sum(row['model'] is not None for row in rows) == 1


def test_source_feed_has_no_invented_social_proof(client):
    rows = client.get('/api/feed/94404').json()['listings']
    for row in rows:
        social = row['social']
        for field in ('thumbs_up', 'thumbs_down', 'open_house_live_count', 'verified_checkins'):
            assert social[field] == 0
        assert social['comments'] == social['visitor_media'] == []
        assert social['attributes'] == {}
        assert social['amazon_stars'] is None
        assert social['upvote_ratio'] is None
        assert social['hybrid_rank_score'] is None


def test_missing_source_manifest_is_an_explicit_service_error(client, monkeypatch, tmp_path):
    monkeypatch.setattr(faithful_tours, 'TOURS', tmp_path)
    response = client.get('/api/feed/94404')
    assert response.status_code == 503
    assert response.json() == {'detail': 'Run python scripts/build_94404.py first.'}
