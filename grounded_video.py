"""Finite source-grounded Gemini video jobs; every generated output needs review."""
import fcntl
import hashlib
import json
import re
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from gemini_provider import (
    VIDEO_MODEL as MODEL, VIDEO_MODELS, GeminiClient, GeminiError,
    load_project_key as credential, output_video_bytes, video_request, failure_details,
)

BASE = Path(__file__).resolve().parent
TOURS = BASE / 'data' / '94404'
TERMINAL = {'generated_unreviewed', 'failed', 'cancelled', 'incomplete',
            'requires_action', 'submission_rejected'}


def digest(content):
    return hashlib.sha256(content).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


@contextmanager
def job_lock(job):
    with (job / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _source_bytes(tours, record):
    path = (tours / record['path']).resolve()
    if not path.is_relative_to((tours / 'assets').resolve()):
        raise ValueError('Source asset is outside the original-image directory.')
    content = path.read_bytes()
    if digest(content) != record['sha256']:
        raise ValueError(f"Source integrity mismatch for photo {record['index']}.")
    return content


def prepare(plan_path, tours=TOURS):
    plan = json.loads(Path(plan_path).read_text())
    manifest = json.loads((tours / 'manifest.json').read_text())
    listing = next(row for row in manifest['listings'] if row['id'] == plan['listing_id'])
    if plan['model'] not in VIDEO_MODELS or type(plan['duration_seconds']) is not int or not 3 <= plan['duration_seconds'] <= 10:
        raise ValueError('This bounded pilot needs a supported Gemini Omni model and a 3–10 second first/last-frame shot.')
    if plan['first_photo_index'] == plan['last_photo_index']:
        raise ValueError('A continuous camera pilot needs two distinct source views.')
    if plan['floor_plan_index'] != (listing.get('model') or {}).get('floor_plan_index'):
        raise ValueError('A retrieved floor plan must ground this pilot.')
    indices = list(dict.fromkeys([plan['first_photo_index'], plan['last_photo_index'],
                                plan['floor_plan_index'], *plan['support_photo_indices']]))
    records = []
    for index in indices:
        record = next(photo for photo in listing['photos'] if photo['index'] == index)
        _source_bytes(tours, record)
        url = urlparse(record['source_url'])
        if url.scheme != 'https' or url.hostname != 'ssl.cdn-redfin.com':
            raise ValueError('Pilot references must retain observed original Redfin image provenance.')
        records.append(record)
    request = {
        'provider': 'gemini', 'model': plan['model'],
        'prompt': plan['prompt'] + '\nThe first input image is the first frame; the second input image is the last frame.'
                  + '\nAvoid: ' + plan['negative_prompt'],
        'image_indices': [plan['first_photo_index'], plan['last_photo_index']],
        'duration_seconds': plan['duration_seconds'], 'resolution': plan['resolution'],
        'aspect_ratio': plan['aspect_ratio'],
    }
    provenance = {'provider': 'gemini', 'listing_id': listing['id'], 'address': listing['address'],
                  'listing_url': listing['redfin_url'], 'sources': records,
                  'scope': plan['scope'], 'conditioning': plan['conditioning']}
    fingerprint = digest(json.dumps({'plan': plan, 'provenance': provenance,
                                    'request': request}, sort_keys=True).encode())[:20]
    job = tours / 'video_jobs' / fingerprint
    job.mkdir(parents=True, exist_ok=True)
    with job_lock(job):
        for filename, value in [('plan.json', plan), ('request.json', request),
                                ('provenance.json', provenance)]:
            path = job / filename
            if path.exists() and json.loads(path.read_text()) != value:
                raise ValueError('Prepared job inputs changed; create a fresh job.')
            write_json(path, value)
    return job


def _check_provider(state):
    if state.get('provider') != 'gemini':
        raise ValueError('Saved state is from another provider; do not poll it through Gemini.')


def _save_result(job, state, result):
    status = result.get('status')
    state['provider_status'] = status
    if status == 'completed':
        try:
            content = output_video_bytes(result)
        except GeminiError:
            state.update(status='failed', failure='invalid_video_output')
            write_json(job / 'state.json', state)
            raise
        if content is None:
            state.update(status='failed', failure='completed_without_video')
        else:
            target = job / 'generated.mp4'
            temporary = target.with_suffix('.download')
            temporary.write_bytes(content)
            temporary.replace(target)
            state.update(status='generated_unreviewed', sha256=digest(content),
                         local_video=str(target.relative_to(job.parent.parent)),
                         generated_at=time.time())
    elif status in ('queued', 'in_progress'):
        state['status'] = 'queued' if status == 'queued' else 'processing'
    elif status in ('failed', 'cancelled', 'incomplete', 'requires_action'):
        state['status'] = status
        if status == 'failed':
            state['failure_code'], state['failure_message'] = failure_details(result)
    else:
        state.update(status='failed', failure='unknown_provider_status')
    write_json(job / 'state.json', state)
    return state


def submit(job, key, client):
    """Submit once, uploading the exact verified endpoint image bytes inline."""
    with job_lock(job):
        state_path = job / 'state.json'
        if state_path.exists():
            state = json.loads(state_path.read_text())
            _check_provider(state)
            if state.get('interaction_id'):
                return state
            raise ValueError('A submission was already attempted. Reconcile its interaction ID before proceeding; automatic retry is disabled.')
        request = json.loads((job / 'request.json').read_text())
        if request.get('provider') != 'gemini' or request.get('model') not in VIDEO_MODELS:
            raise ValueError('Prepare a new Gemini pilot instead of submitting a historical provider request.')
        sources = json.loads((job / 'provenance.json').read_text())['sources']
        contents = {source['index']: _source_bytes(job.parent.parent, source) for source in sources}
        first, last = request['image_indices']
        body = video_request(request['prompt'], contents[first], contents[last], model=request['model'],
                             duration=request['duration_seconds'], resolution=request['resolution'],
                             aspect_ratio=request['aspect_ratio'])
        pending = {'provider': 'gemini', 'model': request['model'],
                   'status': 'submission_pending_reconciliation', 'attempted_at': time.time(),
                   'automatic_retry': False}
        write_json(state_path, pending)
        try:
            result = GeminiClient(key, client).create(body)
        except GeminiError as error:
            if not error.outcome_unknown:
                write_json(state_path, {**pending, 'status': 'submission_rejected',
                                        'http_status': error.status_code, 'rejected_at': time.time()})
            raise
        interaction_id = result.get('id')
        if not isinstance(interaction_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,512}', interaction_id):
            raise RuntimeError('Gemini response lacked a valid interaction ID. Reconcile the submission before retrying.')
        state = {**pending, 'status': 'queued', 'interaction_id': interaction_id,
                 'submitted_at': time.time()}
        write_json(state_path, state)
        return _save_result(job, state, result)


def poll(job, key, client):
    """Resume one saved Gemini interaction; never submit another generation."""
    with job_lock(job):
        state = json.loads((job / 'state.json').read_text())
        _check_provider(state)
        if state.get('status') in TERMINAL:
            return state
        interaction_id = state.get('interaction_id')
        if not interaction_id:
            raise ValueError('No saved Gemini interaction ID to poll; reconcile the attempted submission.')
        return _save_result(job, state, GeminiClient(key, client).get(interaction_id))
