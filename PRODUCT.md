# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Python 3.12+, FastAPI, SQLite, and the FFmpeg CLI, with server-rendered pages and small vanilla JS modules (D16). The browser interface is served from the operator's laptop on `127.0.0.1`.

## Users

One operator prepares clips for Rimons IELTS. The viewers are current and prospective IELTS students on the Rimons IELTS Facebook Page and YouTube channel.

## Product Purpose

Turn two- to three-hour, slide-heavy Zoom classes into accurate, self-contained, approved teaching clips and editable posting packages. Success means clips a person can publish, plus an efficient review process; successful API calls alone are insufficient.

## Operating Context

The operator works on a laptop. Classes are Zoom cloud recordings of slides, Word documents, or similar teaching material with a small teacher video in a corner. The app lists completed recordings through the Zoom API and can import a local MP4/VTT pair. The operator reviews suggested moments and manually uploads approved exports to Facebook and YouTube.

## Capabilities and Constraints

- Priority: publishable clips, minimal manual work, low cost, then processing speed.
- The app binds to loopback and keeps working files locally. It has no user accounts, remote database, cloud deployment, or automatic publishing.
- External services are Zoom for source import, OpenRouter Jev for ranking, a separate OpenRouter text model for editable posting drafts, and OpenRouter speech-to-text when Zoom text is unusable. One OpenRouter key covers all paid calls (D20).
- External paid calls require one per-class authorization and share a hard USD 1.50 cap.
- Clip quality, mixed Bangla/English captions, slide readability, and explicit operator approval are product requirements.
- The owner has stated permission to use the recordings. Each exported clip still receives quality and visible-content review.

## Brand Commitments

The product serves Rimons IELTS. Posting copy must be helpful, accurate, and avoid unsupported score or admission claims. No logo, handle, URL, or example post has been supplied; the app must not invent one.

## Evidence on Hand

The approved conversation decisions are recorded in `docs/decisions.md`. Historical architecture plans exist in `plans/` and `.omx/plans/`. No application code, representative media, class labels, approved brand assets, or live API test evidence is present in this workspace.

## Product Principles

1. Teach something true and complete before optimizing the hook.
2. Prepare work automatically, then ask the operator to decide on the shortlist.
3. Keep slide or document content readable on a phone.
4. Make source, cost, and review state visible and recoverable.
5. Do not call the selector publish-ready until the agreed real-class gate passes.
