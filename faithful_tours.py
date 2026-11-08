"""Source-backed tours isolated from the synthetic hackathon demos."""
import hashlib
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

BASE = Path(__file__).parent
TOURS = BASE / 'data' / '94404'
router = APIRouter()

@router.get('/94404', include_in_schema=False)
def viewer():
    return FileResponse(BASE / 'static' / '94404' / 'index.html')

def read_manifest():
    path = TOURS / 'manifest.json'
    if not path.exists():
        raise HTTPException(503, 'Run python scripts/build_94404.py first.')
    return json.loads(path.read_text())


def reviewed_video_candidates(manifest):
    """Accept review attestations only for this property's current photo/plan set."""
    try:
        registry = json.loads((TOURS / 'generated_videos.json').read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(registry, dict) or not isinstance(registry.get('videos'), list):
        return {}
    originals = {listing['id']: listing for listing in manifest['listings']}
    candidates = {}
    for record in registry['videos']:
        if not isinstance(record, dict) or record.get('status') != 'accepted':
            continue
        listing_id = record.get('listing_id')
        listing = originals.get(listing_id) if isinstance(listing_id, str) else None
        review = record.get('review')
        if not listing or not isinstance(review, dict):
            continue
        if any(review.get(field) != 'pass' for field in ('appearance', 'layout', 'motion')):
            continue
        if not isinstance(review.get('notes'), str) or not review['notes'].strip():
            continue
        sources = record.get('source_sha256')
        if not isinstance(sources, list) or not sources or any(not isinstance(value, str) for value in sources):
            continue
        own_hashes = {photo['sha256'] for photo in listing['photos']}
        model = listing.get('model')
        plan_index = model.get('floor_plan_index') if isinstance(model, dict) else None
        plan = next((photo for photo in listing['photos'] if photo['index'] == plan_index), None)
        if type(plan_index) is not int or plan is None:
            continue
        plan_hash = plan['sha256']
        source_hashes = set(sources)
        if not source_hashes <= own_hashes or plan_hash not in source_hashes or len(source_hashes - {plan_hash}) < 2:
            continue
        if not source_assets_match(listing, source_hashes):
            continue
        relative_path = record.get('path')
        if not isinstance(relative_path, str):
            continue
        relative = Path(relative_path)
        if len(relative.parts) != 2 or relative.parts[0] != 'videos' or relative.suffix.lower() != '.mp4':
            continue
        try:
            video_root = (TOURS / 'videos').resolve()
            path = (TOURS / relative).resolve()
            if not video_root.is_relative_to(TOURS.resolve()) or path.parent != video_root:
                continue
        except OSError:
            continue
        if not isinstance(record.get('sha256'), str):
            continue
        candidates[listing['id']] = (record, path)
    return candidates


def source_assets_match(listing, source_hashes):
    asset_root = (TOURS / 'assets').resolve()
    if not asset_root.is_relative_to(TOURS.resolve()):
        return False
    for photo in listing['photos']:
        if photo['sha256'] not in source_hashes:
            continue
        path = (TOURS / photo['path']).resolve()
        if path.parent != asset_root:
            return False
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest() != photo['sha256']:
                return False
        except OSError:
            return False
    return True


def video_integrity_matches(record, path):
    try:
        content = path.read_bytes()
    except OSError:
        return False
    return len(content) > 12 and content[4:8] == b'ftyp' and hashlib.sha256(content).hexdigest() == record['sha256']


def accepted_generated_videos(manifest):
    accepted = {}
    for listing_id, (record, path) in reviewed_video_candidates(manifest).items():
        if video_integrity_matches(record, path):
            label = record.get('label')
            accepted[listing_id] = {
                'url': f'/api/faithful/videos/{path.name}',
                'label': label if isinstance(label, str) and label.strip() else 'AI-generated walkthrough · reviewed pilot',
                'sha256': record['sha256'],
                'source_sha256': record['source_sha256'],
                'review': record['review'],
            }
    return accepted


@router.get('/api/faithful/94404')
def listings():
    manifest = read_manifest()
    accepted = accepted_generated_videos(manifest)
    return {**manifest, 'listings': [
        {**listing, 'generated_video': accepted.get(listing['id'])}
        for listing in manifest['listings']
    ]}


@router.get('/api/feed/94404')
def feed_listings():
    manifest = listings()
    feed = []
    for listing in manifest['listings']:
        street, city, _ = listing['address'].split(',', 2)
        first_photo = listing['photos'][0]
        generated = listing['generated_video']
        feed.append({
            **listing,
            'source_backed': True,
            'city': city.strip(),
            'title': street,
            'neighborhood': f"{city.strip()} · {listing['zip_code']}",
            'price': f"${listing['price']:,.0f}",
            'price_num': listing['price'],
            'rooms': [{
                'id': 'photo-0',
                'image_url': f"/api/faithful/assets/{Path(first_photo['path']).name}",
                'on_screen_hook': street,
                'short_name': 'Original photo',
            }],
            'preview_clip_url': generated['url'] if generated else None,
            'full_tour_url': generated['url'] if generated else None,
            'video_duration_label': generated['label'] if generated else 'Video pending',
            'research_url': f"/94404?embed=1&view=model#{listing['id']}",
            'social': {
                'thumbs_up': 0,
                'thumbs_down': 0,
                'open_house_live_count': 0,
                'verified_checkins': 0,
                'comments': [],
                'visitor_media': [],
                'attributes': {},
                'amazon_stars': None,
                'upvote_ratio': None,
                'hybrid_rank_score': None,
            },
        })
    return {
        'listings': feed,
        'summary': manifest['summary'],
        'selection': manifest['selection'],
        'requested_count': manifest['requested_count'],
    }


@router.get('/api/faithful/videos/{filename}')
def generated_video(filename: str):
    for record, path in reviewed_video_candidates(read_manifest()).values():
        if path.name == filename:
            if not path.is_file():
                raise HTTPException(404, 'Accepted generated video is missing.')
            if not video_integrity_matches(record, path):
                raise HTTPException(409, 'Generated video integrity check failed. Review the output before accepting a new baseline.')
            return FileResponse(path, media_type='video/mp4', headers={'Cache-Control': 'no-store'})
    raise HTTPException(404, 'No accepted generated video matches this request.')

@router.get('/api/faithful/assets/{filename}')
def asset(filename: str):
    path = TOURS / 'assets' / Path(filename).name
    if not path.is_file():
        raise HTTPException(404, 'Original asset missing. Run scripts/build_94404.py --download.')
    records = json.loads((TOURS / 'downloads.json').read_text())
    expected = next((record['sha256'] for record in records if Path(record['path']).name == path.name), None)
    content = path.read_bytes()
    if expected is None or hashlib.sha256(content).hexdigest() != expected:
        raise HTTPException(409, 'Original asset integrity check failed. Review the source before accepting a new baseline.')
    return Response(content=content, media_type='image/jpeg', headers={'Cache-Control':'no-store'})
