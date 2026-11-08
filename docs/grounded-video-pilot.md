# Generated walkthrough pilot

The target is a newly generated, continuous camera walkthrough video inside the original Homi swipe feed. Photo slideshows and the floor-plan schematic are supporting research, not the requested video. No generated 94404 clip has been rendered or accepted yet.

Start with 140 Spinnaker's living room: source gallery indices 10 and 11 are overlapping views of the same seating area. Seven supporting views and floor-plan index 43 ground route selection and review. The pilot stays on the wooden living floor; it does not cross the lower tiled foyer or the dining table. Camera poses, dimensions and elevations are uncalibrated, so this is a six-second feasibility pilot rather than a verified whole-home reconstruction.

The finite runner submits one GMI Veo 3.1 job. Immediately before submission it compares both public input URLs with the acquired source hashes and blocks unavailable or changed images. It does not invoke the demo worker, generate replacement listing photos, retry models, create a slideshow, or burn through account balance. An interrupted or ambiguous submission blocks automatic resubmission to prevent duplicate spending. The model's [current GMI API documentation](https://docs.gmicloud.ai/model-quickstarts/video/veo-3-1-generate-001) says additional reference images are ignored when a frame image is supplied. Accordingly, the first/last photos are model inputs; the plan and extra views constrain the prompt and human review. This is not a geometrically enforced 3D render.

Prepare offline:

```sh
.venv/bin/python scripts/generate_grounded_video.py prepare
```

For rendering, configure an explicitly designated **project** credential as `HOMI_GMI_API_KEY` in this repository's ignored `.env`. Do not paste credentials into chat. Neither this runner nor source browsing reads a generic personal key. Then submit once and resume polling the same content-addressed job:

```sh
.venv/bin/python scripts/generate_grounded_video.py submit --credential-file .env
.venv/bin/python scripts/generate_grounded_video.py poll --credential-file .env
```

An explicitly designated project `api_key.md` is also supported with `--credential-file api_key.md`. It may contain `GMI_API_KEY=...`, `HOMI_GMI_API_KEY=...`, a bare key, or a GMI label with one key. Ambiguous multiple-key Markdown is rejected. The file stays ignored and is not copied into job artifacts or commits.

`prepare` prints the job directory. After successful generation, inspect it offline:

```sh
.venv/bin/python scripts/review_grounded_video.py data/94404/video_jobs/JOB_ID
```

The review bundle includes sampled frames, source endpoint comparisons, decode/timing checks and a pending review template. Endpoint similarity and byte hashes cannot establish intermediate-view fidelity. Watch the full clip and inspect its frames against all source views: fixed walls/openings, furniture and finishes must persist; reject invented space, furniture collisions, morphs, cuts, crossfades and flat photo animation. Check parallax and occlusion. The original 3:2 photos may be cropped or extended by 16:9 generation, which also requires review.

Only an accepted clip with recorded appearance, layout and motion passes, reviewer notes, matching source hashes and matching MP4 hash may enter `data/94404/generated_videos.json`. Copy its MP4 into the ignored `data/94404/videos/` directory and use the review template's registry structure. The source feed serves accepted videos through the existing reel player. Unreviewed, rejected, missing or modified outputs never become a home's video. Accepting this pilot does not complete the ten-house task or verify a full 3D reconstruction.

Validation on November 7, 2026: the initial 41 automated tests passed. The real feed's desktop/mobile browsing, model research, return navigation and all 147 served original-image hashes passed. A separate temporary-data Chromium test confirmed native video playback, seeking, sound and paused/playing state across research; its test-pattern video was never added to production listings. Both public endpoint image URLs returned the acquired original hashes. These checks validate the pipeline and integration, not a generated property's appearance.

The user subsequently designated the project's ignored `api_key.md`. Its key passed authenticated GMI request-list access (HTTP 200). The single live pilot submission was rejected with HTTP 402 (payment required); no video was accepted or rendered. The job records the rejection and disables automatic resubmission. Resolve project billing/available credit in GMI before reconciling and retrying this same pilot. No personal credential was used, and the project key was never displayed or copied into tracked files.
