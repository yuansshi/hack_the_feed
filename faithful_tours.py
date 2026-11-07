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
