# Generated walkthrough pilot

The target is a newly generated continuous camera walkthrough inside the original Homi swipe feed. Photo slideshows and the floor-plan schematic remain supporting research. A six-second pilot uses 140 Spinnaker living-room photos 10 and 11, seven supporting views and floor-plan photo 43 for route selection and review.

Video uses **gemini-omni-1.2-flash** through Google's Interactions API. The [current video guide](https://ai.google.dev/gemini-api/docs/omni) documents first/last-frame transitions of 3–10 seconds, up to six reference images, and video extension. Argon is excluded; Gemini 3.8 Flash handles planning and Gemini 3.8 Flash TTS handles speech. The screenshot's chat menu does not establish API video access. Multiple images alone do not establish calibrated geometry.

The pilot uploads exact hash-verified JPEG bytes. The floor plan constrains the route and review rather than enforcing geometry. The camera stays on the wooden living-room platform, outside the seating group, without crossing the lower tiled foyer or dining table. Camera poses, dimensions and elevations remain uncalibrated.

Use the explicitly designated Gemini section of this repo's ignored api_key.md, or HOMI_GEMINI_API_KEY in a project .env. Gemini key assignments inside that project file are also supported. Other provider sections and personal credential stores are excluded. Credentials never enter the browser, job artifacts, logs or commits.

```sh
.venv/bin/python scripts/generate_grounded_video.py prepare
.venv/bin/python scripts/generate_grounded_video.py submit --credential-file api_key.md
.venv/bin/python scripts/generate_grounded_video.py poll --credential-file api_key.md
```

One submission creates a resumable Gemini interaction. Ambiguous interrupted submissions block automatic retries. Provider/model/input changes create a distinct content-addressed job. Historical operation IDs are never sent to Gemini. New output remains unreviewed until inspected.

After generation, use the printed job directory:

```sh
.venv/bin/python scripts/review_grounded_video.py data/94404/video_jobs/JOB_ID
```

The review verifies source/video hashes, fully decodes the clip, checks duration, and extracts nine exact frames including endpoints. It produces contact sheets, source comparisons and a pending registry candidate. Similarity/temporal metrics cannot validate novel views or genuine camera motion.

Watch and scrub the whole clip against all source views. Require stable walls, openings, furniture, finishes and lighting, with depth-dependent parallax and occlusion. Reject invented space, furniture collisions, morphs, cuts, crossfades and flat photo animation. Inspect cropping/extension of the original 3:2 photos in 16:9 output. Do not cross the unmeasured raised-floor edge.

Only visually accepted output with appearance/layout/motion passes, reviewer notes, matching original hashes and matching MP4 hash may enter data/94404/generated_videos.json. Copy the MP4 into the ignored data/94404/videos directory and complete the pending review candidate. Accepted clips play in the original reel. This pilot does not complete the ten-house selection or establish a whole-home 3D reconstruction.

On November 7, 2026 the project Gemini key authenticated and its catalog included Omni 1.2 Flash, Flash 3.8 and Flash 3.8 TTS. Prior verification covered all 147 original images, desktop/mobile feed navigation, and isolated native video playback. Actual generated-video fidelity requires separate review. Historical cached videos retain their original provenance; live GMI calls have been removed.

Live probe: one six-second request to Omni 1.2 Flash and one explicit compatibility attempt with Omni 1.1 Flash were accepted as background interactions, then both ended with `RESOURCE_EXHAUSTED`. No video was produced or accepted. Check the Gemini project's usage/quota/billing and service capacity before another attempt. The app preserves each interaction ID, reports the failure safely and does not automatically resubmit. Omni 1.2 remains the default; 1.1 is an explicit compatibility choice. The migration passed 89 automated tests plus the desktop/mobile feed and 147 original-image integrity checks.
