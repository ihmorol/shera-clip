---
version: 1
slug: "shera-templates-review-html"
primary_target: "shera/templates/review.html"
related_targets: ["shera/templates/home.html","shera/templates/job.html","shera/templates/export.html"]
---

Scope: every Shera Clip page (home/import, class job, clip review, export). Mode: Operate.
Audience/job: one Rimons IELTS operator on a laptop turns a long Zoom class into approved portrait + landscape teaching clips. Task per screen: import → approve cost → wait → review each suggested clip (watch, trim, fix captions, preview both versions, approve) → export. Owner found the old UI confusing and asked for a slick, uncommon colour ("surprise me"), delegating the aesthetic.
Constraints: loopback app, system fonts with Bangla coverage (Nirmala UI), no invented brand assets, cost and state always visible, every control keeps default/hover/focus/disabled/loading/error.

## Direction contract
THESIS: The app is a film cutting room, not a SaaS dashboard: a class is a roll, suggested moments are trims pulled from it, and approval is the editor's grease-pencil mark. Refuses the white-card, blue-accent admin panel.
OWN-WORLD: Darkroom-teal ground (the cyan cast of a colour negative's shadows), panels a step lighter, film-base ivory ink, colour-negative orange-mask as the only action colour (primary buttons, current step, focus), leader green for approved, safety red for failed. Stage rail and preview frames carry sprocket perforations; timecodes in edge-print mono.
STORY: On every page the operator sees one "Next" instruction in plain words, then the work. They never guess which of eight panels matters.
FIRST VIEWPORT: Review page: source video and transcript on the left; on the right a sticky cutting bench holding portrait and landscape previews at one shared height scale, one orange "Save and render previews" action, then Approve/Reject. Edits sit below as numbered, collapsible trims.
FORM: Film cutting room (flatbed editor + trim bin), position 4 of 7 on the grounded list, seed 7de36903. Raises: from cracktro queue, only the current item is full-brightness, the rest recede; from the instrument six-pack, the class header is three fixed readouts (step, spend/cap, approved); from sneaker end-labels, every clip row uses one fixed label grid (rank, span, length, scores, category, state); from the botanical folio, both previews share one height scale for honest comparison; from the canon, orange appears only on things you can press or the current step.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
