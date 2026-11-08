#!/usr/bin/env python3
"""Download byte-preserved listing originals; extrude only an inspected source plan.

No model service or API credential is used. Re-run --download on a fresh checkout.
The geometry is a schematic, not a photogrammetric scan or a measured building.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
import httpx
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'data' / '94404'
ASSETS = OUT / 'assets'
MODEL = BASE / 'static' / '94404'
# The only inspected plan in the eligible evidence set.
PLAN_ID = 'redfin-1062292'
PLAN = {'index':43, 'crop':[378,26,902,820]}


def select_listings(source):
    eligible = [row for row in source['listings']
        if row['property_type']=='single_family' and row['zip_code']=='94404'
        and row['listing_status'] in ('for_sale','coming_soon')]
    return sorted(eligible, key=lambda row:(-row['price'], row['id']))[:source['requested_count']]


def sha(data):
    return hashlib.sha256(data).hexdigest()

def download(task):
    listing_id, index, url = task
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'ssl.cdn-redfin.com' or not parsed.path.startswith(('/photo/','/system_files/media/')):
        raise ValueError('Only observed Redfin photo URLs are supported')
    path = ASSETS / f'{listing_id}-{index:03d}.jpg'
    if not path.exists():
        response = httpx.get(url, timeout=30, follow_redirects=False)
        response.raise_for_status()
        # Validate before atomically installing the original bytes.
        import io
        Image.open(io.BytesIO(response.content)).verify()
        temp = path.with_suffix('.tmp')
        temp.write_bytes(response.content)
        temp.replace(path)
    with Image.open(path) as image:
        image.verify()
    return {'listing_id':listing_id,'index':index,'source_url':url,
            'path':f'assets/{path.name}','sha256':sha(path.read_bytes())}

def extract_wall_rectangles(image):
    """Keep thick dark linework; remove isolated text and door swing arcs.

    Exact raster runs become boxes, without rounding or resampling the footprint.
    Fixtures connected to walls can remain: this is disclosed in the model.
    """
    pixels = np.asarray(image.convert('RGB'))
    dark = np.max(pixels,axis=2) < 90
    thick = ndimage.binary_opening(dark, structure=np.ones((3,3)))
    labels, _ = ndimage.label(thick)
    sizes = np.bincount(labels.ravel())
    keep = sizes >= 60
    keep[0] = False
    mask = keep[labels]
    rectangles, active = [], {}
    for y,row in enumerate(mask):
        padded = np.pad(row.astype(int),(1,1))
        starts = np.where(np.diff(padded)==1)[0]
        ends = np.where(np.diff(padded)==-1)[0]
        current = set(zip(starts.tolist(),ends.tolist()))
        for run in set(active)-current:
            start_y = active.pop(run)
            rectangles.append([run[0],start_y,run[1]-run[0],y-start_y])
        for run in current-set(active):
            active[run]=y
    for (x1,x2),y in active.items():
        rectangles.append([x1,y,x2-x1,len(mask)-y])
    return mask, rectangles

def build_model(plan_asset):
    with Image.open(ASSETS / Path(plan_asset['path']).name) as im:
        plan = im.crop(PLAN['crop'])
        mask, rectangles = extract_wall_rectangles(plan)
    # Re-rasterize the actual box footprint independently to catch export errors.
    roundtrip = np.zeros_like(mask)
    for x,y,w,h in rectangles:
        roundtrip[y:y+h,x:x+w]=True
    intersection = np.logical_and(mask, roundtrip).sum()
    union = np.logical_or(mask, roundtrip).sum()
    model = {'source_sha256':plan_asset['sha256'],'source_image':plan_asset['source_url'],
        'crop':PLAN['crop'],'width':plan.width,'height':plan.height,
        'coordinate_system':'source image pixels; x right, z down; no metric calibration',
        'wall_height_pixels':70,'eye_height_pixels':44,'wall_rectangles':rectangles,
        'assumptions':['Wall height is schematic and uniform; ceiling heights are unknown.',
            'Horizontal scale is uncalibrated. Do not use for measurements.',
            'Dark thick plan linework is extruded. Some attached fixtures may remain.',
            'Thin windows, door leaves and arcs are not reconstructed.',
            'Furniture, finishes, lighting and unseen surfaces are not reconstructed.'],
        'review_status':'schematic_only',
        'verification':{'box_footprint_iou':round(float(intersection/union),8),
            'meaning':'Export fidelity to the extracted mask, not building accuracy.',
            'photo_realism':'not reconstructed or verified'}}
    (MODEL/'spinnaker-model.json').write_text(json.dumps(model,separators=(',',':')))
    # Reviewable independent overlay: magenta is extracted wall linework.
    overlay=np.asarray(plan.convert('RGB')).copy()
    overlay[mask] = [170,35,116]
    Image.fromarray(overlay).save(MODEL/'spinnaker-wall-overlay.png')
    return model

def build(fetch=False):
    ASSETS.mkdir(parents=True,exist_ok=True)
    MODEL.mkdir(parents=True,exist_ok=True)
    source=json.loads((BASE/'data/redfin_94404_sources.json').read_text())
    selected=select_listings(source)
    tasks=[(l['id'],i,url) for l in selected for i,url in enumerate(l['urls'])]
    if fetch:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            records=list(pool.map(download,tasks))
        # Preserve the first acquisition hashes: later changes must fail verification.
        old_path=OUT/'downloads.json'
        if old_path.exists():
            old={(r['listing_id'],r['index']):r['sha256'] for r in json.loads(old_path.read_text())}
            for record in records:
                expected=old.get((record['listing_id'],record['index']))
                if expected and expected != record['sha256']:
                    raise ValueError(f"Source changed for {record['path']}; review before accepting new baseline")
        old_path.write_text(json.dumps(records,indent=2)+'\n')
    else:
        records=json.loads((OUT/'downloads.json').read_text())
    photos={(r['listing_id'],r['index']):r for r in records}
    model=build_model(photos[(PLAN_ID,PLAN['index'])])
    listings=[]
    for rank,row in enumerate(selected,1):
        listing_id=row['id']
        assets=[photos[(listing_id,i)] for i in range(len(row['urls']))]
        for asset in assets:
            path=OUT/asset['path']
            if not path.is_file() or sha(path.read_bytes())!=asset['sha256']:
                raise ValueError(f"Original asset failed integrity check: {path.name}")
        listing={'id':listing_id,'rank':rank,'address':row['address'],
            'redfin_url':row['source_url'],'price':row['price'],'beds':row['beds'],
            'baths':row['baths'],'sqft':row['sqft'],
            'property_type':row['property_type'],'listing_status':row['listing_status'],'zip_code':row['zip_code'],'photos':assets,'model':None,
            'status':'needs_floor_plan','blocker':'No usable floor-plan image retrieved; verified whole-home 3D conversion is blocked.',
            'verification':{'original_hashes':'pass','original_count':len(assets),
                'photo_edits':'none; original bytes are served without retouching',
                'spatial_fidelity':'not verified','novel_view_fidelity':'not verified'}}
        if listing_id==PLAN_ID:
            listing.update({'status':'schematic_3d','blocker':'Schematic plan extrusion only. Furnished or photorealistic 3D reconstruction remains unverified.',
                'model':{'url':'/static/94404/spinnaker-model.json','floor_plan_index':PLAN['index'],
                    'overlay_url':'/static/94404/spinnaker-wall-overlay.png',
                    'assumptions':model['assumptions'],'verification':model['verification']}})
        listings.append(listing)
    manifest={'source':source['source'],'selection':source['selection'],
        'snapshot_date':source['snapshot_date'],'snapshot_timezone':source['snapshot_timezone'],
        'requested_count':source['requested_count'],'selection_complete':source['selection_complete'],'excluded':source['excluded'],
        'conversion_complete':False,'summary':{'homes':len(selected),'original_images':sum(len(row['urls']) for row in selected),
            'schematic_models':1,'verified_photorealistic_models':0,'needs_floor_plan':sum(l['model'] is None for l in listings),'unfilled_selection_slots':max(0,source['requested_count']-len(selected))},
        'listings':listings}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest['summary']))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download',action='store_true')
    build(parser.parse_args().download)
