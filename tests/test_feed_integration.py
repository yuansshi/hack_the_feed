import base64
import hashlib
import json
from pathlib import Path
import shutil

import httpx
import pytest
from fastapi.testclient import TestClient

import faithful_tours
import server


ORIGINAL_TOURS = faithful_tours.TOURS


@pytest.fixture
def source_root(tmp_path, monkeypatch):
    shutil.copyfile(ORIGINAL_TOURS / 'manifest.json', tmp_path / 'manifest.json')
    monkeypatch.setattr(faithful_tours, 'TOURS', tmp_path)
    return tmp_path


@pytest.fixture
def client(monkeypatch, source_root):
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
def manifest(source_root):
    return json.loads((source_root / 'manifest.json').read_text())


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
        assert row['video_duration_label'] == 'Video pending'
        assert row['generated_video'] is None
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
    monkeypatch.setattr(faithful_tours, 'TOURS', tmp_path / 'missing')
    response = client.get('/api/feed/94404')
    assert response.status_code == 503
    assert response.json() == {'detail': 'Run python scripts/build_94404.py first.'}


# A tiny neutral gray MP4; never a listing or demonstration-house video.
NEUTRAL_MP4 = base64.b64decode(
    'AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAMxbW9vdgAAAGxtdmhkAAAAAAAAAAAAAAAAAAAD6AAAAZAAAQAAAQAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAlx0cmFrAAAAXHRraGQAAAADAAAAAAAAAAAAAAABAAAAAAAAAZAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAACAAAAAgAAAAAAAkZWR0cwAAABxlbHN0AAAAAAAAAAEAAAGQAAAAAAABAAAAAAHUbWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAAAoAAAAEABVxAAAAAAALWhkbHIAAAAAAAAAAHZpZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAABf21pbmYAAAAUdm1oZAAAAAEAAAAAAAAAAAAAACRkaW5mAAAAHGRyZWYAAAAAAAAAAQAAAAx1cmwgAAAAAQAAAT9zdGJsAAAAv3N0c2QAAAAAAAAAAQAAAK9hdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAACAAIABIAAAASAAAAAAAAAABFExhdmM2My4xLjEwMSBsaWJ4MjY0AAAAAAAAAAAAAAAAGP//AAAANWF2Y0MBZAAK/+EAGGdkAAqs2UlsBEAAAAMAQAAAAwKDxIllgAEABmjr48siwP34+AAAAAAQcGFzcAAAAAEAAAABAAAAFGJ0cnQAAAAAAAA4pAAAAAAAAAAYc3R0cwAAAAAAAAABAAAAAgAACAAAAAAUc3RzcwAAAAAAAAABAAAAAQAAABxzdHNjAAAAAAAAAAEAAAABAAAAAgAAAAEAAAAcc3RzegAAAAAAAAAAAAAAAgAAAsgAAAANAAAAFHN0Y28AAAAAAAAAAQAAA2EAAABhdWR0YQAAAFltZXRhAAAAAAAAACFoZGxyAAAAAAAAAABtZGlyYXBwbAAAAAAAAAAAAAAAACxpbHN0AAAAJKl0b28AAAAcZGF0YQAAAAEAAAAATGF2ZjYzLjEuMTAxAAAACGZyZWUAAALdbWRhdAAAAq0GBf//qdxF6b3m2Ui3lizYINkj7u94MjY0IC0gY29yZSAxNjUgcjMyMjIgYjM1NjA1YSAtIEguMjY0L01QRUctNCBBVkMgY29kZWMgLSBDb3B5bGVmdCAyMDAzLTIwMjUgLSBodHRwOi8vd3d3LnZpZGVvbGFuLm9yZy94MjY0Lmh0bWwgLSBvcHRpb25zOiBjYWJhYz0xIHJlZj0zIGRlYmxvY2s9MTowOjAgYW5hbHlzZT0weDM6MHgxMTMgbWU9aGV4IHN1Ym1lPTcgcHN5PTEgcHN5X3JkPTEuMDA6MC4wMCBtaXhlZF9yZWY9MSBtZV9yYW5nZT0xNiBjaHJvbWFfbWU9MSB0cmVsbGlzPTEgOHg4ZGN0PTEgY3FtPTAgZGVhZHpvbmU9MjEsMTEgZmFzdF9wc2tpcD0xIGNocm9tYV9xcF9vZmZzZXQ9LTIgdGhyZWFkcz0xIGxvb2thaGVhZF90aHJlYWRzPTEgc2xpY2VkX3RocmVhZHM9MCBucj0wIGRlY2ltYXRlPTEgaW50ZXJsYWNlZD0wIGJsdXJheV9jb21wYXQ9MCBjb25zdHJhaW5lZF9pbnRyYT0wIGJmcmFtZXM9MyBiX3B5cmFtaWQ9MiBiX2FkYXB0PTEgYl9iaWFzPTAgZGlyZWN0PTEgd2VpZ2h0Yj0xIG9wZW5fZ29wPTAgd2VpZ2h0cD0yIGtleWludD0yNTAga2V5aW50X21pbj01IHNjZW5lY3V0PTQwIGludHJhX3JlZnJlc2g9MCByY19sb29rYWhlYWQ9NDAgcmM9Y3JmIG1idHJlZT0xIGNyZj0yMy4wIHFjb21wPTAuNjAgcXBtaW49MCBxcG1heD02OSBxcHN0ZXA9NCBpcF9yYXRpbz0xLjQwIGFxPTE6MS4wMACAAAAAE2WIhAAQ//73gb8yfaqyWn2EN8EAAAAJQZohbEP//quA'
)


@pytest.fixture
def accepted_video(source_root, manifest):
    listing = next(row for row in manifest['listings'] if row['model'])
    plan = next(photo for photo in listing['photos'] if photo['index'] == listing['model']['floor_plan_index'])
    anchors = [photo for photo in listing['photos'] if photo != plan][:2]
    for photo in [*anchors, plan]:
        target = source_root / photo['path']
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(ORIGINAL_TOURS / photo['path'], target)
    path = source_root / 'videos' / 'reviewed-pilot.mp4'
    path.parent.mkdir()
    path.write_bytes(NEUTRAL_MP4)
    record = {
        'listing_id': listing['id'],
        'path': 'videos/reviewed-pilot.mp4',
        'sha256': hashlib.sha256(NEUTRAL_MP4).hexdigest(),
        'status': 'accepted',
        'review': {'appearance': 'pass', 'layout': 'pass', 'motion': 'pass', 'notes': 'Test review attestation.'},
        'source_sha256': [photo['sha256'] for photo in [*anchors, plan]],
        'label': 'AI-generated walkthrough · reviewed pilot',
    }
    return record, listing, path


def write_video_registry(source_root, record):
    (source_root / 'generated_videos.json').write_text(json.dumps({'videos': [record]}))


def test_only_reviewed_source_grounded_video_is_exposed_and_range_served(client, source_root, manifest, accepted_video):
    record, listing, path = accepted_video
    original_manifest = (source_root / 'manifest.json').read_bytes()
    write_video_registry(source_root, record)
    url = '/api/faithful/videos/reviewed-pilot.mp4'
    rows = client.get('/api/feed/94404').json()['listings']
    row = next(row for row in rows if row['id'] == listing['id'])
    assert row['preview_clip_url'] == row['full_tour_url'] == url
    assert row['video_duration_label'] == record['label']
    assert row['generated_video']['review'] == record['review']
    assert row['photos'] == listing['photos']
    assert all(other['preview_clip_url'] is None for other in rows if other['id'] != listing['id'])
    raw = client.get('/api/faithful/94404').json()['listings']
    assert next(item for item in raw if item['id'] == listing['id'])['generated_video'] == row['generated_video']
    assert (source_root / 'manifest.json').read_bytes() == original_manifest
    video = client.get(url)
    assert video.status_code == 200
    assert video.headers['content-type'] == 'video/mp4'
    assert video.headers['cache-control'] == 'no-store'
    assert video.content == path.read_bytes()
    partial = client.get(url, headers={'Range': 'bytes=0-31'})
    assert partial.status_code == 206
    assert partial.content == NEUTRAL_MP4[:32]


@pytest.mark.parametrize('problem, status', [
    ('unreviewed', 404), ('failed_review', 404), ('empty_notes', 404),
    ('unknown_listing', 404), ('foreign_hash', 404), ('missing_plan', 404),
    ('one_anchor', 404), ('missing_media', 404), ('tampered_media', 409),
    ('wrong_checksum', 409), ('non_mp4', 409), ('path_escape', 404),
    ('tampered_source', 404), ('missing_source', 404), ('malformed_listing', 404),
])
def test_unreviewed_unrelated_or_changed_media_never_enters_feed(client, source_root, manifest, accepted_video, problem, status):
    record, listing, path = accepted_video
    if problem == 'unreviewed': record['status'] = 'unreviewed'
    elif problem == 'failed_review': record['review']['layout'] = 'fail'
    elif problem == 'empty_notes': record['review']['notes'] = '  '
    elif problem == 'unknown_listing': record['listing_id'] = 'unrelated-home'
    elif problem == 'foreign_hash': record['source_sha256'][0] = manifest['listings'][0]['photos'][0]['sha256']
    elif problem == 'missing_plan': record['source_sha256'].pop()
    elif problem == 'one_anchor': record['source_sha256'].pop(0)
    elif problem == 'missing_media': path.unlink()
    elif problem == 'tampered_media': path.write_bytes(NEUTRAL_MP4 + b'changed')
    elif problem == 'wrong_checksum': record['sha256'] = '0' * 64
    elif problem == 'non_mp4':
        path.write_bytes(b'not a video')
        record['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif problem == 'path_escape': record['path'] = '../reviewed-pilot.mp4'
    elif problem in ('tampered_source', 'missing_source'):
        source = source_root / listing['photos'][0]['path']
        if problem == 'tampered_source': source.write_bytes(b'changed original')
        else: source.unlink()
    elif problem == 'malformed_listing': record['listing_id'] = {'bad': 'id'}
    write_video_registry(source_root, record)
    for endpoint in ('/api/feed/94404', '/api/faithful/94404'):
        response = client.get(endpoint)
        assert response.status_code == 200
        assert all(row['generated_video'] is None for row in response.json()['listings'])
        if endpoint == '/api/feed/94404':
            assert all(row['preview_clip_url'] is None and row['full_tour_url'] is None for row in response.json()['listings'])
    assert client.get('/api/faithful/videos/reviewed-pilot.mp4').status_code == status


def test_plan_index_refers_to_source_photo_index_not_array_position(client, source_root, manifest, accepted_video):
    record, listing, _ = accepted_video
    listing['photos'].reverse()
    (source_root / 'manifest.json').write_text(json.dumps(manifest))
    write_video_registry(source_root, record)
    rows = client.get('/api/feed/94404').json()['listings']
    assert next(row for row in rows if row['id'] == listing['id'])['preview_clip_url'] == '/api/faithful/videos/reviewed-pilot.mp4'


def test_bad_optional_registry_fails_closed_without_breaking_source_browsing(client, source_root):
    (source_root / 'generated_videos.json').write_text('not JSON')
    assert client.get('/api/feed/94404').status_code == 200
    assert client.get('/api/faithful/videos/anything.mp4').status_code == 404
