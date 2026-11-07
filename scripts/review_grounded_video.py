#!/usr/bin/env python3
"""Offline technical checks and visual-review artifacts for one generated pilot.

This command never accepts or publishes a video. Endpoint similarity and temporal
changes are diagnostics; novel-view fidelity always requires a separate review.
"""
import argparse
import fcntl
import hashlib
import io
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

BASE = Path(__file__).resolve().parents[1]
TOURS = BASE / 'data' / '94404'
REVIEW_ITEMS = (
    'source_identity_and_camera_correspondence',
    'endpoint_appearance',
    'layout_openings_and_clearances',
    'furniture_materials_and_lighting',
    'temporal_geometry_and_object_consistency',
    'genuine_camera_motion_parallax_and_occlusion',
    'no_cuts_morphs_or_restyling',
    'floor_plan_consistency_and_unseen_surfaces',
    'novel_view_fidelity',
)


class ReviewError(ValueError):
    pass


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def run(command, timeout=90):
    try:
        return subprocess.run(command, check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout).stdout
    except FileNotFoundError as error:
        raise ReviewError(f'Required executable is unavailable: {command[0]}') from error
    except subprocess.TimeoutExpired as error:
        raise ReviewError(f'{command[0]} exceeded the {timeout}s offline review limit.') from error
    except subprocess.CalledProcessError as error:
        # Report diagnostics, never source files, environment variables or credentials.
        detail = error.stderr.decode(errors='replace').strip()[-1200:]
        raise ReviewError(f'{command[0]} failed: {detail}') from error


def verified_sources(plan, provenance, tours):
    manifest = json.loads((tours / 'manifest.json').read_text())
    listing = next((row for row in manifest['listings'] if row['id'] == plan['listing_id']), None)
    if listing is None or provenance['listing_id'] != plan['listing_id']:
        raise ReviewError('Source listing identity does not match the current manifest.')
    required = set([plan['first_photo_index'], plan['last_photo_index'],
                    plan['floor_plan_index'], *plan['support_photo_indices']])
    sources = provenance['sources']
    if len({record['index'] for record in sources}) != len(sources):
        raise ReviewError('Duplicate source photo indices in job provenance.')
    by_index = {record['index']: record for record in sources}
    if not required.issubset(by_index):
        raise ReviewError('Job provenance does not include every required source image.')
    current = {record['index']: record for record in listing['photos']}
    checks, endpoints = [], {}
    for index, record in by_index.items():
        expected = current.get(index)
        if expected is None or any(record[key] != expected[key] for key in ('path', 'sha256', 'source_url')):
            raise ReviewError(f'Source identity or hash baseline changed for photo {index}.')
        path = (tours / record['path']).resolve()
        if not path.is_relative_to((tours / 'assets').resolve()):
            raise ReviewError(f'Source photo {index} is outside the original-image directory.')
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != record['sha256']:
            raise ReviewError(f'Source integrity mismatch for photo {index}.')
        checks.append({'photo_index': index, 'path': record['path'],
                       'sha256': record['sha256'], 'status': 'pass'})
        if index in (plan['first_photo_index'], plan['last_photo_index']):
            with Image.open(io.BytesIO(content)) as image:
                endpoints[index] = image.convert('RGB')
    return checks, endpoints


def inspect_video(video, expected_duration):
    if expected_duration not in (4, 6, 8):
        raise ReviewError('Pilot duration must be 4, 6 or 8 seconds.')
    probe = json.loads(run([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames',
        '-show_entries', 'stream=codec_name,width,height,avg_frame_rate,nb_read_frames,duration:format=duration',
        '-of', 'json', str(video),
    ]))
    streams = probe.get('streams', [])
    if len(streams) != 1:
        raise ReviewError('No readable video stream was found.')
    stream = streams[0]
    try:
        duration = float(stream.get('duration') or probe['format']['duration'])
        count = int(stream['nb_read_frames'])
        width, height = int(stream['width']), int(stream['height'])
    except (KeyError, ValueError, TypeError) as error:
        raise ReviewError('Video duration, dimensions or decoded frame count is unavailable.') from error
    if not np.isfinite(duration) or abs(duration - expected_duration) > .5:
        raise ReviewError(f'Video duration {duration:g}s does not match the requested {expected_duration}s (±0.5s).')
    if not (9 <= count <= 2000 and 0 < width <= 8192 and 0 < height <= 8192):
        raise ReviewError('Video dimensions/frame count are outside this bounded pilot review.')
    # Decode every frame with error escalation. A tiny whole-frame representation
    # also allows adjacent-frame changes to be inspected without new dependencies.
    raw = run([
        'ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(video),
        '-map', '0:v:0', '-an', '-vf',
        'scale=96:54:force_original_aspect_ratio=decrease,pad=96:54:(ow-iw)/2:(oh-ih)/2',
        '-pix_fmt', 'rgb24', '-fps_mode', 'passthrough', '-f', 'rawvideo', '-',
    ])
    pixels_per_frame = 96 * 54 * 3
    if len(raw) != count * pixels_per_frame:
        raise ReviewError('Full decode frame count did not match ffprobe.')
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(count, 54, 96, 3)
    changes = np.abs(np.diff(frames.astype(np.int16), axis=0)).mean(axis=(1, 2, 3))
    return {
        'status': 'pass', 'codec': stream['codec_name'], 'width': width,
        'height': height, 'duration_seconds': duration,
        'requested_duration_seconds': expected_duration, 'duration_tolerance_seconds': .5,
        'decoded_frame_count': count,
    }, {
        'method': 'Adjacent-frame mean absolute RGB change, whole frames letterboxed to 96x54.',
        'changes_0_255': np.round(changes, 5).tolist(),
        'near_still_pair_count': int((changes < .5).sum()),
        'large_change_frame_indices': (np.flatnonzero(changes > 60) + 1).tolist(),
        'flags': (['mostly_near_still'] if float((changes < .5).mean()) > .9 else [])
                 + (['large_adjacent_frame_change'] if bool((changes > 60).any()) else []),
        'caveat': 'Diagnostic flags only. Static content, slow motion, cuts and warps need visual inspection; these numbers cannot validate genuine 3D motion.',
    }


def letterbox(image, size):
    fitted = ImageOps.contain(image.convert('RGB'), size, Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', size, '#151515')
    canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    return canvas


def make_artifacts(job, video, count, sources, plan):
    output = job / 'review'
    output.mkdir(exist_ok=True)
    indices = [round(index * (count - 1) / 8) for index in range(9)]
    for index in range(1, 10):
        (output / f'frame-{index:02d}.png').unlink(missing_ok=True)
    expression = '+'.join(f'eq(n\\,{index})' for index in indices)
    run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(video),
         '-map', '0:v:0', '-an', '-vf', f'select={expression}',
         '-fps_mode', 'vfr', '-frames:v', '9', str(output / 'frame-%02d.png')])
    paths = [output / f'frame-{index:02d}.png' for index in range(1, 10)]
    if not all(path.is_file() for path in paths):
        raise ReviewError('Reference-frame extraction did not produce all nine frames.')
    frames = []
    for path in paths:
        with Image.open(path) as image:
            frames.append(image.convert('RGB'))
    sheet = Image.new('RGB', (960, 3 * 204), '#151515')
    draw = ImageDraw.Draw(sheet)
    for offset, (index, frame) in enumerate(zip(indices, frames, strict=True)):
        x, y = offset % 3 * 320, offset // 3 * 204
        sheet.paste(letterbox(frame, (320, 180)), (x, y))
        draw.text((x + 8, y + 184), f'Reference {offset + 1}: decoded frame {index}', fill='white')
    sheet.save(output / 'contact-sheet.jpg', quality=95)
    comparison = Image.new('RGB', (1280, 2 * 388), '#151515')
    draw = ImageDraw.Draw(comparison)
    diagnostics = {}
    for row, (name, index, frame) in enumerate([
        ('first', plan['first_photo_index'], frames[0]),
        ('last', plan['last_photo_index'], frames[-1]),
    ]):
        source = letterbox(sources[index], (640, 360))
        generated = letterbox(frame, (640, 360))
        comparison.paste(source, (0, row * 388))
        comparison.paste(generated, (640, row * 388))
        draw.text((8, row * 388 + 365), f'Original {name} source: photo index {index}', fill='white')
        draw.text((648, row * 388 + 365), f'Generated {name} decoded frame', fill='white')
        mae = float(np.abs(np.asarray(source).astype(np.float32)
                           - np.asarray(generated).astype(np.float32)).mean())
        diagnostics[name] = {'photo_index': index, 'rgb_mean_absolute_error_0_255': round(mae, 5),
                             'mean_absolute_similarity_0_1': round(1 - mae / 255, 6)}
    comparison.save(output / 'endpoint-comparison.jpg', quality=95)
    return {
        'reference_frames': [{'frame_index': index, 'path': str(path.relative_to(job))}
                             for index, path in zip(indices, paths, strict=True)],
        'contact_sheet': 'review/contact-sheet.jpg',
        'endpoint_comparison': 'review/endpoint-comparison.jpg',
    }, {
        'method': 'Mean absolute RGB error after resizing and letterboxing each entire image to 640x360; similarity = 1 - error/255. No crop or registration.',
        'endpoints': diagnostics,
        'caveat': 'Diagnostic only, with no pass threshold. Viewpoint, aspect ratio, exposure and codec differences affect this score. Endpoint similarity does not validate intermediate or novel views, layout, temporal consistency or 3D camera motion.',
    }


def review_job(job_dir, tours_dir=TOURS):
    job, tours = Path(job_dir).resolve(), Path(tours_dir).resolve()
    if not job.is_dir():
        raise ReviewError('Job directory does not exist.')
    report = {'schema_version': 1, 'technical_status': 'failed',
              'visual_review_status': 'pending', 'publishable': False,
              'checks': {}, 'artifacts': {}, 'diagnostics': {}}
    template = {'schema_version': 1, 'overall_status': 'pending',
                'publishable': False, 'reviewer': None,
                'instructions': 'Copy this template to a separate review record. This file never approves or publishes a video; rerunning QC regenerates this pending template.',
                'reviews': {item: {'status': 'pending', 'notes': ''} for item in REVIEW_ITEMS}}
    stage = 'job_inputs'
    with (job / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            plan = json.loads((job / 'plan.json').read_text())
            provenance = json.loads((job / 'provenance.json').read_text())
            state = json.loads((job / 'state.json').read_text())
            if state.get('status') != 'generated_unreviewed':
                raise ReviewError('QC requires a generated_unreviewed job; it never starts generation.')
            report['listing_id'] = plan['listing_id']
            report['checks'][stage] = {'status': 'pass'}
            stage = 'video_integrity'
            video = job / 'generated.mp4'
            if not video.resolve().is_relative_to(job) or not video.is_file() or video.stat().st_size > 200 * 1024 * 1024:
                raise ReviewError('Generated video is missing or exceeds the 200 MiB pilot bound.')
            video_sha = digest(video)
            if video_sha != state.get('sha256'):
                raise ReviewError('Generated video SHA-256 does not match the recorded output.')
            report['video_sha256'] = template['video_sha256'] = video_sha
            report['checks'][stage] = {'status': 'pass', 'sha256': video_sha}
            stage = 'source_integrity'
            checks, endpoints = verified_sources(plan, provenance, tours)
            report['checks'][stage] = {'status': 'pass', 'sources': checks}
            template['registry_candidate'] = {
                'listing_id': plan['listing_id'], 'path': f'videos/{job.name}.mp4',
                'sha256': video_sha, 'status': 'generated_unreviewed',
                'source_sha256': [source['sha256'] for source in provenance['sources']],
                'review': {'appearance': 'pending', 'layout': 'pending', 'motion': 'pending', 'notes': ''},
                'label': 'AI-generated walkthrough · reviewed pilot',
            }
            stage = 'video_decode_and_duration'
            media, temporal = inspect_video(video, plan['duration_seconds'])
            report['checks'][stage] = media
            report['diagnostics']['temporal_changes'] = temporal
            stage = 'review_artifacts'
            artifacts, similarity = make_artifacts(job, video, media['decoded_frame_count'], endpoints, plan)
            report['artifacts'] = artifacts
            report['diagnostics']['endpoint_similarity'] = similarity
            report['checks'][stage] = {'status': 'pass'}
            report['technical_status'] = 'passed_visual_review_pending'
            write_json(job / 'quality-report.json', report)
            write_json(job / 'review-template.json', template)
        except (ReviewError, OSError, KeyError, TypeError, ValueError) as error:
            report['checks'][stage] = {'status': 'failed', 'error': str(error)}
            write_json(job / 'quality-report.json', report)
            write_json(job / 'review-template.json', template)
            raise ReviewError(str(error)) from error
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_dir', type=Path)
    args = parser.parse_args()
    try:
        report = review_job(args.job_dir)
    except ReviewError as error:
        parser.exit(1, f'QC failed: {error}\n')
    print(json.dumps({'technical_status': report['technical_status'],
                      'visual_review_status': report['visual_review_status'],
                      'publishable': False, 'report': str(args.job_dir / 'quality-report.json')}))


if __name__ == '__main__':
    main()
