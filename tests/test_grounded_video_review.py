import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from scripts.review_grounded_video import ReviewError, review_job


def write(path, data):
    path.write_text(json.dumps(data))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def generated_job(tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('ffmpeg and ffprobe are required for offline media review')
    tours = tmp_path / 'tours'
    assets = tours / 'assets'
    assets.mkdir(parents=True)
    photos = []
    for index, color in [(0, '#bb4422'), (1, '#ffffff')]:
        image = assets / f'{index}.png'
        Image.new('RGB', (64, 48), color).save(image)
        photos.append({'index': index, 'path': f'assets/{index}.png',
                       'source_url': f'https://ssl.cdn-redfin.com/photo/test/{index}.png',
                       'sha256': sha(image)})
    write(tours / 'manifest.json', {'listings': [{'id': 'pilot', 'photos': photos}]})
    job = tours / 'video_jobs' / 'fixture'
    job.mkdir(parents=True)
    write(job / 'plan.json', {'listing_id': 'pilot', 'duration_seconds': 4,
                              'first_photo_index': 0, 'last_photo_index': 0,
                              'floor_plan_index': 1, 'support_photo_indices': []})
    write(job / 'provenance.json', {'listing_id': 'pilot', 'sources': photos})
    video = job / 'generated.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-loop', '1',
                    '-i', str(assets / '0.png'), '-t', '4', '-r', '4',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True)
    write(job / 'state.json', {'status': 'generated_unreviewed', 'sha256': sha(video)})
    return job, tours


def test_decoded_still_video_never_passes_visual_review(generated_job):
    job, tours = generated_job
    original_state = (job / 'state.json').read_bytes()
    report = review_job(job, tours)
    assert report['technical_status'] == 'passed_visual_review_pending'
    assert report['visual_review_status'] == 'pending'
    assert report['publishable'] is False
    assert report['checks']['video_decode_and_duration']['decoded_frame_count'] == 16
    references = report['artifacts']['reference_frames']
    assert len(references) == 9
    assert references[0]['frame_index'] == 0
    assert references[-1]['frame_index'] == 15
    assert all((job / frame['path']).is_file() for frame in references)
    assert (job / 'review/contact-sheet.jpg').is_file()
    assert (job / 'review/endpoint-comparison.jpg').is_file()
    assert 'mostly_near_still' in report['diagnostics']['temporal_changes']['flags']
    template = json.loads((job / 'review-template.json').read_text())
    assert template['overall_status'] == 'pending'
    candidate = template['registry_candidate']
    assert candidate['listing_id'] == 'pilot'
    assert candidate['path'] == f'videos/{job.name}.mp4'
    assert candidate['sha256'] == report['video_sha256']
    assert candidate['status'] == 'generated_unreviewed'
    assert candidate['review'] == {'appearance': 'pending', 'layout': 'pending', 'motion': 'pending', 'notes': ''}
    assert len(candidate['source_sha256']) == 2
    assert template['publishable'] is False
    assert all(item['status'] == 'pending' for item in template['reviews'].values())
    assert (job / 'state.json').read_bytes() == original_state


def test_changed_source_cannot_reuse_a_passing_report(generated_job):
    job, tours = generated_job
    review_job(job, tours)
    with (tours / 'assets/0.png').open('ab') as image:
        image.write(b'changed source')
    with pytest.raises(ReviewError, match='Source integrity mismatch'):
        review_job(job, tours)
    report = json.loads((job / 'quality-report.json').read_text())
    assert report['technical_status'] == 'failed'
    assert report['checks']['source_integrity']['status'] == 'failed'
    assert report['visual_review_status'] == 'pending'
    assert report['publishable'] is False
    assert report['artifacts'] == {}


def test_changed_generated_video_is_rejected(generated_job):
    job, tours = generated_job
    with (job / 'generated.mp4').open('ab') as video:
        video.write(b'changed video')
    with pytest.raises(ReviewError, match='SHA-256'):
        review_job(job, tours)
