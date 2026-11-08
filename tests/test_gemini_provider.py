import base64

import httpx
import pytest

import gemini_provider as gemini

FAKE_GEMINI = 'AIza-project-gemini-test-placeholder-12345'
FAKE_GMI = 'gmi-project-test-placeholder-123456789'
MP4 = b'\x00\x00\x00\x18ftypisom' + b'fixture-only'


@pytest.mark.parametrize('content', [
    f'Gemini API key\n{FAKE_GEMINI}\nGMI API key\n{FAKE_GMI}',
    f'GMI API key\n{FAKE_GMI}\n\n## Gemini API key\n```\n{FAKE_GEMINI}\n```',
    f'GMI_API_KEY={FAKE_GMI}\nGEMINI_API_KEY="{FAKE_GEMINI}"',
    f'export HOMI_GEMINI_API_KEY={FAKE_GEMINI}',
    f'PROJECT_GEMINI_API_KEY={FAKE_GEMINI}',
    f'GOOGLE_API_KEY={FAKE_GEMINI}',
    f'Gemini_API_KEY={FAKE_GEMINI}\nGMI_API_KEY={FAKE_GMI}',
    FAKE_GEMINI,
])
def test_explicit_file_reads_only_the_project_gemini_key(tmp_path, content):
    path = tmp_path / 'project-key.md'
    path.write_text(content)
    assert gemini.load_project_key(path) == FAKE_GEMINI


@pytest.mark.parametrize('content', [
    f'GMI API key\n{FAKE_GMI}',
    f'GMI_API_KEY={FAKE_GMI}',
    f'Gemini API keys\n{FAKE_GEMINI}\nAIza-second-test-project-placeholder-54321',
    f'GMI_API_KEY={FAKE_GEMINI}',
    FAKE_GMI,
])
def test_ambiguous_or_other_provider_key_is_not_used(tmp_path, content):
    path = tmp_path / 'project-key.md'
    path.write_text(content)
    with pytest.raises(gemini.GeminiError):
        gemini.load_project_key(path)


def test_no_personal_environment_or_store_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(gemini, 'BASE', tmp_path)
    requested = []

    def project_only(name, default=None):
        requested.append(name)
        assert name == 'HOMI_GEMINI_API_KEY'
        return default

    monkeypatch.setattr(gemini.os.environ, 'get', project_only)
    with pytest.raises(gemini.GeminiError, match='Configure HOMI_GEMINI_API_KEY'):
        gemini.load_project_key()
    assert requested == ['HOMI_GEMINI_API_KEY']


def test_labeled_dotted_credential_is_preserved_whole(tmp_path):
    path = tmp_path / 'project-key.md'
    dotted = 'project-placeholder-longsegment-0000.short.signature'
    path.write_text('Gemini API key\n' + dotted)
    assert gemini.load_project_key(path) == dotted


def test_non_argon_video_request_preserves_two_source_images():
    request = gemini.video_request('Continuous camera arc, no dissolves.', b'first image', b'last image')
    assert request['model'] == 'gemini-omni-1.2-flash'
    assert request['response_format'] == {'type': 'video', 'aspect_ratio': '16:9',
                                          'resolution': '720p', 'duration': '6s'}
    assert request['background'] is request['store'] is True
    assert [base64.b64decode(part['data']) for part in request['input'][:2]] == [b'first image', b'last image']
    assert request['input'][2]['text'] == 'Continuous camera arc, no dissolves.'
    with pytest.raises(gemini.GeminiError, match='Omni video'):
        gemini.video_request('test', b'first', b'last', model='gemini-4-argon')
    for duration in (2, 11, True, 6.5):
        with pytest.raises(gemini.GeminiError, match='3 to 10'):
            gemini.video_request('test', b'first', b'last', duration=duration)


def test_rest_auth_is_header_only_and_requests_do_not_retry():
    requests = []

    def transport(request):
        requests.append(request)
        assert request.url.host == 'generativelanguage.googleapis.com'
        assert not request.url.query
        assert request.headers['x-goog-api-key'] == FAKE_GEMINI
        assert request.headers['Api-Revision'] == '2026-05-20'
        return httpx.Response(200, json={'id': 'v1_test', 'status': 'queued'})

    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        with gemini.GeminiClient(FAKE_GEMINI, http) as client:
            assert client.create({'model': gemini.VIDEO_MODEL})['id'] == 'v1_test'
            assert client.get('v1_test')['status'] == 'queued'
            client.models()
        assert http.is_closed is False
    assert [request.method for request in requests] == ['POST', 'GET', 'GET']


def test_http_errors_never_echo_provider_body_or_key():
    def transport(request):
        return httpx.Response(429, json={'error': {'message': FAKE_GEMINI}})

    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        client = gemini.GeminiClient(FAKE_GEMINI, http)
        with pytest.raises(gemini.GeminiError) as caught:
            client.create({})
    assert caught.value.status_code == 429
    assert caught.value.outcome_unknown is False
    assert str(caught.value) == 'Gemini API returned HTTP 429.'


def test_network_submission_error_remains_unknown_without_retry():
    requests = []

    def transport(request):
        requests.append(request)
        raise httpx.ReadTimeout('Provider echoed ' + FAKE_GEMINI)

    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        client = gemini.GeminiClient(FAKE_GEMINI, http)
        with pytest.raises(gemini.GeminiError) as caught:
            client.create({})
    assert caught.value.outcome_unknown is True
    assert FAKE_GEMINI not in str(caught.value)
    assert len(requests) == 1


def test_all_model_output_steps_are_collected_and_video_is_decoded():
    interaction = {'steps': [
        {'type': 'user_input', 'content': [{'type': 'text', 'text': 'Do not return this'}]},
        {'type': 'model_output', 'content': [{'type': 'text', 'text': 'first '}]},
        {'type': 'model_output', 'content': [
            {'type': 'text', 'text': 'second'},
            {'type': 'video', 'mime_type': 'video/mp4', 'data': base64.b64encode(MP4).decode()},
        ]},
    ]}
    assert gemini.output_text(interaction) == 'first second'
    assert gemini.output_video_bytes(interaction) == MP4
    assert gemini.output_audio_bytes(interaction) is None


def test_pending_or_invalid_media_cannot_become_a_video():
    assert gemini.output_video_bytes({'status': 'in_progress'}) is None
    invalid = {'steps': [{'type': 'model_output', 'content': [
        {'type': 'video', 'mime_type': 'video/mp4', 'data': base64.b64encode(b'not an MP4').decode()},
    ]}]}
    with pytest.raises(gemini.GeminiError, match='not an MP4'):
        gemini.output_video_bytes(invalid)
    invalid['steps'][0]['content'][0]['data'] = 'invalid:base64!'
    with pytest.raises(gemini.GeminiError, match='invalid base64'):
        gemini.output_video_bytes(invalid)


def test_audio_data_and_mime_are_preserved():
    content = b'RIFF audio fixture'
    interaction = {'steps': [{'type': 'model_output', 'content': [
        {'type': 'audio', 'mime_type': 'audio/wav', 'data': base64.b64encode(content).decode()},
    ]}]}
    assert gemini.output_audio_bytes(interaction) == (content, 'audio/wav')
