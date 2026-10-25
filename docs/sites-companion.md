# Sites and the local video companion

The owner changed the product direction on 2026-10-01: Shera Clip accepts
general video content, with built-in or custom selection criteria. IELTS is
one preset. A Sites interface connects to a companion running on each user's
computer; it does not use the project owner's computer as a shared backend.

The hosted source is in `site/public`. Video files, transcripts, SQLite jobs,
previews, exports, provider keys, and paid-call journals stay in the user's
local companion. Authorized transcription sends audio to OpenRouter;
translation, criteria proposals, scoring, and posting drafts send transcript
content to the configured providers. Processing is local; inference is not
claimed to be offline.

## Start on another computer

1. Download `companion.zip` from the site's first-time setup and extract it.
2. Install Python 3.12+ and FFmpeg with ffprobe and libass. Windows requires
   Nirmala UI for Bangla captions; other operating systems may need font
   configuration before caption rendering is reliable. Infographic videos
   (D35–D38) additionally render slides in a local Chromium-family browser:
   Microsoft Edge on Windows is used when present, or run
   `python -m playwright install chromium` once.
3. In the extracted folder, run `python -m pip install -e .`.
4. Copy `.env.example` to `.env`, configure `OPENROUTER_API_KEY`, and run
   `python -m shera`. Do not send the key to the site or paste it into chat.
5. Open the Sites URL, connect to `http://127.0.0.1:8765`, and paste the
   process-specific pairing code printed in the terminal. Allow the browser's
   local-network permission if it asks. Restarting the companion changes the
   code and requires reconnecting.

The companion accepts only loopback hosts and explicitly configured origins.
`SHERA_SITE_ORIGIN` overrides the default published Sites origin. The local
frontend development origin is `http://127.0.0.1:8877`. Pairing credentials are
kept in page memory. Signed media URLs last less than five minutes and permit
streaming range requests without publishing recordings.

## Workflow

Import a file or a direct public HTTPS video link. Optionally include a VTT
transcript and replacement audio with a file import. Select a preset and
duration range. Imports pause before paid processing. Set custom intent,
checks, categories, weights and score thresholds in the criteria editor.
When an imported transcript is available, request an AI criteria proposal
inside the existing $1.50 per-video authorization cap, then review and save it.
Criteria become immutable once candidates exist; re-import to rank with a
different rubric. Resume after proposing criteria, or authorize processing
directly when using user-defined criteria.

Browse the shortlist or all candidates, search their text, filter decisions,
and sort by rank or source time. Edit boundaries, captions, posting drafts,
title and portrait crop. Render both previews, watch them, then explicitly
approve or reject. Changes to rendered content withdraw an existing approval.
Export only approved clips and download their videos, subtitles, thumbnail,
posting text and source provenance.

## Current limits and evidence

- URL import supports direct HTTPS files up to 4 GiB, with public-address,
  DNS-pinning, TLS and redirect checks. YouTube and other watch pages are not
  automatically extracted. Download those files separately before importing.
- Selection reads transcripts. Silent video and visual-only events do not
  have a visual understanding pipeline. Every supported recording still
  needs operator video review; ranked scores do not guarantee best clips.
- Preview rendering uses FFmpeg and the current portrait/landscape pipeline.
  Large inputs depend on local disk, memory and processing speed.
- Infographic videos (D35–D38) render locally per approved clip: one paid
  scene-plan call per clip under the same per-video authorization cap, slides
  screenshot in a local browser, and every file passes media checks (codec,
  size, duration, stream offsets, audio presence) before it is offered. No
  voice is modelled or replaced; nothing is added at the start or the end.
- Browser-to-loopback connectivity depends on local-network browser support
  and permissions. Failed connections show an error; no cloud fallback exists.
- Regression and synthetic media checks do not establish real-world selection
  quality or publish-ready status. The existing real-media acceptance gates
  remain evidence requirements, with IELTS-specific quality rubrics requiring
  future domain-specific evaluation for other presets.
