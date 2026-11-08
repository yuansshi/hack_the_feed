"""Exercise Gemini route lifecycle without project credentials or live services."""
import asyncio
import base64
import io
import json
import wave
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

import server


# A format-header fixture for byte-preserving API round trips, not a rendered clip.
VIDEO_BYTES = b'\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2' + b'fixture' * 10


def output(interaction_id, kind, value, mime=None):
    part = {'type': kind}
    if kind == 'text':
        part['text'] = value
    else:
        part.update(data=base64.b64encode(value).decode(), mime_type=mime)
    return {'id': interaction_id, 'status': 'completed',
            'steps': [{'type': 'model_output', 'content': [part]}]}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    cache = tmp_path / 'cache'
    cache.mkdir()
    monkeypatch.setattr(server, 'CACHE_DIR', cache)
    monkeypatch.setattr(server, 'CACHE_INDEX_PATH', tmp_path / 'cache_index.json')
    monkeypatch.setattr(server, 'generation_lock', asyncio.Lock())
    monkeypatch.setattr(server, 'get_or_init_listing_social', lambda listing_id: {})
    rooms = []
    for room_id, color in [('first', '#835a42'), ('last', '#d9d1b8')]:
        filename = f'img_test-house_{room_id}_fixture.jpg'
        Image.new('RGB', (32, 24), color).save(cache / filename)
        rooms.append({'id': room_id, 'image_url': f'https://example.invalid/{room_id}.jpg'})
    listing = {'id': 'test-house', 'address': 'Fixture house', 'rooms': rooms,
               'transitions': [{'index': 0, 'from_room': 'first', 'to_room': 'last',
                                'prompt': 'One continuous camera move.'}]}
    monkeypatch.setattr(server, 'CURATED_LISTINGS', [listing])

    def forbidden(*args, **kwargs):
        raise AssertionError('Route lifecycle tests must not read credentials or call a service')

    monkeypatch.setattr(server.gemini, 'load_project_key', forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    provider = AsyncMock()
    monkeypatch.setattr(server, 'call_gemini', provider)
    with TestClient(server.app) as client:
        yield client, provider, cache


def segment_request():
    return {'listing_id': 'test-house', 'transition_index': 0,
            'from_room': 'first', 'to_room': 'last',
            'first_frame_url': '/api/cache/img_test-house_first_fixture.jpg',
            'last_frame_url': '/api/cache/img_test-house_last_fixture.jpg',
            'prompt': 'One continuous camera move.', 'model': server.gemini.VIDEO_MODEL}


def test_segment_queued_to_ready_resumes_without_duplicate_submission(setup):
    client, provider, cache = setup
    provider.side_effect = [
        {'id': 'video-interaction-1', 'status': 'queued'},
        output('video-interaction-1', 'video', VIDEO_BYTES, 'video/mp4'),
    ]
    first = client.post('/api/gemini/generate-segment', json=segment_request())
    assert first.status_code == 200
    assert first.json()['status'] == 'processing'
    assert first.json()['interaction_id'] == 'video-interaction-1'
    assert client.post('/api/gemini/generate-segment', json=segment_request()).json() == first.json()
    assert provider.await_count == 1
    body = provider.await_args_list[0].args[1]
    assert body['model'] == 'gemini-omni-1.2-flash'
    assert body['background'] is body['store'] is True
    assert base64.b64decode(body['input'][0]['data']) == (cache / 'img_test-house_first_fixture.jpg').read_bytes()
    assert base64.b64decode(body['input'][1]['data']) == (cache / 'img_test-house_last_fixture.jpg').read_bytes()
    assert client.get('/api/listings').json()['listings'][0]['transitions'][0]['status'] == 'processing'
    assert provider.await_count == 1

    ready = client.get('/api/gemini/poll/test-house_seg0')
    assert ready.status_code == 200
    assert ready.json()['status'] == 'ready'
    media = client.get(ready.json()['video_url'])
    assert media.status_code == 200
    assert media.headers['content-type'] == 'video/mp4'
    assert media.content == VIDEO_BYTES
    cached = client.post('/api/gemini/generate-segment', json=segment_request()).json()
    assert cached['status'] == 'ready' and cached['cached'] is True
    assert client.get('/api/gemini/poll/test-house_seg0').json()['status'] == 'ready'
    assert [call.args[0] for call in provider.await_args_list] == ['create', 'get']
    assert provider.await_args_list[1].args[1] == 'video-interaction-1'


def test_plan_queued_to_ready_is_cached_and_uses_flash(setup):
    client, provider, _ = setup
    plan = {'hook_strategy': 'Preserve supplied facts', 'compound_caption': 'Fixture home'}
    provider.side_effect = [
        {'id': 'plan-interaction-1', 'status': 'in_progress'},
        output('plan-interaction-1', 'text', json.dumps(plan)),
    ]
    payload = {'listing_id': 'test-house'}
    assert client.post('/api/gemini/plan-tour', json=payload).json()['status'] == 'processing'
    assert client.post('/api/gemini/plan-tour', json=payload).json()['interaction_id'] == 'plan-interaction-1'
    assert provider.await_count == 1
    assert provider.await_args_list[0].args[1]['model'] == 'gemini-3.8-flash'
    ready = client.get('/api/gemini/poll/plan_test-house').json()
    assert ready['status'] == 'ready'
    assert ready['plan'] == plan
    cached = client.post('/api/gemini/plan-tour', json=payload).json()
    assert cached['cached'] is True and cached['plan'] == plan
    assert provider.await_count == 2


def test_voiceover_queued_to_ready_serves_audio_and_never_resubmits(setup):
    client, provider, _ = setup
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b'\x00\x00' * 24)
    audio_bytes = stream.getvalue()
    provider.side_effect = [
        {'id': 'audio-interaction-1', 'status': 'queued'},
        output('audio-interaction-1', 'audio', audio_bytes, 'audio/wav'),
    ]
    payload = {'listing_id': 'test-house', 'text': 'Fixture property narration.'}
    assert client.post('/api/gemini/generate-voiceover', json=payload).json()['status'] == 'processing'
    client.post('/api/gemini/generate-voiceover', json=payload)
    assert provider.await_count == 1
    assert provider.await_args_list[0].args[1]['model'] == 'gemini-3.8-flash-tts'
    ready = client.get('/api/gemini/poll/vo_test-house').json()
    assert ready['status'] == 'ready'
    media = client.get(ready['audio_url'])
    assert media.headers['content-type'] == 'audio/wav'
    assert media.content == audio_bytes
    assert client.post('/api/gemini/generate-voiceover', json=payload).json()['cached'] is True
    assert provider.await_count == 2


@pytest.mark.parametrize('terminal', ['failed', 'cancelled', 'incomplete', 'requires_action'])
def test_terminal_video_status_never_polls_or_submits_again(setup, terminal):
    client, provider, _ = setup
    provider.side_effect = [
        {'id': 'terminal-interaction', 'status': 'queued'},
        {'id': 'terminal-interaction', 'status': terminal},
    ]
    client.post('/api/gemini/generate-segment', json=segment_request())
    terminal_response = client.get('/api/gemini/poll/test-house_seg0').json()
    assert terminal_response['status'] == terminal
    assert 'no automatic resubmission' in terminal_response['error'].lower()
    assert 'video_url' not in terminal_response
    assert client.get('/api/gemini/poll/test-house_seg0').json()['status'] == terminal
    assert client.post('/api/gemini/generate-segment', json=segment_request()).json()['status'] == terminal
    assert provider.await_count == 2


def test_historical_media_is_preserved_without_reading_a_key(setup):
    client, provider, cache = setup
    (cache / 'legacy.mp4').write_bytes(VIDEO_BYTES)
    server.save_cache_index({'segments': {'test-house_seg0': {
        'status': 'ready', 'model': 'veo-3.1-generate-001',
        'request_id': 'historical-job', 'local_file': 'legacy.mp4',
    }}})
    cached = client.post('/api/gemini/generate-segment', json=segment_request()).json()
    assert cached['cached'] is True
    assert cached['provider'] == 'gmi-cloud'
    assert cached['model'] == 'veo-3.1-generate-001'
    assert client.get(cached['video_url']).content == VIDEO_BYTES
    transition = client.get('/api/listings').json()['listings'][0]['transitions'][0]
    assert transition['provider'] == 'gmi-cloud'
    assert client.get('/api/gemini/poll/test-house_seg0').json()['status'] == 'ready'
    provider.assert_not_awaited()


@pytest.mark.parametrize('method,path', [
    ('POST', '/api/gmi/plan-tour'),
    ('POST', '/api/gmi/generate-segment'),
    ('POST', '/api/gmi/generate-voiceover'),
    ('GET', '/api/gmi/poll/test-house_seg0'),
])
def test_gmi_live_routes_are_removed(setup, method, path):
    client, provider, _ = setup
    assert client.request(method, path, json={}).status_code == 404
    provider.assert_not_awaited()


def test_unknown_listing_and_argon_video_choice_are_rejected_before_provider_access(setup):
    client, provider, _ = setup
    payload = {**segment_request(), 'listing_id': 'missing-house'}
    assert client.post('/api/gemini/generate-segment', json=payload).status_code == 404
    payload = {**segment_request(), 'model': 'gemini-4-argon'}
    assert client.post('/api/gemini/generate-segment', json=payload).status_code == 422
    payload = {**segment_request(), 'first_frame_url': 'https://unrelated.invalid/room.jpg'}
    assert client.post('/api/gemini/generate-segment', json=payload).status_code == 422
    assert client.get('/api/gemini/poll/not-a-job').status_code == 404
    provider.assert_not_awaited()


def test_uncertain_submission_is_not_retried(setup):
    client, provider, _ = setup
    provider.side_effect = HTTPException(503, 'Simulated service timeout')
    first = client.post('/api/gemini/generate-segment', json=segment_request())
    assert first.status_code == 503
    resumed = client.post('/api/gemini/generate-segment', json=segment_request()).json()
    assert resumed['status'] == 'submission_uncertain'
    assert client.get('/api/gemini/poll/test-house_seg0').status_code == 409
    provider.assert_awaited_once()


def test_explicit_compatible_video_model_is_forwarded_to_gemini(setup):
    client, provider, _ = setup
    provider.return_value = {'id': 'compatible-model', 'status': 'queued'}
    result = client.post('/api/gemini/generate-segment', json={**segment_request(), 'model': 'gemini-omni-1.1-flash'})
    assert result.status_code == 200
    assert result.json()['model'] == 'gemini-omni-1.1-flash'
    assert provider.await_args.args[1]['model'] == 'gemini-omni-1.1-flash'
