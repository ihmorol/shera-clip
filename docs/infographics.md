# Infographic videos: extension PRD, strategy, and architecture

**Status:** owner-directed extension, 2026-10-25 (in chat). Extends the [PRD](PRD.md) without replacing it.
**Authority chain:** the PRD still governs clip selection, approval, spend, and provenance. This document
specifies what happens **after** a clip is approved: turning it into a visual-first video for YouTube.
**Decisions:** D35–D38 in [decisions.md](decisions.md). **Acceptance:** gate A8 in [acceptance.md](acceptance.md).
Branch: `feat/infographic-video-pipeline` (extension work; not merged by instruction of the owner).

## 1. Problem and goal

An approved Shera Clip is a screen-recording excerpt with the teacher's voice. That is right for Facebook
and Shorts, but some approved moments read poorly on YouTube: the shared screen may be absent, unreadable
at 1080p, or visually dull, and the owner wants a **faceless, visual-first** way to publish the same
teaching. The owner directed (2026-10-25):

> From the decided (approved) clips, produce infographic videos. Another model designs the infographics.
> The audio is the original clip audio — no model changes the voice. The video runs exactly as long as the
> audio, and what the infographic shows must match what the voice is saying. N chosen clips produce N
> videos. The videos must be cheap, good, error-free, publishable to YouTube, and must not contain an
> intro or an ending. The user should not have to do much manual work; AI does most of the work.

Goal: after the operator approves clips (one explicit action), the app produces one finished,
YouTube-ready infographic video per approved clip with zero further required input.

## 2. Requirements

1. **One approved clip → one video.** The output count always equals the approved count; nothing is
   dropped, merged, or padded (PRD rule: never fill a quota; extended here: never inflate it).
2. **Voice untouched.** The audio track is the clip's own audio from `media.mp4`, stream-copied when AAC
   (same rule as D21). No TTS, no voice model, no denoise, no re-cutting of speech.
3. **Duration equals the audio.** The video track is assembled to exactly the audio's length; tolerance
   ±0.25 s (the A5 media tolerance).
4. **Visuals follow the speech.** Scenes are cut on transcript-line boundaries and each scene shows,
   in the spoken language, what the voice is saying during that scene. Text is drawn from the transcript
   only; the planner may compress and structure, never invent facts, numbers, names, or claims.
5. **Publishable to YouTube.** 1920×1080 (16:9), H.264 High/yuv420p, AAC audio, `+faststart`, a burned-in
   spoken-line caption so the video is watchable muted, and a first-frame poster image per clip.
6. **No intro, no outro, no filler.** No branded intro/outro cards are generated (none exist to use —
   PRD forbids inventing brand assets). Class logistics lines (greetings, chat prompts, farewells) are
   rendered as plain speech text only, and the auto-selected shortlist already excludes offtopic clips.
7. **Error-free output.** Every finished file passes automated QC before the UI may show it as done; a
   failing file is shown as failed with its report, never as done (DESIGN.md rule: never fake success).
8. **Cheap.** Rendering is local CPU. The only paid step is one small LLM call per clip through the
   existing ledger and the same USD 1.50 per-class cap (D11).
9. **Minimal manual work.** After "Approve the selected clips" (one click), generating all videos is one
   more click. Upstream, the app removes routine clicks: previews render automatically, AI criteria can
   apply without a pause, drafts are already prepared automatically (D9).

## 3. Strategy

The extension rides the existing pipeline instead of adding a second product:

```
import → transcript → authorize → transcribe → translate → criteria → candidates → score → prepare
                                                                                ↓
                                                        review (approve) ── the decision point
                                                                                ↓ (new)
        for each approved clip:  plan scenes (LLM, paid, ledgered)
                              → render slide PNGs (local headless browser)
                              → assemble video + original audio (local ffmpeg)
                              → QC gates → data/exports/<job>/infographics/NN-<cid>/
```

Manual-work reduction happens **upstream of approval** (auto-preview rendering, one-click shortlist
approval, optional auto-applied AI criteria) so the operator's remaining role is exactly the one the PRD
reserves for a human: watching and approving. Post-approval, everything is automatic.

## 4. Architecture

### 4.1 Modules

| Module | Responsibility |
| --- | --- |
| `shera/providers.py` | `scene_plan()`: one OpenRouter chat call per clip. In: the clip's transcript lines (as spoken + English), the operator's title, category, and profile intent. Out: a validated scene plan JSON. Ledger kind `infographic`. |
| `shera/infographics.py` | Pure logic + local rendering: clip transcript slicing, scene timing, plan validation/normalization, slide HTML (Jinja template), Playwright screenshots, ffmpeg assembly, QC, and per-clip report. |
| `shera/pipeline.py` | `infographic(cid)` orchestration (mirrors `draft()`): ledgered plan, render, QC, atomic per-clip output folder; `render_previews(job_id)` for auto-preview rendering. |
| `shera/app.py` | Routes: infographics page, generate-all, per-clip generate, state polling; job-page bulk approve; background task keys `info:{cid}`, `autorender:{job_id}`. |
| `shera/templates/infographics.html` | Results page: per-clip state, player, QC report, poster, duration readouts. |

### 4.2 Scene plan contract (planner output)

The planner receives the clip's transcript lines with absolute source times and must return JSON:

```json
{
  "headline": "Short on-screen title, in the spoken language",
  "scenes": [
    {"u0": 0, "u1": 2, "kind": "point",
     "heading": "…", "bullets": ["…"], "emphasis": "…", "note": "…"}
  ]
}
```

- `u0`/`u1` select a contiguous, gap-free range of the clip's transcript lines; together the scenes must
  cover every line of the clip exactly once (the renderer re-derives timing from these, so the audio and
  the visuals can never drift).
- `kind` ∈ `point | list | steps | example | mistake | definition | quote | comparison | chatter`.
  `chatter` renders logistics/speech-only lines as a quiet spoken-text card.
- `heading` ≤ 90 chars; `bullets` ≤ 5 items, each ≤ 110 chars; `emphasis` is a key phrase or number
  already said in the clip; `note` is an optional English gloss when the clip is Bangla.
- Validation is strict (wrong coverage, unknown kind, missing text → `ProviderError(billed=True)`);
  normalization clamps lengths and drops empty bullets. The planner is instructed to write Bangla text in
  Bangla, keep English terms, and never invent anything.

### 4.3 Timing model

All times are clip-relative seconds (`t − review.start`). Scene k spans
`[units[u0].start, units[u1+0].start)`; the first scene is clamped to 0 (leading silence belongs to the
first scene) and the last scene is clamped to the audio duration (trailing silence belongs to it). Gaps
between lines extend the previous scene. Scene count adapts: short clips get fewer, larger scenes.
The spoken-line captions use the same units, so caption, scene, and audio agree by construction.

### 4.4 Slide rendering

- One Jinja template (`slide.html`), self-contained inline CSS, palette lifted from DESIGN.md tokens
  (darkroom teal ground, ivory ink, orange mask accents, leader/safety for right/wrong panels).
- Fonts: the DESIGN.md system stack — **Nirmala UI** carries Bangla shaping (Windows system font, same
  font the ASS caption path already uses), Segoe UI for Latin, Noto Sans Bengali as declared fallback.
- Layout per `kind`: heading block, bullets (numbered for `steps`/`list`), emphasis chip, wrong/right
  split for `mistake`, two columns for `comparison`, large text for `quote`. A thin progress bar and
  scene index run along the bottom. No brand marks, no handles, no URLs.
- The browser is Playwright's Chromium using the installed **Edge channel** (`channel="msedge"`), so no
  browser download is needed on Windows; Chrome and a downloaded Chromium are fallbacks. Chromium shapes
  Bangla correctly (HarfBuzz), which is why slides are browser-rendered rather than drawn by ffmpeg
  drawtext or Pillow.

### 4.5 Video assembly (one ffmpeg invocation per clip)

- Inputs: N slide PNGs (`-loop 1`), the source `media.mp4` with `-ss {start}` before `-i`.
- Per scene: `scale` to 2× then `zoompan` Ken Burns (alternating in/out, ~1.06× over the scene) at
  30 fps → `concat` → `fade` in/out → `format=yuv420p`.
- Audio: `-map 0:a:0` of the source input, stream-copied when AAC, else AAC 192k (D21 rule).
- `-t {audio_duration}` caps the mux so video and audio end together; `+faststart`.
- Motion is deliberately conservative: smooth, slow, deterministic — no transitions that could show black
  between scenes, no animation frames that multiply render time. One scene ≈ one designed slide held on
  screen with gentle motion; the caption band carries the spoken line.

### 4.6 QC gates (A8, enforced in code)

A clip's output counts as **done** only when all of these pass; otherwise the task is `error` and the
report says which gate failed:

1. `media.verify(video, audio_duration, (1920, 1080))` — H.264/AAC, size, duration within ±0.25 s,
   stream start/end offsets within 0.2 s.
2. Scene coverage: validated plan, Σ scene durations == audio duration (by construction, re-checked).
3. Audio present and not silent: the clip source already passed `check_audible`; the report records the
   measured loudness envelope peak so a muxing mistake (silent video) cannot slip through.
4. Every scene has non-empty heading or spoken text; every PNG exists and is 1920×1080.
5. Report `report.json` next to the video records plan hash, timings, QC results, and cost.

### 4.7 Output layout

```
data/exports/<job>/infographics/
  index.json                  # one entry per clip: folder, cid, rank, title, duration, qc
  01-<cid>/
    video.mp4                 # 1920x1080, original audio, captions burned in
    poster.jpg                # first frame (thumbnail for YouTube)
    plan.json                 # the scene plan actually rendered
    report.json               # timings, QC results, cost, model
    slides/scene-01.png …     # the rendered slides (auditable, editable, re-runnable)
```

The infographics folder is separate from the clip export packages (those remain the 9:16 + 16:9 source
recordings). Job deletion removes both. Site companion exposes list/generate/state endpoints mirroring
the export endpoints.

## 5. Cost

| Step | Cost | Notes |
| --- | --- | --- |
| Scene plan | ~$0.001–0.002 per clip | small text-in/text-out call on `google/gemini-3.1-flash-lite` (the D25 translation model; strong Bangla) |
| Slide render | $0 | local CPU, one screenshot per scene |
| Assembly + QC | $0 | local ffmpeg |

Ten clips cost about one Jev scoring call. The ledger treats `infographic` like every other paid kind:
journaled before sending, replayed on resume, capped by the class authorization. With no OpenRouter key
configured the app falls back to the **offline planner** (`infographics.local_plan`): consecutive
transcript lines are grouped into ~15 s scenes headed by their first spoken line, no provider is called,
and the report records `planner: "local"` so the cheaper plans are never mistaken for model-designed
ones. `scripts/test_infographics_offline.py` renders test videos from existing jobs with a local
whisper transcription and the offline planner, touching no database rows and making no paid call.

## 6. Reduced manual work (D37)

| Before | After |
| --- | --- |
| Click "Render previews" on each of ~10 clips | Previews render automatically in the background once scoring finishes |
| Watch, then approve each clip individually | Clips still watched individually, but "Approve the selected clips" approves the whole shortlist in one explicit action (per-clip edit/reject still available) |
| Confirm AI-proposed criteria at a pause | When the operator checked "Let AI propose criteria" at import, the proposal can be applied without pausing (default follows the import choice) |
| Click export, then post | unchanged (manual posting is the boundary) + one click to generate all infographic videos |

Approval remains explicit and per-clip in effect: bulk approve requires current previews, any later edit
withdraws approval (existing rules apply unchanged).

## 7. Non-goals and limits

- No text-to-speech, voice cloning, translation of the audio, or re-timing of speech.
- No generative B-roll, images, characters, or music. Slides are typographic infographics.
- No auto-posting to YouTube; the file is prepared for manual upload (PRD boundary).
- Portrait 9:16 infographic variant is deferred (recorded in D36); the existing clip exports cover Shorts.
- No animated kinetics beyond Ken Burns and fades in this phase; the scene plan schema keeps room for
  richer per-scene animation later without another model call.
- Rendering needs a local Chromium-family browser (Edge on Windows qualifies). The page reports a setup
  gap like the ffmpeg/OpenRouter checks rather than failing silently.
