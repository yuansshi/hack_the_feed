"""Finite source-grounded video jobs. Generated outputs always require visual review."""
import fcntl
import hashlib
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx

BASE = Path(__file__).resolve().parent
TOURS = BASE / 'data' / '94404'
QUEUE = 'https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/requests'
MODEL = 'veo-3.1-generate-001'


def digest(content):
    return hashlib.sha256(content).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def prepare(plan_path, tours=TOURS):
    plan = json.loads(Path(plan_path).read_text())
    manifest = json.loads((tours / 'manifest.json').read_text())
    listing = next(row for row in manifest['listings'] if row['id'] == plan['listing_id'])
    if plan['model'] != MODEL or plan['duration_seconds'] not in (4, 6, 8):
        raise ValueError('This bounded pilot supports Veo 3.1 and 4/6/8 seconds only.')
    if plan['first_photo_index'] == plan['last_photo_index']:
        raise ValueError('A continuous camera pilot needs two distinct source views.')
    if plan['floor_plan_index'] != (listing.get('model') or {}).get('floor_plan_index'):
        raise ValueError('A retrieved floor plan must ground this pilot.')
    indices = list(dict.fromkeys([plan['first_photo_index'], plan['last_photo_index'],
                                plan['floor_plan_index'], *plan['support_photo_indices']]))
    records = []
    for index in indices:
        record = next(photo for photo in listing['photos'] if photo['index'] == index)
        path = (tours / record['path']).resolve()
        if not path.is_relative_to((tours / 'assets').resolve()):
            raise ValueError('Source asset is outside the original-image directory.')
        if digest(path.read_bytes()) != record['sha256']:
            raise ValueError(f'Source integrity mismatch for photo {index}.')
        url = urlparse(record['source_url'])
        if url.scheme != 'https' or url.hostname != 'ssl.cdn-redfin.com':
            raise ValueError('Pilot inputs must be observed original Redfin image URLs.')
        records.append(record)
    photos = {record['index']: record for record in records}
    if len(plan['prompt']) > 2000 or len(plan['negative_prompt']) > 500:
        raise ValueError('Prompt exceeds the documented provider limits.')
    request = {'model': MODEL, 'payload': {
        'prompt': plan['prompt'],
        'image': photos[plan['first_photo_index']]['source_url'],
        'lastFrame': photos[plan['last_photo_index']]['source_url'],
        'durationSeconds': plan['duration_seconds'],
        'aspectRatio': plan['aspect_ratio'],
        'resolution': plan['resolution'],
        'generateAudio': False, 'personGeneration': 'disallow',
        'negativePrompt': plan['negative_prompt'], 'seed': 94404,
    }}
    provenance = {'listing_id': listing['id'], 'address': listing['address'],
                  'listing_url': listing['redfin_url'], 'sources': records,
                  'scope': plan['scope'], 'conditioning': plan['conditioning']}
    fingerprint = digest(json.dumps({'plan': plan, 'provenance': provenance,
                                    'request': request}, sort_keys=True).encode())[:20]
    job = tours / 'video_jobs' / fingerprint
    job.mkdir(parents=True, exist_ok=True)
    # Content-addressed inputs are immutable across resume attempts.
    with job_lock(job):
        for filename, value in [('plan.json', plan), ('request.json', request),
                                ('provenance.json', provenance)]:
            path = job / filename
            if path.exists() and json.loads(path.read_text()) != value:
                raise ValueError('Prepared job inputs changed; create a fresh job.')
            write_json(path, value)
    return job


@contextmanager
def job_lock(job):
    with (job / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def credential(credential_file=None):
    # Deliberately never inspect generic GMI_API_KEY or personal credential stores.
    if credential_file:
        for line in Path(credential_file).read_text().splitlines():
            name, separator, value = line.strip().partition('=')
            if separator and name == 'HOMI_GMI_API_KEY':
                key = value.strip().strip('\"\'')
                if key:
                    return key
        raise ValueError('Project file must define HOMI_GMI_API_KEY.')
    key = os.environ.get('HOMI_GMI_API_KEY', '').strip()
    if not key:
        raise ValueError('Configure the project HOMI_GMI_API_KEY or pass --credential-file; no personal key is read.')
    return key


def submit(job, key, client):
    """At most one POST per job, including ambiguous network failures."""
    with job_lock(job):
        state_path = job / 'state.json'
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state.get('request_id'):
                return state
            raise ValueError('A submission was already attempted. Reconcile its provider request ID before proceeding; automatic retry is disabled.')
        request = json.loads((job / 'request.json').read_text())
        sources = json.loads((job / 'provenance.json').read_text())['sources']
        for field in ('image', 'lastFrame'):
            url = request['payload'][field]
            expected = next(source['sha256'] for source in sources if source['source_url'] == url)
            original = client.get(url, timeout=30, follow_redirects=False)
            if original.status_code != 200 or digest(original.content) != expected:
                raise ValueError('Provider input URL is unavailable or changed from the acquired original. No generation was submitted.')
        write_json(state_path, {'status': 'submission_pending_reconciliation',
                                'attempted_at': time.time(), 'automatic_retry': False})
        try:
            response = client.post(QUEUE, headers={'Authorization': f'Bearer {key}'},
                                   json=request, timeout=45)
        except httpx.HTTPError:
            raise RuntimeError('Submission outcome unknown. Check the GMI dashboard; do not resubmit this job.') from None
        if response.status_code not in (200, 201, 202):
            raise RuntimeError(f'GMI submission HTTP {response.status_code}; no retry or alternate model was started.')
        result = response.json()
        request_id = result.get('request_id') or result.get('id')
        if not isinstance(request_id, str) or not request_id or '/' in request_id:
            raise RuntimeError('GMI response lacked a valid request ID. Reconcile in its dashboard; do not resubmit.')
        state = {'status': 'queued', 'request_id': request_id, 'submitted_at': time.time(),
                 'automatic_retry': False}
        write_json(state_path, state)
        return state


def poll(job, key, client):
    """Poll once, download once on success. Never starts a generation."""
    with job_lock(job):
        state_path = job / 'state.json'
        state = json.loads(state_path.read_text())
        if state.get('status') in ('generated_unreviewed', 'failed', 'cancelled'):
            return state
        request_id = state.get('request_id')
        if not isinstance(request_id, str) or not request_id or '/' in request_id:
            raise ValueError('No valid request ID to poll.')
        response = client.get(f'{QUEUE}/{request_id}', headers={'Authorization': f'Bearer {key}'}, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f'GMI poll HTTP {response.status_code}.')
        result = response.json()
        status = result.get('status')
        state['status'] = status if status in ('failed', 'cancelled') else 'processing'
        if status in ('success', 'finished', 'succeeded', 'completed'):
            url = (result.get('outcome') or {}).get('video_url')
            parsed = urlparse(url or '')
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise RuntimeError('GMI completed without a valid HTTPS video URL.')
            target = job / 'generated.mp4'
            temporary = target.with_suffix('.download')
            try:
                with client.stream('GET', url, timeout=90, follow_redirects=False) as download:
                    if download.status_code != 200:
                        raise RuntimeError(f'Video download HTTP {download.status_code}.')
                    total = 0
                    with temporary.open('wb') as output:
                        for chunk in download.iter_bytes():
                            total += len(chunk)
                            if total > 200 * 1024 * 1024:
                                raise RuntimeError('Generated pilot exceeded the 200 MiB download bound.')
                            output.write(chunk)
                if total < 1000:
                    raise RuntimeError('Generated media is empty or invalid.')
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            state.update(status='generated_unreviewed', sha256=digest(target.read_bytes()),
                         local_video=str(target.relative_to(TOURS)) if target.is_relative_to(TOURS) else str(target),
                         generated_at=time.time())
        write_json(state_path, state)
        return state
