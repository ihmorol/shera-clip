# Acceptance and evidence plan

The [PRD](PRD.md) is the product authority. This document defines observable proof. A build, passing unit tests, or a valid MP4 alone does not establish that the tool produces publishable clips.

## Test seam

Use the highest useful seam: an operator starts in the local browser or the `shera` CLI (D29), imports a real class, reviews candidates, approves clips in the review UI, downloads a package, and checks private platform previews. Synthetic media and fake provider responses cover repeatable failures; real classes and authenticated provider calls establish the product claim. Store only sanitized fixture descriptions and evidence summaries in Git.

## Gates

| Gate | Required evidence |
| --- | --- |
| A1: local import and recovery | Server listens on `127.0.0.1` only and is unreachable from another LAN device. Import one representative 2–3 hour Zoom cloud recording through the API, plus one local fallback pair. Confirm the selected meeting occurrence and MP4 layout, file size/hash, progress, restart recovery, and actionable errors for wrong VTT, incomplete download, unsupported media, or lost Zoom authorization. |
| A2: transcript | Show source and language. At audible words near start, middle, and end, cues align within ±1 second or are corrected before ranking. A missing/bad Zoom VTT triggers an estimate, one authorization, and a real full-class paid fallback kept under the USD 1.50 cap. Each request respects the provider file limit; chunk joins have no unreported gaps or duplicates. Mixed Bangla/English accuracy is judged on real material. |
| A3: selection quality | Freeze three representative classes before tuning: two calibration, one untouched held-out. Humans independently label at least 60 candidate moments total, including 20 held-out. On the held-out class, at least 7 of the top 10 meet the written worth-reviewing rubric and at least 3 become approved clips after video review. Report the number available and failures honestly. If the gate fails, revise only on calibration data, then use a new held-out class. |
| A4: review and content | Each approved clip is a complete, accurate IELTS point with an intelligible opening/closing, readable teaching content, correct editable mixed-language captions, one primary category, posting drafts reviewed by the operator, and source provenance. No weak filler, knowingly inaccurate claim, missing slide content, or unreviewed private detail is approved. Review state survives refresh/restart. |
| A5: media | Every export is decodable H.264/AAC at 9:16 and within its chosen duration. Check audio/video stream start and end offsets within 200 ms, then watch at least three early/middle/late exports beside the source. Check first/last words, audible clarity, lip sync where a face speaks, phone-sized slide text, caption position, and title legibility. Instrumental probe output alone is insufficient. |
| A6: state and spend | Restart after import, approval/rejection, boundary edit, render error, budget stop, and an uncertain sent API request. No durably completed paid call repeats. Indeterminate calls stay reserved until reconciled or the operator chooses a retry. One class cannot exceed USD 1.50 authorized external spend. Time routine review separately and compare it to the 30-minute target. |
| A7: posting package | One approved package contains video, subtitle file, thumbnail, editable Facebook/YouTube copy, category, source/time, and index. The operator checks an unlisted/private YouTube Short and a nonpublic Facebook Page draft/test where the account permits it. Check video, audio, framing, captions, and title on both previews. If Facebook offers no nonpublic path, record the blocked platform gate rather than claim it passed. No public post is required. |

## Worth-reviewing rubric

A candidate passes the transcript-level label only when it is relevant to IELTS, has a usable opening, explains one complete teaching point, and has a concrete takeaway or worked example. Mark incomplete context, repetition, generic encouragement, off-topic talk, and misleading hooks as failures. Labelers separately flag audio, visual, caption, factual, private-detail, and rights problems after watching the video. Jev sees text only; its confidence does not replace these judgments.

## Pilot record

For each class record a non-identifying sample ID, source hash, recording layout, transcript source, model/rubric versions, reviewer, number of candidates, label split, top-ten verdicts, approved clips, export checksums, real spend by provider, stage times, routine review minutes, platform-preview evidence, and defects. Do not upload original recordings, student identifiers, API responses containing private text, or secrets to GitHub.

The first complete one-class run may be called a **working prototype**. Use **publish-ready** only when A1–A7 are supported by current evidence; state any blocked platform gate explicitly.
