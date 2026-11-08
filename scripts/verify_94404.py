#!/usr/bin/env python3
"""Verify served original bytes against independently saved acquisition hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import httpx

BASE=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8044')
    args=parser.parse_args()
    hashes=json.loads((BASE/'data/94404/downloads.json').read_text())
    with httpx.Client(base_url=args.base_url,timeout=30) as client:
        response=client.get('/api/faithful/94404');response.raise_for_status()
        manifest=response.json()
        assert len(manifest['listings'])==6
        assert manifest['requested_count']==10
        assert manifest['selection_complete'] is False
        assert all(row['property_type']=='single_family' for row in manifest['listings'])
        for record in hashes:
            response=client.get('/api/faithful/assets/'+Path(record['path']).name)
            response.raise_for_status()
            assert hashlib.sha256(response.content).hexdigest()==record['sha256'],record['path']
        assert manifest['conversion_complete'] is False
        assert manifest['summary']['verified_photorealistic_models']==0
    print(json.dumps({'served_original_hashes':'pass','originals_checked':len(hashes),
        'conversion_complete':False,'verified_photorealistic_models':0}))

if __name__=='__main__':main()
