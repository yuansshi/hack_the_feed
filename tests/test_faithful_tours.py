import hashlib
import importlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

BASE = Path(__file__).resolve().parents[1]

@pytest.fixture
def client():
    import server
    with patch.object(server, 'load_api_key', side_effect=AssertionError('Browsing must not read a credential')):
        with TestClient(server.app) as client:
            yield client

def test_browsing_and_worker_import_need_no_api_key(client):
    importlib.import_module('gmi_agent_worker')
    assert client.get('/').status_code == 200
    assert client.get('/94404').status_code == 200
    assert client.get('/api/listings').status_code == 200

def test_unavailable_listing_never_becomes_a_substitute_home(client):
    result=client.post('/api/redfin/parse',json={'url':'https://www.redfin.com/CA/Foster-City/missing-94404/home/00000'})
    assert result.status_code==422
    assert 'listing' not in result.json()
    assert client.post('/api/redfin/parse',json={'url':'https://example.org/'}).status_code==422

def test_import_selected_listing_opens_source_viewer(client):
    manifest=client.get('/api/faithful/94404').json()
    listing=next(row for row in manifest['listings'] if row['id']=='redfin-1062292')
    result=client.post('/api/redfin/parse',json={'url':listing['redfin_url']}).json()
    assert result=={'viewer_url':'/94404#redfin-1062292','source':'listing_originals'}

def test_partial_conversion_cannot_be_reported_as_verified(client):
    manifest=client.get('/api/faithful/94404').json()
    assert manifest['conversion_complete'] is False
    assert len(manifest['listings'])==6
    assert sum(l['model'] is not None for l in manifest['listings'])==1
    assert all(l['verification']['novel_view_fidelity']=='not verified' for l in manifest['listings'])
    assert all(l['model'] is None for l in manifest['listings'] if l['status']=='needs_floor_plan')

def test_served_originals_are_byte_identical_to_acquisition(client):
    manifest=client.get('/api/faithful/94404').json()
    for listing in manifest['listings']:
        for photo in listing['photos']:
            filename=Path(photo['path']).name
            # Offline CI may lack originals; local acceptance runs with all assets.
            path=BASE/'data/94404/assets'/filename
            if not path.exists():
                pytest.skip('Run scripts/build_94404.py --download for asset integrity acceptance')
            response=client.get('/api/faithful/assets/'+filename)
            assert response.status_code==200
            assert hashlib.sha256(response.content).hexdigest()==photo['sha256']

def test_missing_asset_is_explicit_not_replaced(client):
    assert client.get('/api/faithful/assets/not-a-listing-photo.jpg').status_code==404


def test_modified_original_is_rejected(client):
    from faithful_tours import TOURS
    path=TOURS/'assets/redfin-1062292-010.jpg'
    if not path.exists():
        pytest.skip('Local originals are required')
    original=path.read_bytes()
    try:
        path.write_bytes(original+b'changed')
        assert client.get('/api/faithful/assets/redfin-1062292-010.jpg').status_code==409
    finally:
        path.write_bytes(original)


def test_selection_excludes_non_houses_and_sorts_asking_prices():
    from scripts.build_94404 import select_listings
    rows=[
        dict(id='house-low',property_type='single_family',zip_code='94404',listing_status='for_sale',price=2),
        dict(id='condo-high',property_type='condo',zip_code='94404',listing_status='for_sale',price=9),
        dict(id='sold-high',property_type='single_family',zip_code='94404',listing_status='sold',price=8),
        dict(id='pending-high',property_type='single_family',zip_code='94404',listing_status='pending',price=7),
        dict(id='wrong-zip',property_type='single_family',zip_code='94065',listing_status='for_sale',price=6),
        dict(id='house-high',property_type='single_family',zip_code='94404',listing_status='coming_soon',price=5)]
    assert [row['id'] for row in select_listings({'listings':rows,'requested_count':10})]==['house-high','house-low']


def test_selection_shortfall_is_explicit(client):
    manifest=client.get('/api/faithful/94404').json()
    assert manifest['requested_count']==10
    assert manifest['selection_complete'] is False
    assert manifest['summary']['unfilled_selection_slots']==4
    rows=manifest['listings']
    assert all(row['property_type']=='single_family' and row['zip_code']=='94404' for row in rows)
    assert [row['price'] for row in rows]==sorted([row['price'] for row in rows],reverse=True)
