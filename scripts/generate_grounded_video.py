#!/usr/bin/env python3
"""Prepare one grounded pilot, submit it once, or resume polling without regeneration."""
import argparse
import json
import sys
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import grounded_video


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'submit', 'poll'])
    parser.add_argument('--plan', type=Path, default=BASE / 'data/94404/spinnaker-video-pilot.json')
    parser.add_argument('--credential-file', type=Path,
                        help='Explicitly designated project Gemini credential file (env assignment or labeled Markdown key)')
    args = parser.parse_args()
    try:
        job = grounded_video.prepare(args.plan)
        result = {'status': 'prepared', 'job': str(job), 'generation_requests': 0,
                  'source_images_verified': len(json.loads((job / 'provenance.json').read_text())['sources']),
                  'automatic_acceptance': False}
        if args.action != 'prepare':
            key = grounded_video.credential(args.credential_file)
            with httpx.Client() as client:
                action = grounded_video.submit if args.action == 'submit' else grounded_video.poll
                result = {**action(job, key, client), 'job': str(job)}
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, RuntimeError, KeyError, StopIteration, httpx.HTTPError) as error:
        # Never print provider response bodies, request headers, or credential values.
        print(str(error) if not isinstance(error, httpx.HTTPError) else 'Gemini connection failed; resume the same job.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
