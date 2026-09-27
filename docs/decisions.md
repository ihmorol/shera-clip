# Confirmed decisions and change control

**Owner confirmation:** 2026-09-25, after four rounds of `grill-me`.
**Authority:** [PRD](PRD.md) describes required behavior. This record explains choices and tells agents which inputs remain pending. An implementation note or historical plan cannot override either document.

| ID | Decision |
| --- | --- |
| D01 | Use MVP v2 as the starting analysis, then consolidate into one canonical PRD. The older architecture plans and v2 file are historical. |
| D02 | Prioritize publishable clips, minimal manual work, low cost, then speed. Serve current and prospective IELTS students and improve Rimons IELTS Facebook/YouTube reach. |
| D03 | One operator uses a laptop-hosted browser app at loopback. No cloud backend, accounts, or automatic public posting. |
| D04 | Import completed Zoom cloud recordings by API through a read-only account app when credentials are set up; list and choose one occurrence. Retain local MP4/VTT fallback. |
| D05 | Preserve original-media absolute time, accurate short-span cuts, resumable jobs, and auditable source and cost records. |
| D06 | Jev ranks self-contained, accurate teaching moments. Default weights are provisional and can change only after human-label evidence and owner approval. About ten candidates enter normal review; three approved clips is the aim, not a forced quota. |
| D07 | Target 15–45 seconds, normally up to 60. Flag longer complete explanations for the operator instead of truncating a thought. Weak classes may yield zero clips. |
| D08 | Slide/Word readability takes priority over the teacher inset in portrait composition. Captions preserve spoken Bangla and English, are editable, and are visible by default on approved clips. |
| D09 | Automatically prepare previews, captions, layout, and posting drafts. The operator explicitly approves each exported clip. Recording-use permission is settled; there is no separate per-clip permission workflow. |
| D10 | A separate OpenRouter text model drafts editable Facebook/YouTube title, description, and modest CTA from the selected excerpt and category. Do not invent brand assets, handles, links, or outcome claims. |
| D11 | One per-class authorization covers paid calls inside a hard USD 1.50 cap. Stop before crossing it. Routine review target is 30 minutes per class; measure it without weakening quality. |
| D12 | Keep local jobs until explicit deletion. Save post URLs and offer optional manual performance metrics; neither blocks package export. |
| D13 | The one-class prototype is distinct from publish-ready. Publish-ready requires three classes, 60 independent human labels, at least 7 worthwhile held-out top-ten suggestions, 3 approved held-out clips, media checks, and user-assisted private platform previews. |
| D14 | Agents may choose routine implementation details. Changes to product scope, quality rules, UI wording/layout, external spend, or acceptance criteria require owner decision. |
| D15 | 2026-09-26, [#6](https://github.com/ihmorol/shera-clip/issues/6): Build local MP4/VTT import first; the phase-1 working prototype does not need Zoom credentials. Zoom API listing and import follow in phase 2. Gate A1 still requires Zoom API import before publish-ready. |
| D16 | 2026-09-27, [#7](https://github.com/ihmorol/shera-clip/issues/7), owner delegated the choice: Python + FastAPI + SQLite + FFmpeg CLI, server-rendered pages with small vanilla JS modules. Move the review screen to a Vite + TypeScript frontend only if the plain editor becomes hard to maintain. |
| D17 | 2026-09-27, [#8](https://github.com/ihmorol/shera-clip/issues/8), owner delegated the choice: candidates are deterministic windows of whole transcript units (15–60 s, overlapping starts). Jev scores each window. Times come only from the transcript. Overlapping candidates are suppressed after ranking. The normal shortlist holds at most ten candidates with value ≥ 2 and clarity ≥ 2; others stay visible outside it, so a weak class can yield zero. Model-proposed spans are deferred until calibration labels show boundary problems. |
| D18 | 2026-09-27, [#9](https://github.com/ihmorol/shera-clip/issues/9), owner delegated an interim choice: each clip offers a scaled full frame (default) or an operator-set crop box with an optional repositioned teacher inset. The operator picks per clip from the phone-size preview. The real-recording phone readability check remains open under gate A5. |
| D19 | 2026-09-27: The paid transcription fallback uses OpenAI `whisper-1` with segment timestamps, the only OpenAI transcription model that returns timestamps (checked 2026-09-27). Posting drafts use a configurable OpenRouter text model. Recheck prices at implementation time; the USD 1.50 cap is enforced from recorded provider cost. |
| D20 | 2026-09-27, owner: use only OpenRouter with one API key. Speech-to-text goes through OpenRouter `/api/v1/audio/transcriptions` with segment timestamps. The default model is `openai/whisper-large-v3` (stronger on Bangla), with one retry on `openai/whisper-1` if the routed provider rejects timestamps (HTTP 400, unbilled). This replaces the OpenAI-direct part of D19. |
| D21 | 2026-09-27, owner: every approved clip exports in two versions, portrait 9:16 (1080×1920, title band, captions) and landscape 16:9 (1920×1080, whole source frame, captions only; a title over the frame would cover slide text). The review preview shows both. The source audio is kept as recorded: the AAC stream is copied, not resampled, downmixed, or re-encoded. |
| D22 | 2026-09-27, owner: a (nearly) silent recording stops before authorization with a clear error, so no paid transcription is spent on silence. The owner asked for a slicker, less confusing interface with a distinctive color; the new theme is recorded in `docs/ui-theme.md`. |
| D23 | 2026-09-27, owner: a class may be imported with its Zoom audio recording (.m4a). That audio replaces the video's own sound (OBS captures can be silent or poor). It is lined up automatically, by matching sound when the video has audio, else by the two files' recording clocks (about 1 s), and stream-copied so the samples are never re-encoded. The reviewer sees why each clip was suggested: one or two short lines in the clip list, and an "About this clip" block (what it teaches, the scorer's rubric reasons, what to check) inside the fixed preview panel without making it taller. An AI posting draft fills an empty on-video title. |

## Inputs pending, not permission to guess

- A read-only Zoom Server-to-Server OAuth app in the account hosting the recordings will be set up when implementation needs it. Normal Zoom sign-in credentials must not be used as the application integration.
- Three representative, consent-cleared classes and human labels are needed for quality proof. They are not in this repository. Keep actual media, VTT, labels containing personal information, and exports out of Git.
- OpenRouter and paid transcription credentials are needed for authenticated tests. Never request secrets in an issue or chat transcript and never commit them.
- Rimons IELTS logo, handle, URLs, and example posts may be supplied later. If absent, omit video marks and specific links.
- A durable visual identity is recorded in `PRODUCT.md` and the UI theme record when settled ([#5](https://github.com/ihmorol/shera-clip/issues/5)). Its absence does not alter the product contract.

## How decisions change

Open a GitHub issue titled `Decision: ...`, describe the current rule, proposed change, evidence and user impact, and obtain the owner's answer. Update this record, the PRD, acceptance checks, and UI record in the same pull request where applicable. Never silently lower a gate after a failed pilot. Keep external API prices and availability as dated verification facts, not permanent product promises.
