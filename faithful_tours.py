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

@router.get('/api/faithful/94404')
def listings():
    path = TOURS / 'manifest.json'
    if not path.exists():
        raise HTTPException(503, 'Run python scripts/build_94404.py first.')
    return json.loads(path.read_text())


@router.get('/api/feed/94404')
def feed_listings():
    manifest = listings()
    feed = []
    for listing in manifest['listings']:
        street, city, _ = listing['address'].split(',', 2)
        first_photo = listing['photos'][0]
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
            'preview_clip_url': None,
            'full_tour_url': None,
            'video_duration_label': 'Original photos',
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
