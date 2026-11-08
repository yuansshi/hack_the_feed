import base64
import json

import httpx
import pytest

import gemini_provider
import grounded_video as video

MP4 = b'\x00\x00\x00\x18ftypisom' + b'generated test fixture only'


def completed():
    return {'id': 'v1_test', 'status': 'completed', 'steps': [
        {'type': 'model_output', 'content': [
            {'type': 'video', 'mime_type': 'video/mp4', 'data': base64.b64encode(MP4).decode()},
        ]},
    ]}


@pytest.fixture
def job(tmp_path):
    tours = tmp_path / 'tours'
    (tours / 'assets').mkdir(parents=True)
    photos = []
    for index in (0, 1, 2, 3):
        content = f'original {index}'.encode()
        path = f'assets/property-{index}.jpg'
        (tours / path).write_bytes(content)
        photos.append({'index': index, 'path': path, 'sha256': video.digest(content),
                       'source_url': f'https://ssl.cdn-redfin.com/photo/{index}.jpg'})
    listing = {'id': 'test-house', 'address': 'Test house', 'redfin_url': 'https://www.redfin.com/home/1',
               'photos': photos, 'model': {'floor_plan_index': 2}}
    (tours / 'manifest.json').write_text(json.dumps({'listings': [listing]}))
    plan = {'id': 'pilot', 'listing_id': 'test-house', 'model': video.MODEL,
            'duration_seconds': 6, 'first_photo_index': 0, 'last_photo_index': 1,
            'floor_plan_index': 2, 'support_photo_indices': [3], 'prompt': 'Continuous camera move',
            'negative_prompt': 'no cuts', 'aspect_ratio': '16:9', 'resolution': '720p',
            'scope': 'single room', 'conditioning': {'floor_plan': 'route and review reference'}}
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(plan))
    return video.prepare(plan_path, tours), tours, plan_path


def test_prepare_is_offline_source_grounded_and_repeatable(job):
    path, tours, plan = job
    assert video.prepare(plan, tours) == path
    request = json.loads((path / 'request.json').read_text())
    assert request['provider'] == 'gemini'
    assert request['model'] == 'gemini-omni-1.2-flash'
    assert request['image_indices'] == [0, 1]
    assert request['duration_seconds'] == 6
    assert 'first input image is the first frame' in request['prompt']
    assert not (path / 'state.json').exists()
    assert len(json.loads((path / 'provenance.json').read_text())['sources']) == 4


def test_modified_source_blocks_preparation(job):
    _, tours, plan = job
    (tours / 'assets/property-0.jpg').write_bytes(b'changed')
    with pytest.raises(ValueError, match='integrity mismatch'):
        video.prepare(plan, tours)


def test_submit_uploads_exact_images_and_resumes_without_spending_again(job):
    path, _, _ = job
    requests = []
    def transport(request):
        requests.append(request)
        assert request.method == 'POST'
        assert request.url.host == 'generativelanguage.googleapis.com'
        assert not request.url.query
        body = json.loads(request.content)
        assert body['model'] == video.MODEL
        assert [base64.b64decode(part['data']) for part in body['input'][:2]] == [b'original 0', b'original 1']
        assert body['response_format']['duration'] == '6s'
        return httpx.Response(200, json={'id': 'v1_test', 'status': 'queued'})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        state = video.submit(path, 'project-test-placeholder', client)
        assert state['interaction_id'] == 'v1_test'
        assert state['provider'] == 'gemini'
        assert video.submit(path, 'project-test-placeholder', client) == state
    assert len(requests) == 1


def test_ambiguous_submission_never_retries(job):
    path, _, _ = job
    calls = []
    def transport(request):
        calls.append(request)
        raise httpx.ReadTimeout('simulated timeout')
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(video.GeminiError) as caught:
            video.submit(path, 'project-test-placeholder', client)
        assert caught.value.outcome_unknown is True
        with pytest.raises(ValueError, match='already attempted'):
            video.submit(path, 'project-test-placeholder', client)
    assert len(calls) == 1
    assert json.loads((path / 'state.json').read_text())['status'] == 'submission_pending_reconciliation'


def test_changed_support_reference_blocks_spending_before_post(job):
    path, tours, _ = job
    (tours / 'assets/property-3.jpg').write_bytes(b'changed support view')
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail('No API call allowed'))) as client:
        with pytest.raises(ValueError, match='integrity mismatch'):
            video.submit(path, 'project-test-placeholder', client)
    assert not (path / 'state.json').exists()


def test_billing_rejection_is_recorded_without_automatic_retry(job):
    path, _, _ = job
    posts = []
    def transport(request):
        posts.append(request)
        return httpx.Response(402, json={'detail': 'Simulated billing rejection'})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(video.GeminiError, match='HTTP 402'):
            video.submit(path, 'project-test-placeholder', client)
        with pytest.raises(ValueError, match='already attempted'):
            video.submit(path, 'project-test-placeholder', client)
    state = json.loads((path / 'state.json').read_text())
    assert state['status'] == 'submission_rejected'
    assert state['http_status'] == 402
    assert state['automatic_retry'] is False
    assert len(posts) == 1


def test_poll_decodes_inline_mp4_without_download_or_new_generation(job):
    path, _, _ = job
    video.write_json(path / 'state.json', {'provider': 'gemini', 'model': video.MODEL,
                                          'status': 'queued', 'interaction_id': 'v1_test'})
    requests = []
    def transport(request):
        requests.append(request)
        assert request.method == 'GET'
        assert request.url.host == 'generativelanguage.googleapis.com'
        assert request.url.path.endswith('/interactions/v1_test')
        return httpx.Response(200, json=completed())
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        state = video.poll(path, 'project-test-placeholder', client)
        assert state['status'] == 'generated_unreviewed'
        assert state['sha256'] == video.digest(MP4)
        assert (path / 'generated.mp4').read_bytes() == MP4
        assert video.poll(path, 'project-test-placeholder', client) == state
    assert len(requests) == 1
    assert not (path.parent.parent / 'generated_videos.json').exists()


def test_immediate_completion_keeps_id_and_is_not_accepted(job):
    path, _, _ = job
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=completed()))) as client:
        state = video.submit(path, 'project-test-placeholder', client)
    assert state['interaction_id'] == 'v1_test'
    assert state['status'] == 'generated_unreviewed'
    assert not (path.parent.parent / 'generated_videos.json').exists()


def test_background_quota_failure_is_actionable_and_never_retried(job):
    path, _, _ = job
    video.write_json(path / 'state.json', {'provider': 'gemini', 'status': 'processing', 'interaction_id': 'v1_test'})
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={'id': 'v1_test', 'status': 'failed',
            'errors': [{'code': 'RESOURCE_EXHAUSTED', 'message': 'Do not echo this arbitrary service content'}]})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result = video.poll(path, 'project-test-placeholder', client)
        assert result['failure_code'] == 'RESOURCE_EXHAUSTED'
        assert 'billing' in result['failure_message']
        assert 'arbitrary service content' not in result['failure_message']
        assert video.poll(path, 'project-test-placeholder', client) == result
    assert len(calls) == 1


@pytest.mark.parametrize('status', ['failed', 'cancelled', 'incomplete', 'requires_action'])
def test_terminal_provider_state_does_not_poll_again(job, status):
    path, _, _ = job
    video.write_json(path / 'state.json', {'provider': 'gemini', 'status': 'processing', 'interaction_id': 'v1_test'})
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={'id': 'v1_test', 'status': status})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        state = video.poll(path, 'project-test-placeholder', client)
        assert state['status'] == status
        assert video.poll(path, 'project-test-placeholder', client) == state
    assert len(calls) == 1


def test_completed_without_video_is_an_explicit_failure(job):
    path, _, _ = job
    result = {'id': 'v1_test', 'status': 'completed', 'steps': []}
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=result))) as client:
        state = video.submit(path, 'project-test-placeholder', client)
        assert state['status'] == 'failed'
        assert state['failure'] == 'completed_without_video'
        assert video.poll(path, 'project-test-placeholder', client) == state
    assert not (path / 'generated.mp4').exists()


def test_historical_provider_ids_are_never_sent_to_gemini(job):
    path, _, _ = job
    video.write_json(path / 'state.json', {'provider': 'legacy', 'status': 'queued', 'request_id': 'old-id'})
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail('No API call allowed'))) as client:
        with pytest.raises(ValueError, match='another provider'):
            video.poll(path, 'project-test-placeholder', client)
        with pytest.raises(ValueError, match='another provider'):
            video.submit(path, 'project-test-placeholder', client)


def test_missing_submission_id_cannot_cause_duplicate_post(job):
    path, _, _ = job
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={'status': 'queued'})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(RuntimeError, match='valid interaction ID'):
            video.submit(path, 'project-test-placeholder', client)
        with pytest.raises(ValueError, match='already attempted'):
            video.submit(path, 'project-test-placeholder', client)
    assert len(calls) == 1


def test_credential_alias_reads_only_scoped_configuration(monkeypatch, tmp_path):
    monkeypatch.setattr(gemini_provider, 'BASE', tmp_path)
    def project_only(name, default=None):
        assert name == 'HOMI_GEMINI_API_KEY'
        return default
    monkeypatch.setattr(gemini_provider.os.environ, 'get', project_only)
    with pytest.raises(video.GeminiError, match='Configure HOMI_GEMINI_API_KEY'):
        video.credential()


def test_explicit_compatible_omni_model_gets_separate_job(job):
    original, tours, plan_path = job
    plan = json.loads(plan_path.read_text())
    plan['model'] = 'gemini-omni-1.1-flash'
    plan_path.write_text(json.dumps(plan))
    alternative = video.prepare(plan_path, tours)
    assert alternative != original
    assert json.loads((alternative / 'request.json').read_text())['model'] == 'gemini-omni-1.1-flash'
