#!/usr/bin/env python3
"""
Parallel GMI Cloud Continuous Image + Video Walkthrough Generator Worker.
Designed to be run by multiple parallel agents (--worker 1, 2, 3, 4) across
distinct GMI Cloud model queues until the GMI_API_KEY token balance is exhausted.

Every time a segment clip or voiceover finishes:
1. Downloads the MP4/MP3/JPG to data/cache/
2. Atomically updates data/cache_index.json (using fcntl file lock)
3. Runs build_unique_house_feeds.py (with lock) so the live web app at
   http://localhost:8000 immediately serves the newly rendered GMI video!
"""
import argparse
import base64
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "data" / "cache"
CACHE_INDEX_PATH = BASE_DIR / "data" / "cache_index.json"
LOCK_PATH = BASE_DIR / "data" / "cache_index.lock"
GMI_ROOMS_DIR = CACHE_DIR / "gmi_rooms"
GMI_ROOMS_DIR.mkdir(parents=True, exist_ok=True)

from server import CURATED_LISTINGS, load_api_key, GMI_QUEUE_BASE_URL, extract_media_url, extract_base64_audio


def atomic_update_cache_index(mutator_fn):
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        try:
            if CACHE_INDEX_PATH.exists():
                idx = json.loads(CACHE_INDEX_PATH.read_text())
            else:
                idx = {"segments": {}, "voiceovers": {}, "oriane": {}, "gmi_generations": []}
            mutator_fn(idx)
            CACHE_INDEX_PATH.write_text(json.dumps(idx, indent=2))
        finally:
            fcntl.flock(lockf, fcntl.LOCK_UN)


def safe_rebuild_tours():
    with open(LOCK_PATH, "w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        try:
            subprocess.run(
                [sys.executable, str(BASE_DIR / "build_unique_house_feeds.py")],
                check=False,
            )
        finally:
            fcntl.flock(lockf, fcntl.LOCK_UN)


def build_model_payload(
    model: str,
    prompt: str,
    first_frame_url: str,
    last_frame_url: str,
    duration: int = 8,
    resolution: str = "1080p",
) -> Dict[str, Any]:
    if model in ("veo-3.1-lite-generate-001", "veo-3.1-fast-generate-001", "veo-3.1-generate-001"):
        return {
            "model": model,
            "payload": {
                "prompt": prompt,
                "image": first_frame_url,
                "lastFrame": last_frame_url,
                "durationSeconds": duration if duration in (4, 6, 8) else 8,
                "aspectRatio": "16:9",
                "generateAudio": False,
                "resolution": resolution if resolution in ("720p", "1080p") else "1080p",
            },
        }
    elif model == "pixverse-v6-transition":
        return {
            "model": model,
            "payload": {
                "prompt": prompt,
                "first_frame_img": first_frame_url,
                "last_frame_img": last_frame_url,
                "duration": duration if duration in (5, 8) else 5,
                "quality": "720p",
                "generate_audio_switch": False,
            },
        }
    elif model == "pixverse-v5.6-transition":
        return {
            "model": model,
            "payload": {
                "prompt": prompt,
                "first_frame_image": first_frame_url,
                "last_frame_image": last_frame_url,
                "duration": str(duration if duration in (5, 8, 10) else 8),
                "quality": "720p",
                "generate_audio_switch": False,
            },
        }
    elif model == "kling-o1-flfv":
        return {
            "model": model,
            "payload": {
                "prompt": prompt,
                "first_frame_image": first_frame_url,
                "end_frame_image": last_frame_url,
                "mode": "pro",
                "duration": "5",
            },
        }
    elif model == "vidu-q2-pro-flfv":
        return {
            "model": model,
            "payload": {
                "prompt": prompt,
                "first_frame_image": first_frame_url,
                "last_frame_image": last_frame_url,
                "duration": 5,
            },
        }
    elif model == "ltx-2-fast-image-to-video":
        return {
            "model": model,
            "payload": {
                "image_uri": first_frame_url,
                "prompt": prompt,
                "duration": "8",
                "resolution": "1920x1080",
                "fps": 25,
                "generate_audio": False,
                "camera_motion": "dolly_in",
            },
        }
    else:
        raise ValueError(f"Unsupported model: {model}")


def submit_and_wait_gmi_job(
    client: httpx.Client,
    body: Dict[str, Any],
    target_prefix: str,
    max_wait_sec: int = 360,
) -> Optional[Path]:
    headers = {
        "Authorization": f"Bearer {load_api_key('GMI_API_KEY')}",
        "Content-Type": "application/json",
    }
    model = body.get("model")
    print(f"[GMI Submit] model={model} target={target_prefix}")
    resp = client.post(f"{GMI_QUEUE_BASE_URL}/requests", headers=headers, json=body, timeout=45.0)
    if resp.status_code not in (200, 201, 202):
        print(f"[GMI Error] model={model} HTTP {resp.status_code}: {resp.text[:300]}")
        if "insufficient" in resp.text.lower() or "balance" in resp.text.lower() or "quota" in resp.text.lower() or resp.status_code == 402:
            print("[GMI Exhausted] Token balance reached 0!")
            sys.exit(0)
        return None

    rjson = resp.json()
    req_id = rjson.get("request_id") or rjson.get("id")
    if not req_id:
        print(f"[GMI Error] No request_id in {rjson}")
        return None

    print(f"[GMI Queued] model={model} req_id={req_id} -> polling...")
    start_t = time.time()
    while time.time() - start_t < max_wait_sec:
        time.sleep(6)
        pr = client.get(f"{GMI_QUEUE_BASE_URL}/requests/{req_id}", headers=headers, timeout=30.0)
        if pr.status_code != 200:
            continue
        pdata = pr.json()
        status = pdata.get("status", "processing")
        if status in ("finished", "succeeded", "completed", "success"):
            media_url = extract_media_url(pdata)
            if media_url:
                ext = ".mp4"
                if ".jpg" in media_url or ".jpeg" in media_url or "img_" in target_prefix:
                    ext = ".jpg"
                elif ".png" in media_url:
                    ext = ".png"
                elif ".mp3" in media_url or "vo_" in target_prefix:
                    ext = ".mp3"
                filename = f"{target_prefix}_{req_id[:8]}{ext}"
                out_path = CACHE_DIR / filename
                dl = client.get(media_url, follow_redirects=True, timeout=90.0)
                if dl.status_code == 200 and len(dl.content) > 1000:
                    out_path.write_bytes(dl.content)
                    print(f"[GMI Ready!] {filename} ({len(dl.content)//1024} KB) via {model}")
                    return out_path
            b64_audio = extract_base64_audio(pdata)
            if b64_audio:
                filename = f"{target_prefix}_{req_id[:8]}.mp3"
                out_path = CACHE_DIR / filename
                out_path.write_bytes(b64_audio)
                print(f"[GMI Audio Ready!] {filename} ({len(b64_audio)//1024} KB)")
                return out_path
            print(f"[GMI Warning] Job {req_id} finished but no media_url extracted: {str(pdata)[:300]}")
            return None
        elif status in ("failed", "error", "cancelled", "canceled"):
            print(f"[GMI Job Failed] req_id={req_id} model={model}: {str(pdata)[:300]}")
            return None
    print(f"[GMI Timeout] req_id={req_id} model={model} after {max_wait_sec}s")
    return None


def register_ready_segment(listing_id: str, seg_idx: int, from_room: str, to_room: str, model: str, local_path: Path):
    req_short = local_path.stem.split("_")[-1]
    seg_key = f"{listing_id}_seg{seg_idx}"

    def _mutate(idx):
        idx.setdefault("segments", {})[seg_key] = {
            "request_id": req_short,
            "model": model,
            "status": "ready",
            "from_room": from_room,
            "to_room": to_room,
            "local_file": local_path.name,
        }
        idx.setdefault("gmi_generations", []).append({
            "type": "video_segment",
            "segment": seg_key,
            "model": model,
            "file": local_path.name,
            "timestamp": time.time(),
        })

    atomic_update_cache_index(_mutate)
    # Remove any old slow_ cached file for this segment so rebuild regenerates it
    for old_slow in CACHE_DIR.glob(f"slow_{listing_id}_seg{seg_idx}_*.mp4"):
        try:
            old_slow.unlink()
        except OSError:
            pass
    safe_rebuild_tours()


def register_ready_voiceover(listing_id: str, local_path: Path):
    req_short = local_path.stem.split("_")[-1]

    def _mutate(idx):
        idx.setdefault("voiceovers", {})[listing_id] = {
            "request_id": req_short,
            "status": "ready",
            "local_file": local_path.name,
        }

    atomic_update_cache_index(_mutate)
    safe_rebuild_tours()


def run_voiceovers_for_all_houses(client: httpx.Client):
    voices = ["Amara", "Marcus", "Amara", "Marcus", "Amara"]
    for i, listing in enumerate(CURATED_LISTINGS):
        lid = listing["id"]
        idx = json.loads(CACHE_INDEX_PATH.read_text()) if CACHE_INDEX_PATH.exists() else {}
        vo = idx.get("voiceovers", {}).get(lid, {})
        if vo.get("local_file") and (CACHE_DIR / vo["local_file"]).exists():
            continue
        script = listing.get("voiceover_script", "")
        if isinstance(script, tuple):
            script = " ".join(script)
        body = {
            "model": "inworld-tts-2-flash",
            "payload": {
                "text": script,
                "voice_id": voices[i % len(voices)],
            },
        }
        out = submit_and_wait_gmi_job(client, body, f"vo_{lid}", max_wait_sec=90)
        if out and out.exists():
            register_ready_voiceover(lid, out)


def get_listing_transition_jobs() -> List[Dict[str, Any]]:
    jobs = []
    for listing in CURATED_LISTINGS:
        lid = listing["id"]
        rooms_by_id = {r["id"]: r for r in listing.get("rooms", [])}
        for t in listing.get("transitions", []):
            r_from = rooms_by_id.get(t["from_room"])
            r_to = rooms_by_id.get(t["to_room"])
            if not r_from or not r_to:
                continue
            jobs.append({
                "listing_id": lid,
                "seg_idx": t["index"],
                "from_room": t["from_room"],
                "to_room": t["to_room"],
                "first_frame_url": r_from["image_url"],
                "last_frame_url": r_to["image_url"],
                "prompt": t["prompt"],
            })
    return jobs


def run_worker(worker_id: int, max_rounds: int = 25):
    """
    Each worker targets a distinct set of GMI Cloud model queues and house segments
    so all workers run in parallel without hitting per-model concurrency limits,
    continuously generating and upgrading house walkthroughs until GMI credits run out.
    """
    all_jobs = get_listing_transition_jobs()
    # Filter to jobs that still use photo-glide fallback first, then cycle all jobs with higher-tier models
    priority_jobs = [j for j in all_jobs if j["listing_id"] != "palo-alto-glass-villa"] + [
        j for j in all_jobs if j["listing_id"] == "palo-alto-glass-villa"
    ]

    worker_models = {
        1: ["veo-3.1-fast-generate-001", "veo-3.1-generate-001"],
        2: ["veo-3.1-lite-generate-001", "ltx-2-fast-image-to-video"],
        3: ["pixverse-v6-transition", "pixverse-v5.6-transition", "kling-o1-flfv"],
        4: ["vidu-q2-pro-flfv", "veo-3.1-fast-generate-001", "pixverse-v6-transition"],
    }.get(worker_id, ["veo-3.1-fast-generate-001"])

    with httpx.Client(timeout=60.0) as client:
        if worker_id == 1:
            print("[Worker 1] Generating GMI Inworld TTS voiceovers for all houses first...")
            run_voiceovers_for_all_houses(client)

        round_num = 0
        while round_num < max_rounds:
            round_num += 1
            print(f"=== [Worker {worker_id}] Starting Continuous GMI Generation Round {round_num} ===")

            # If worker 4, also generate bespoke 2K architectural room photos via gemini-3.1-flash-image / seedream-5.0-pro
            if worker_id == 4:
                for listing in CURATED_LISTINGS:
                    lid = listing["id"]
                    for room in listing.get("rooms", []):
                        rid = room["id"]
                        img_prompt = (
                            f"Ultra-luxury architectural Digest interior photography of {room['name']} in {listing['city']}, "
                            f"{room['vibe']}, {room['ambient_desc']}, warm golden hour natural sunlight, 16:9 wide angle rectilinear lens, photorealistic 8k."
                        )
                        img_model = "gemini-3.1-flash-image" if (round_num % 2 == 1) else "seedream-5.0-pro"
                        if img_model == "gemini-3.1-flash-image":
                            img_body = {
                                "model": "gemini-3.1-flash-image",
                                "payload": {
                                    "prompt": img_prompt,
                                    "image_size": "2K",
                                    "aspect_ratio": "16:9",
                                    "image_output_format": "jpeg",
                                },
                            }
                        else:
                            img_body = {
                                "model": "seedream-5.0-pro",
                                "payload": {
                                    "prompt": img_prompt,
                                    "size": "2720x1536",
                                    "output_format": "jpeg",
                                    "watermark": False,
                                },
                            }
                        img_out = submit_and_wait_gmi_job(client, img_body, f"img_{lid}_{rid}_r{round_num}", max_wait_sec=120)
                        if img_out and img_out.exists():
                            # Copy to data/cache/rooms/{lid}_{rid}.jpg so local room cache is upgraded too
                            target_room_jpg = CACHE_DIR / "rooms" / f"{lid}_{rid}.jpg"
                            target_room_jpg.write_bytes(img_out.read_bytes())
                            print(f"[Worker 4] Upgraded room photo {target_room_jpg.name} via {img_model}")

            # Partition jobs across workers so each worker tackles different house segments first
            my_jobs = [j for idx, j in enumerate(priority_jobs) if (idx % 4) == (worker_id - 1)] + [
                j for idx, j in enumerate(priority_jobs) if (idx % 4) != (worker_id - 1)
            ]

            for job_i, job in enumerate(my_jobs):
                lid = job["listing_id"]
                seg_idx = job["seg_idx"]
                model = worker_models[(job_i + round_num - 1) % len(worker_models)]
                res = "1080p" if round_num >= 1 else "720p"
                dur = 8
                body = build_model_payload(
                    model=model,
                    prompt=job["prompt"],
                    first_frame_url=job["first_frame_url"],
                    last_frame_url=job["last_frame_url"],
                    duration=dur,
                    resolution=res,
                )
                prefix = f"{lid}_seg{seg_idx}"
                out_mp4 = submit_and_wait_gmi_job(client, body, prefix, max_wait_sec=360)
                if out_mp4 and out_mp4.exists() and out_mp4.stat().st_size > 20000:
                    register_ready_segment(
                        listing_id=lid,
                        seg_idx=seg_idx,
                        from_room=job["from_room"],
                        to_room=job["to_room"],
                        model=model,
                        local_path=out_mp4,
                    )
                    print(f"[Worker {worker_id}] Updated live tour for {lid} with {out_mp4.name}!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=int, default=1, help="Worker ID (1..4)")
    parser.add_argument("--rounds", type=int, default=25, help="Max rounds until token exhaustion")
    args = parser.parse_args()
    run_worker(args.worker, args.rounds)
