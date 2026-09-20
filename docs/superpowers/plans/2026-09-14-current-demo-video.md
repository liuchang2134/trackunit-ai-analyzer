# Current v9 Demonstration Video Plan

> Execute inline. Capture the existing approved 8892 browser only. No new service, provider requests, extension installation, commits, publishing or changes to sealed software/documents.

**Goal:** Deliver a five-minute Chinese-captioned video of the current `.11` prototype using actual UI images and local playback capture.

**Architecture:** Capture bounded, explicitly synthetic UI states with CUA. Compose those real frames and one short animated work-state sequence with the installed FFmpeg. Caption the edited nature and current gaps; do not fabricate a successful Gemini result or an XGSS manual.

**Tech Stack:** Existing CUA browser, installed FFmpeg 7.1, Python standard library for timeline/ASS/SRT metadata. No added paid service or voice dependency.

## Constraints

- Show only explicit SIM devices. Never capture the data page's registered real serial, private messages or credentials into distributed footage.
- Keep Gemini unchanged and do not submit analysis. The daily-quota message is a prior recorded result, not a live availability test.
- Use actual local numerical-model output; include false alarms and the lack of field validation.
- Preserve v9 ZIP and competition documents. Name the video separately and describe it as edited actual UI frames plus local playback, with Chinese subtitles and no voiceover.
- Keep the browser's default viewport unchanged. Capture at its natural 552×614 size; compose a 1080×1440 video without distorting screenshots. No filesystem deletion or service restart.

## Task 1: Capture current behavior

- [x] Inspect current runtime, reuse the live browser and capture synthetic device finder, evidence/window/table, fault material and accurate pre-submit AI handoff.
- [x] Capture cooling warning, comparison, evaluation and same-device/time handoff. Capture approximately 12 seconds of actual work-state playback using timestamped CUA screenshots; stop playback afterward.
- [x] Save capture metadata, inspect every selected still, and ensure screenshots contain no registered real-device details. Default browser viewport remained unchanged. Actual playback recorded 466 frames in 12.024 seconds and was paused via its visible control.

## Task 2: Build a reviewable video

- [x] Create `.tmp/demo-video-v9/build_video.py` and timeline JSON with current captions, durations totalling 300 seconds, original frame paths and provenance. Generate `.ass` and `.srt` captions in UTF-8.
- [x] Use installed `.tmp/video-tools/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe` to encode a new 1080×1440 H.264/yuv420p MP4 at 25 fps with burned-in Chinese subtitles, preserving source frame aspect ratios.
- [x] Decode representative frames including all chapter changes; verify readable, unclipped captions, original UI, no fake model result and no confidential screen content. Check actual duration and stream properties.

## Task 3: Deliver and record limits

- [x] Save the reviewed MP4, SRT and short companion note under `docs`; record hashes, duration, capture times/build, content coverage and omitted live gates in `docs/evaluation/2026-09-14-demo-video-v9.{md,json}`.
- [x] Update current README/acceptance links. Keep older videos and sealed documents unchanged. This closes the current demonstration-video deliverable only; real API and complete business acceptance remain pending.
