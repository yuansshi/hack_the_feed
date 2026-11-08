"""Direct Gemini Interactions API with explicitly scoped project credentials."""
import base64
import binascii
import os
import re
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent
API = 'https://generativelanguage.googleapis.com/v1beta'
VIDEO_MODEL = 'gemini-omni-1.2-flash'
TEXT_MODEL = 'gemini-3.8-flash'
TTS_MODEL = 'gemini-3.8-flash-tts'
VIDEO_MODELS = (VIDEO_MODEL, 'gemini-omni-1.1-flash')
MAX_MEDIA_BYTES = 200 * 1024 * 1024
PROJECT_KEY_NAMES = ('HOMI_GEMINI_API_KEY', 'PROJECT_GEMINI_API_KEY',
                     'GEMINI_API_KEY', 'GOOGLE_API_KEY')
TOKEN = re.compile(r'(?<![A-Za-z0-9._-])[A-Za-z0-9._-]{20,}(?![A-Za-z0-9._-])')


class GeminiError(RuntimeError):
    def __init__(self, message, status_code=None, outcome_unknown=False):
        super().__init__(message)
        self.status_code = status_code
        self.outcome_unknown = outcome_unknown


def _file_key(content):
    assignments = {}
    for line in content.splitlines():
        match = re.fullmatch(r'\s*(?:export\s+)?([A-Z_]+)\s*=\s*(.*?)\s*', line)
        if match and match[1] in PROJECT_KEY_NAMES:
            value = match[2].strip().strip('\"\'')
            if value:
                assignments.setdefault(match[1], set()).add(value)
    for name in PROJECT_KEY_NAMES:
        values = assignments.get(name, set())
        if len(values) > 1:
            raise GeminiError('Project Gemini credential file contains conflicting assignments.')
        if values:
            return values.pop()
    active = False
    labeled = set()
    nonempty = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('```'):
            continue
        nonempty.append(stripped)
        label = TOKEN.sub('', stripped)
        if re.search(r'gemini|google', label, re.I):
            active = True
        elif re.search(r'\bgmi\b|GMI_API_KEY|oriane|openai|anthropic', label, re.I):
            active = False
        elif stripped.startswith('#'):
            active = False
        if active:
            labeled.update(TOKEN.findall(stripped))
    if len(labeled) == 1:
        return labeled.pop()
    if len(labeled) > 1:
        raise GeminiError('Project file has multiple Gemini keys; use one explicit project assignment.')
    if len(nonempty) == 1:
        bare = nonempty[0].strip('`\"\'')
        if bare.startswith('AIza') and TOKEN.fullmatch(bare):
            return bare
    raise GeminiError('Configure one Gemini key in the designated project credential file.')


def load_project_key(credential_file=None):
    """Never consult generic ambient keys or personal credential stores."""
    if credential_file is not None:
        paths = [Path(credential_file)]
    else:
        key = os.environ.get('HOMI_GEMINI_API_KEY', '').strip()
        if key:
            return key
        paths = [BASE / 'api_key.md', BASE / '.env']
    for path in paths:
        try:
            content = path.read_text()
        except FileNotFoundError:
            continue
        except OSError:
            raise GeminiError('Cannot read the designated project Gemini credential file.') from None
        try:
            return _file_key(content)
        except GeminiError:
            if credential_file is not None:
                raise
    raise GeminiError('Configure HOMI_GEMINI_API_KEY or a Gemini key in this project’s api_key.md/.env.')


class GeminiClient:
    def __init__(self, key, client=None):
        if not isinstance(key, str) or not key.strip():
            raise GeminiError('A designated project Gemini credential is required.')
        self._key = key.strip()
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=60)

    def close(self):
        if self._owns_client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _request(self, method, path, body=None):
        try:
            response = self._client.request(method, API + path,
                headers={'x-goog-api-key': self._key, 'Api-Revision': '2026-05-20'},
                json=body, timeout=60, follow_redirects=False)
        except httpx.HTTPError:
            raise GeminiError('Gemini connection failed; reconcile the existing interaction before resubmitting.'
                              if method == 'POST' else 'Gemini connection failed; polling can be resumed.',
                              outcome_unknown=method == 'POST') from None
        if response.status_code < 200 or response.status_code >= 300:
            raise GeminiError(f'Gemini API returned HTTP {response.status_code}.', response.status_code)
        try:
            result = response.json()
        except ValueError:
            raise GeminiError('Gemini returned an unreadable response.',
                              outcome_unknown=method == 'POST') from None
        if not isinstance(result, dict):
            raise GeminiError('Gemini returned an invalid response shape.',
                              outcome_unknown=method == 'POST')
        return result

    def create(self, body):
        return self._request('POST', '/interactions', body)

    def get(self, interaction_id):
        if not isinstance(interaction_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,512}', interaction_id):
            raise GeminiError('A valid saved Gemini interaction ID is required.')
        return self._request('GET', '/interactions/' + interaction_id)

    def models(self):
        return self._request('GET', '/models')


def image_part(content, mime='image/jpeg'):
    if mime not in ('image/jpeg', 'image/png', 'image/webp') or not isinstance(content, bytes) or not content:
        raise GeminiError('Provide nonempty JPEG, PNG or WebP image bytes.')
    return {'type': 'image', 'mime_type': mime, 'data': base64.b64encode(content).decode('ascii')}


def video_request(prompt, first_bytes, last_bytes, model=VIDEO_MODEL,
                  duration=6, resolution='720p', aspect_ratio='16:9'):
    if model not in VIDEO_MODELS:
        raise GeminiError('Select a supported Gemini Omni video model.')
    if type(duration) is not int or not 3 <= duration <= 10:
        raise GeminiError('First/last-frame videos require an integer duration from 3 to 10 seconds.')
    if resolution not in ('360p', '720p', '1080p', '4k') or aspect_ratio not in ('16:9', '9:16'):
        raise GeminiError('Unsupported Gemini video resolution or aspect ratio.')
    if not isinstance(prompt, str) or not prompt.strip():
        raise GeminiError('A video motion prompt is required.')
    return {'model': model, 'input': [image_part(first_bytes), image_part(last_bytes),
                                    {'type': 'text', 'text': prompt}],
            'response_format': {'type': 'video', 'aspect_ratio': aspect_ratio,
                                'resolution': resolution, 'duration': f'{duration}s'},
            'background': True, 'store': True}


def _output_parts(interaction):
    for step in interaction.get('steps', []):
        if isinstance(step, dict) and step.get('type') == 'model_output':
            for part in step.get('content', []):
                if isinstance(part, dict):
                    yield part


def output_text(interaction):
    return ''.join(part.get('text', '') for part in _output_parts(interaction)
                   if part.get('type') == 'text' and isinstance(part.get('text', ''), str))


def failure_details(interaction):
    """Expose recognized failure codes without echoing arbitrary provider content."""
    messages = {
        'RESOURCE_EXHAUSTED': 'Gemini quota or capacity is exhausted. Check project usage, quota and billing before retrying.',
        'PERMISSION_DENIED': 'The project does not have permission to generate with this model.',
        'INVALID_ARGUMENT': 'Gemini rejected the generation parameters.',
        'UNAVAILABLE': 'The Gemini generation service is temporarily unavailable.',
        'INTERNAL': 'Gemini could not finish this generation because of an internal service error.',
        'FAILED_PRECONDITION': 'The Gemini project does not meet this generation request’s prerequisites.',
        'DEADLINE_EXCEEDED': 'Gemini generation exceeded its service deadline.',
    }
    errors = interaction.get('errors', [])
    if isinstance(errors, list):
        for error in errors:
            code = error.get('code') if isinstance(error, dict) else None
            if code in messages:
                return code, messages[code] + ' No automatic resubmission was started.'
    return 'GENERATION_FAILED', 'Gemini did not complete the generation. No automatic resubmission was started.'


def _media_bytes(part):
    data = part.get('data')
    if not isinstance(data, str) or not data or len(data) > ((MAX_MEDIA_BYTES + 2) // 3) * 4:
        raise GeminiError('Gemini output media is missing or exceeds the 200 MiB bound.')
    try:
        content = base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error):
        raise GeminiError('Gemini output media has invalid base64 encoding.') from None
    if not content or len(content) > MAX_MEDIA_BYTES:
        raise GeminiError('Gemini output media is empty or exceeds the 200 MiB bound.')
    return content


def output_video_bytes(interaction):
    for part in _output_parts(interaction):
        if part.get('type') == 'video':
            content = _media_bytes(part)
            if part.get('mime_type') != 'video/mp4' or len(content) < 12 or content[4:8] != b'ftyp':
                raise GeminiError('Gemini output is not an MP4 video.')
            return content
    return None


def output_audio_bytes(interaction):
    for part in _output_parts(interaction):
        if part.get('type') == 'audio':
            mime = part.get('mime_type')
            if not isinstance(mime, str) or not mime.startswith('audio/'):
                raise GeminiError('Gemini output is not supported audio.')
            return _media_bytes(part), mime
    return None
