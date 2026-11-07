#!/usr/bin/env python3
"""
Builds 100% distinct, slow-paced architectural walkthrough segments and 40-48s feed tours
for every house in CURATED_LISTINGS.
- Auto-discovers all genuine house-specific GMI AI video clips on disk in data/cache/
  (e.g. {lid}_seg{t_idx}_{reqid}.mp4), GMI voiceovers (vo_{lid}_{reqid}.mp3),
  and GMI 2K room photos (img_{lid}_{rid}_*.jpg).
- Never overwrites a real GMI video clip with a photo-glide fallback.
- Stitches each house's full 40-48s tour_*.mp4 with its own voiceover audio.
"""
import json
import subprocess
from pathlib import Path
from typing import Optional
import httpx

from server import CURATED_LISTINGS, CACHE_DIR, CACHE_INDEX_PATH, load_cache_index, save_cache_index

ROOMS_DIR = CACHE_DIR / "rooms"
ROOMS_DIR.mkdir(parents=True, exist_ok=True)


def find_newest_gmi_segment_mp4(lid: str, t_idx: int) -> Optional[Path]:
    prefix = f"{lid}_seg{t_idx}_"
    candidates = []
    for p in CACHE_DIR.glob(f"{prefix}*.mp4"):
        if p.name.endswith("_glide.mp4") or p.name.startswith("slow_"):
            continue
        if p.is_file() and p.stat().st_size > 20000:
            candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return candidates[0]


def find_newest_gmi_voiceover(lid: str) -> Optional[Path]:
    candidates = [
        p for p in CACHE_DIR.glob(f"vo_{lid}_*.mp3")
        if p.is_file() and p.stat().st_size > 5000
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return candidates[0]


def find_newest_gmi_room_image(lid: str, rid: str) -> Optional[Path]:
    candidates = [
        p for p in CACHE_DIR.glob(f"img_{lid}_{rid}_*.jpg")
        if p.is_file() and p.stat().st_size > 10000
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return candidates[0]


def download_room_images():
    with httpx.Client(timeout=25.0, follow_redirects=True) as client:
        for listing in CURATED_LISTINGS:
            lid = listing["id"]
            for room in listing.get("rooms", []):
                rid = room["id"]
                local_img = ROOMS_DIR / f"{lid}_{rid}.jpg"
                gmi_img = find_newest_gmi_room_image(lid, rid)
                if gmi_img:
                    local_img.write_bytes(gmi_img.read_bytes())
                    continue
                if not local_img.exists() or local_img.stat().st_size < 5000:
                    url = room["image_url"]
                    print(f"[Download] {lid} / {rid} -> {local_img.name}")
                    r = client.get(url)
                    if r.status_code == 200:
                        local_img.write_bytes(r.content)


def make_slow_cinematic_glide(img_a: Path, img_b: Path, out_mp4: Path):
    """
    Creates a serene, slow-paced 9-second 1280x720@30fps architectural glide from img_a to img_b
    using smooth pan + 2.0s optical cross-dissolve so there is zero fast jumping.
    """
    filter_complex = (
        "[0:v]scale=1360:765:force_original_aspect_ratio=increase,crop=1280:720:x='(iw-1280)*(t/5.5)':y='(ih-720)/2',fps=30,format=yuv420p[va];"
        "[1:v]scale=1360:765:force_original_aspect_ratio=increase,crop=1280:720:x='(iw-1280)*(1-t/5.5)':y='(ih-720)/2',fps=30,format=yuv420p[vb];"
        "[va][vb]xfade=transition=fade:duration=2.0:offset=3.5,format=yuv420p[v]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", "30", "-t", "5.5", "-i", str(img_a),
        "-loop", "1", "-framerate", "30", "-t", "5.5", "-i", str(img_b),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-maxrate", "1800k", "-bufsize", "3600k",
        "-movflags", "+faststart",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def normalize_and_slow_clip(in_mp4: Path, out_mp4: Path):
    """
    Normalizes a raw GMI video clip to 1280x720@30fps and slows it down by 1.55x
    so a 5s-8s GMI clip becomes a serene 8s-12s architectural walkthrough glide.
    """
    vf = (
        "setpts=1.55*PTS,"
        "scale=1280:720:force_original_aspect_ratio=increase,"
        "crop=1280:720,"
        "fps=30,"
        "format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_mp4),
        "-vf", vf,
        "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-maxrate", "1800k", "-bufsize", "3600k",
        "-movflags", "+faststart",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def rebuild_all_house_tours():
    download_room_images()
    idx = load_cache_index()
    segments = idx.setdefault("segments", {})
    voiceovers = idx.setdefault("voiceovers", {})

    for listing in CURATED_LISTINGS:
        lid = listing["id"]
        norm_clips = []

        # Auto-discover voiceover on disk
        vo_disk = find_newest_gmi_voiceover(lid)
        if vo_disk:
            req_short = vo_disk.stem.split("_")[-1]
            voiceovers[lid] = {
                "request_id": req_short,
                "status": "ready",
                "local_file": vo_disk.name,
            }

        for t in listing.get("transitions", []):
            t_idx = t["index"]
            seg_key = f"{lid}_seg{t_idx}"
            from_id = t["from_room"]
            to_id = t["to_room"]
            existing = segments.get(seg_key, {})

            # Always prefer a real GMI segment MP4 on disk for this house + segment
            real_gmi_mp4 = find_newest_gmi_segment_mp4(lid, t_idx)
            if real_gmi_mp4:
                req_short = real_gmi_mp4.stem.split("_")[-1]
                segments[seg_key] = {
                    "request_id": req_short,
                    "model": existing.get("model", "veo-3.1-fast-generate-001"),
                    "status": "ready",
                    "from_room": from_id,
                    "to_room": to_id,
                    "local_file": real_gmi_mp4.name,
                }
                slow_name = f"slow_{real_gmi_mp4.name}"
                slow_path = CACHE_DIR / slow_name
                if not slow_path.exists() or slow_path.stat().st_size < 10000:
                    print(f"[Slow-Mo Real GMI Clip] {seg_key}: {real_gmi_mp4.name} -> {slow_name}")
                    normalize_and_slow_clip(real_gmi_mp4, slow_path)
                norm_clips.append(slow_path)
            else:
                glide_name = f"{lid}_seg{t_idx}_glide.mp4"
                glide_path = CACHE_DIR / glide_name
                img_a = ROOMS_DIR / f"{lid}_{from_id}.jpg"
                img_b = ROOMS_DIR / f"{lid}_{to_id}.jpg"
                if not glide_path.exists() and img_a.exists() and img_b.exists():
                    print(f"[Build Unique House Glide] {seg_key}: {from_id} -> {to_id}")
                    make_slow_cinematic_glide(img_a, img_b, glide_path)
                if glide_path.exists():
                    segments[seg_key] = {
                        "request_id": f"glide-{lid}-{t_idx}",
                        "model": "gmi-room-glide",
                        "status": "ready",
                        "from_room": from_id,
                        "to_room": to_id,
                        "local_file": glide_name,
                    }
                    norm_clips.append(glide_path)

        # Stitch norm_clips into this house's dedicated 40-48s tour MP4 (atomically via temp file)
        tour_url = listing.get("preview_clip_url", "")
        if tour_url.startswith("/api/cache/") and norm_clips:
            tour_filename = tour_url.replace("/api/cache/", "")
            tour_path = CACHE_DIR / tour_filename
            tmp_tour_path = CACHE_DIR / f".tmp_{tour_filename}"

            sequence = list(norm_clips)
            if len(sequence) <= 3:
                sequence = sequence + list(reversed(sequence))[:2]
            elif len(sequence) == 4:
                sequence = sequence + [sequence[0]]

            concat_txt = CACHE_DIR / f"concat_{lid}.txt"
            concat_txt.write_text("".join(f"file '{p.name}'\n" for p in sequence))

            vo_info = voiceovers.get(lid, {})
            vo_file = vo_info.get("local_file")
            vo_path = (CACHE_DIR / vo_file) if vo_file else None

            if vo_path and vo_path.exists():
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                    "-i", str(vo_path),
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-maxrate", "1800k", "-bufsize", "3600k",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(tmp_tour_path),
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-maxrate", "1800k", "-bufsize", "3600k",
                    "-movflags", "+faststart",
                    str(tmp_tour_path),
                ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            tmp_tour_path.replace(tour_path)
            print(f"[Stitched Unique Tour] {lid} -> {tour_filename} ({tour_path.stat().st_size // 1024} KB)")

    save_cache_index(idx)
    print("All houses updated with latest GMI video segments, voiceovers & room images!")


if __name__ == "__main__":
    rebuild_all_house_tours()
