# Product requirements: Shera Clip

**Status:** owner-confirmed product scope, 2026-09-25

**Authority:** this document controls product behavior and acceptance. `docs/decisions.md` records the owner's choices; `docs/acceptance.md` expands the evidence gates. Historical plans are research, not competing instructions.
**Product stage:** specification only; no application code or real-class fixtures are in this repository.

## Problem Statement

A two- to three-hour Rimons IELTS Zoom class contains useful explanations, but turning it into social clips requires finding complete moments, checking context, framing slide-heavy video for a phone, correcting mixed Bangla/English captions, and preparing posting text. Doing this manually takes too much time. A clip that merely renders successfully may still be unreadable, misleading, incomplete, or unsuitable to publish.

The operator needs a dependable local workflow that prepares a small, strong shortlist and posting packages while retaining final human approval. The business goal is to reach current and prospective IELTS students through the Rimons IELTS Facebook Page and YouTube channel. Reach and student inquiries are measured from actual posts, not inferred from model scores.

## Solution

The app runs in the operator's browser against a server bound to `127.0.0.1`. The operator connects a read-only Zoom cloud-recording integration when ready, chooses a completed class, and the app imports its teaching video and available transcript. Local MP4/VTT import remains available. It aligns or transcribes speech, proposes complete teaching moments, ranks and categorizes them, and prepares phone-sized video previews, captions, and posting drafts. The operator reviews each shortlisted clip, edits where necessary, and explicitly approves it. The app exports an auditable, editable package for manual posting to Facebook and YouTube.

The priority order is **publishable clips > less manual work > low cost > speed**. Routine review should take at most 30 minutes per class in the pilot, measured separately from initial setup, calibration labeling, and manual platform upload. This is a target to test, not a reason to bypass approval or weaken quality.

## User Stories

### Source and setup

1. As the operator, I want the app to run only on my laptop, so that class media and job state remain under my control.
2. As the operator, I want clear first-run setup for Zoom and paid providers, so that I know which connection is missing without exposing credentials.
3. As the operator, I want to see completed recordings from the authorized Zoom account, so that I can select a class without downloading files manually.
4. As the operator, I want to refresh and search recordings by host, date, or title, so that I can find the intended occurrence.
5. As the operator, I want to see available video layouts and transcript status before import, so that I do not process the wrong recording file.
6. As the operator, I want the app to prefer the recording that preserves screen sharing and the teacher, so that teaching content remains visible.
7. As the operator, I want local MP4/VTT import as a fallback, so that a Zoom access problem does not stop work on a class I already have.
8. As the operator, I want download progress, disk estimates, integrity checks, and restart recovery, so that a large class can be imported reliably.

### Transcript and candidate discovery

9. As the operator, I want Zoom VTT used when it is accurate, so that I avoid unnecessary transcription cost.
10. As the operator, I want missing or poorly aligned transcript text flagged before ranking, so that the app does not cut the wrong speech.
11. As the operator, I want a visible estimate and one authorization for all paid work within a hard per-class cap, so that I control spend without approving every request.
12. As the operator, I want a resumable paid transcription fallback for unusable VTT, so that mixed Bangla/English classes can still be processed.
13. As the operator, I want the spoken languages preserved in the transcript, so that captions do not silently translate or rewrite teaching content.
14. As the operator, I want candidate moments to include a complete point and useful context, so that a hook is not cut off from its explanation.
15. As the operator, I want candidates aligned to the original recording timeline, so that the preview and export show the exact chosen moment.
16. As the operator, I want silence and duplicate candidates filtered automatically, so that I spend review time on distinct teaching moments.

### Ranking and review

17. As the operator, I want roughly ten strongest candidates ranked, so that I can review a manageable shortlist.
18. As the operator, I want educational value, standalone clarity, and opening strength shown separately, so that I understand why a clip was suggested.
19. As the operator, I want one primary category and optional IELTS topic tags, so that the posting package is organized.
20. As the operator, I want weak or uncertain candidates visible but outside the normal shortlist, so that the app does not silently discard possible lessons.
21. As the operator, I want a playable source preview with transcript, waveform, and source time, so that I can verify the content quickly.
22. As the operator, I want to change clip boundaries without truncating words or the teaching point, so that the result stands alone.
23. As the operator, I want the app to prepare a readable portrait layout and show it at phone size, so that Word and slide text are actually legible.
24. As the operator, I want to approve or reject each proposed clip and preserve those choices across restarts, so that only my approved work enters export.
25. As the operator, I want zero output when a class has no strong moments, so that the system never fills a quota with weak clips.

### Captions, posting package, and export

26. As the operator, I want editable Bangla/English captions with visible placement on the preview, so that I can correct model errors before export.
27. As the operator, I want an editable subtitle file and approved visible captions rendered into the video by default, so that the package works across posting workflows.
28. As the operator, I want editable title, description, and modest CTA drafts, so that I do not write every post from scratch.
29. As the operator, I want separate Facebook and YouTube posting fields based on the same approved clip, so that platform formatting does not require rework.
30. As the operator, I want the app to omit missing logos, handles, and links, so that it never fabricates Rimons IELTS assets.
31. As the operator, I want a 9:16 H.264/AAC video, thumbnail, subtitles, metadata, source time, and category in one package, so that manual posting is straightforward.
32. As the operator, I want export failures to be recoverable without repeating completed paid calls, so that a render error does not waste money or prior review.
33. As the operator, I want an explicit delete action and storage view, so that I control local copies of recordings and exports.
34. As the operator, I want to record post URLs and optional reach metrics later, so that actual performance can inform future decisions without blocking export.

### Proof and maintenance

35. As the product owner, I want selection measured on untouched real classes and human labels, so that a convincing demo is not mistaken for a reliable selector.
36. As the product owner, I want private Facebook and YouTube previews checked before a publish-ready claim, so that platform-specific failures are caught without public posting.
37. As the product owner, I want product decisions and evidence linked from issues and pull requests, so that an agent cannot silently change a requirement or assert an untested result.

## Implementation Decisions

- **Source integration:** A read-only Zoom Server-to-Server OAuth app is the intended path for recordings in the authorized account. Set it up when implementation needs access. Poll on app open and explicit refresh; a public webhook receiver is outside the local-only MVP. Retain local-file import. Build order (D15): local MP4/VTT import first for the phase-1 prototype, Zoom API import in phase 2, before any publish-ready claim.
- **Recording choice:** Treat each meeting occurrence separately. Prefer a shared-screen-with-speaker video; show a choice when multiple layouts materially differ. Pair the selected MP4 with its VTT when available. Never assume one MP4 per meeting.
- **Media timeline:** Store clip boundaries as zero-based seconds on the original media presentation timeline with a source hash. Do not use rounded frame numbers as identity. Cut from original media with accurate short-span decode/re-encode and verify playback, audio, and first/last words.
- **Transcript:** Parse real VTT cues and speaker text, normalize rolling captions, and check beginning/middle/end alignment within one second. Zoom's cloud-recording audio transcript is English-only; test mixed-language material. If unusable, estimate and explicitly authorize paid transcription, split requests below provider file limits, restore absolute offsets, and flag joins and uncertain results. Preserve the spoken language; translation is a separate reviewable option.
- **Candidates:** Generate complete teaching moments around speech and sentence boundaries with context, not rigid 30-second final cuts. Logical analysis windows may overlap; video chunks are not a scoring prerequisite. Deduplicate by source and absolute time.
- **Rank policy:** Jev supplies typed scores for educational value, standalone clarity, and opening strength on described 0–4 scales, plus a mutually exclusive primary category. Start with `0.45 × value/4 + 0.35 × clarity/4 + 0.20 × opening/4`, tie-breaking by earlier source time. The weights are provisional; any quality-rule change requires owner approval after calibration evidence. Do not invent prose rationales from Jev. Show scores and supporting source text.
- **Taxonomy:** Primary categories are Exam tip, Worked example, Common mistake and correction, Vocabulary/phrase, Practice exercise, and Other. Optional tags include IELTS module, task type, skill, and level. The operator can edit both.
- **Quality policy:** A clip must provide a complete, accurate, relevant takeaway with a useful opening. No clickbait, cut-off words, missing teaching content, knowingly wrong captions, or unreviewed private details. Prioritize teaching truth over a dramatic excerpt. Do not manufacture three clips from weak material.
- **Duration:** Target 15–45 seconds, normally allow up to 60 seconds, and flag longer complete explanations for operator choice instead of truncating them.
- **Review:** Auto-prepare about ten previews and drafts, then require per-clip human approval. Provide quick approve/edit/reject controls and focus manual attention on flagged problems. Treat recording permission as settled; there is no separate per-clip permission workflow.
- **Portrait composition:** Readable slide or Word content comes first. Keep or reposition the teacher's corner video where practical. A scaled full-frame layout is acceptable only when phone-preview text is legible; any crop must not hide teaching content. Caption placement must not obscure it.
- **Captions:** Preserve Bangla and English as spoken. Provide editable timed subtitles and a subtitle file; visible captions are the default for approved exports after correction.
- **Posting drafts:** A separate OpenRouter generative model receives only the selected clip excerpt and category to draft editable Facebook and YouTube title, description, and modest CTA text. Jev does not generate prose. Avoid invented score, admission, or outcome claims. Omit unsupplied logos, handles, URLs, and examples.
- **Export package:** Approved clips only. Include portrait H.264/AAC MP4, subtitle file, thumbnail, platform posting fields, category/tags, source/time provenance, and machine-readable posting index. Manual upload is the boundary; no automatic public post.
- **Job and cost state:** Store immutable source and candidate records separately from editable review state and final manifest. Journal paid calls before sending; completed work is not re-billed on restart. Indeterminate sent calls pause for reconciliation. A single per-class authorization covers paid calls up to a hard USD 1.50 cap; stop before exceeding it and preserve partial work.
- **Security and storage:** Bind only to loopback, keep media and state locally, keep provider secrets out of browser responses, logs, exports, and Git, and provide explicit job deletion. No cloud backend, remote database, account system, or telemetry.
- **Model/provider failure:** Never fabricate rankings or titles when a provider fails. A poor real Bangla/English transcription sample triggers measured alternatives for owner decision before a provider or spend-policy change.

## Testing Decisions

The highest evidence seam is the **operator's browser workflow from source selection through approved export and private platform preview**. Tests should assert observable media, cost, state, and review behavior rather than mock internal function calls. No application test suite exists yet.

- Run media integration tests on real and synthetic FFmpeg fixtures, including variable frame rate, nonzero stream start, silent segments, long recordings, and first/last-second decode. Compare early, middle, and late clips against the original source.
- Run VTT and fallback-transcription tests on consent-cleared Zoom examples, rolling captions, missing/bad cues, mixed Bangla/English samples, and chunk joins. Check sampled audio/cue alignment within one second.
- Run provider-contract tests with fake responses, then one authenticated Jev typed-decision smoke test and a short timestamped transcription smoke test. Check actual prices and provider data handling at implementation time.
- Run job-state scenarios for import interruption, browser refresh, process restart, budget exhaustion, timeout after send, boundary edits, rejection, and render failure. Verify no replay of durably completed paid work.
- Run a real-browser pilot on three classes: two for calibration, one untouched held-out, with at least 60 independently human-labeled candidate moments and at least 20 held-out labels. At least seven of the held-out top ten must meet the written worth-reviewing rubric, and at least three must become approved clips after video review. If the gate fails, revise on calibration data and use a new held-out class; do not lower the bar silently.
- Measure routine review minutes per class against the 30-minute target; record actual per-stage cost and time. If a real class yields fewer than three suitable moments, report the failure instead of forcing output.
- Inspect private YouTube and nonpublic Facebook previews with the operator when account features allow. If a platform cannot provide a nonpublic preview, record that limitation; do not claim that platform gate passed.

Detailed evidence and pass conditions are in `docs/acceptance.md`.

## Out of Scope

Public hosting, cloud database, user accounts, cross-device sync, public webhook receiver, automated posting, unattended approval, automatic revenue prediction, face tracking, generative B-roll, whole-class video re-encoding, and collecting platform analytics through APIs are outside the MVP. No product requirement authorizes agents to make or relax business, quality, visual, external-spend, or acceptance decisions.

## Further Notes

- The repository contains no class media, labels, API credentials, verified brand assets, or running application. These are explicit implementation prerequisites, not material to fabricate.
- Zoom API access must be established in the same account that hosts the recordings. Normal Zoom sign-in credentials are not the integration contract. See `docs/zoom-setup.md`.
- The first one-class workflow may be called a prototype. The publish-ready claim requires all real-class and platform gates above.
- The owner approved the product decisions through a four-round `grill-me` interview on 2026-09-25. Changes to them require a linked decision record and owner approval.
- Official references: [Zoom cloud recording API](https://developers.zoom.us/docs/api/meetings/), [Zoom transcription limits](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0065911), [OpenRouter Jev guide](https://openrouter.ai/blog/tutorials/how-to-use-jev/), [OpenAI file transcription guide](https://developers.openai.com/api/docs/guides/speech-to-text), and [FFmpeg documentation](https://ffmpeg.org/ffmpeg.html). API availability and pricing must be rechecked at implementation time.
