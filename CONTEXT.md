# Shera Clip domain context

This is the vocabulary for the single product context. The [PRD](docs/PRD.md) remains the behavior authority.

| Term | Meaning |
| --- | --- |
| Class | One teaching session, typically two to three hours, from which clips may be selected. |
| Meeting occurrence | One recorded instance of a Zoom meeting. A recurring meeting ID may have several occurrences; import the selected instance only. |
| Source recording | The selected Zoom MP4 or locally supplied MP4. It is immutable for a job and identified by a content hash. |
| Transcript | Timed speech text paired with the source recording, from Zoom VTT or an approved transcription fallback. Its language and alignment status are explicit. |
| Candidate | A proposed source-time span containing one possible teaching moment. It is not automatically a clip or an approval. |
| Shortlist | Roughly ten ranked candidates prepared for the operator's normal review; weak or uncertain candidates remain accessible outside it. |
| Approved clip | A candidate whose boundaries, content, visible layout, and captions the operator explicitly accepted. Only approved clips may be exported as ready. |
| Posting package | The video, subtitle file, thumbnail, editable Facebook/YouTube text, category, provenance, and posting index for manual upload. |
| Job | The local, resumable processing record for one imported class and its associated settings, provider spend, review decisions, and exports. |
| Worth reviewing | A human transcript-level judgment that a candidate has a relevant, complete takeaway and usable opening. This does not mean the video is approved. |
| Publish-ready | The product claim that all gates in `docs/acceptance.md` have passed on real classes and private platform previews. It is not a synonym for a successful render. |

Do not use “confidence” as a synonym for correctness or “approved” as a synonym for published. The operator's post URLs and metrics are optional later records; the app does not publish automatically.
