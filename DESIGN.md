---
name: Shera Clip
description: A film cutting room for turning a long Zoom class into approved portrait and landscape teaching clips.
colors:
  ground: "#09090c"
  panel: "#141419"
  raised: "#1d1d25"
  raised-hover: "#262634"
  well: "#0e0e13"
  line: "#262631"
  line-hi: "#383846"
  ink: "#f2f2f6"
  ink-2: "#a9a9b8"
  ink-3: "#7e7e90"
  mask: "#5e53dd"
  mask-hi: "#6c61e8"
  mask-lo: "#4a3fc4"
  mask-ink: "#ffffff"
  mask-wash: "rgba(108, 97, 232, .14)"
  leader: "#8ab4f8"
  leader-hi: "#a5c6fa"
  leader-ink: "#101735"
  leader-wash: "rgba(138, 180, 248, .13)"
  pencil: "#efc368"
  pencil-ink: "#231a02"
  pencil-wash: "rgba(239, 195, 104, .12)"
  safety: "#ff7a70"
  safety-ink: "#2a0703"
  safety-wash: "rgba(255, 122, 112, .12)"
  run: "#9a8df6"
  run-wash: "rgba(154, 141, 246, .13)"
  film: "#0b0b10"
  film-frame: "#17171f"
  film-frame-done: "#191927"
typography:
  display:
    fontFamily: "Segoe UI Variable Text, Segoe UI, Nirmala UI, system-ui, -apple-system, Noto Sans Bengali, sans-serif"
    fontSize: "2rem"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Segoe UI Variable Text, Segoe UI, Nirmala UI, system-ui, -apple-system, Noto Sans Bengali, sans-serif"
    fontSize: "1.6rem"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Segoe UI Variable Text, Segoe UI, Nirmala UI, system-ui, -apple-system, Noto Sans Bengali, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Segoe UI Variable Text, Segoe UI, Nirmala UI, system-ui, -apple-system, Noto Sans Bengali, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Segoe UI Variable Text, Segoe UI, Nirmala UI, system-ui, -apple-system, Noto Sans Bengali, sans-serif"
    fontSize: "0.82rem"
    fontWeight: 600
    lineHeight: 1.25
  timecode:
    fontFamily: "Cascadia Mono, Cascadia Code, Consolas, ui-monospace, monospace"
    fontSize: "0.88em"
    fontWeight: 400
    fontFeature: "tnum"
rounded:
  cell: "3px"
  strip: "6px"
  sm: "9px"
  frame: "8px"
  md: "14px"
  pill: "999px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "0.75rem"
  base: "1rem"
  lg: "1.25rem"
  xl: "1.5rem"
  xxl: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.mask}"
    textColor: "{colors.mask-ink}"
    rounded: "{rounded.sm}"
    padding: "0.55rem 1rem"
  button-primary-hover:
    backgroundColor: "{colors.mask-hi}"
    textColor: "{colors.mask-ink}"
  button-primary-active:
    backgroundColor: "{colors.mask-lo}"
  button-secondary:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0.55rem 1rem"
  button-secondary-hover:
    backgroundColor: "{colors.raised-hover}"
  button-approve:
    backgroundColor: "{colors.leader}"
    textColor: "{colors.leader-ink}"
    rounded: "{rounded.sm}"
    padding: "0.55rem 1rem"
  button-approve-hover:
    backgroundColor: "{colors.leader-hi}"
  button-danger:
    backgroundColor: "transparent"
    textColor: "{colors.safety}"
    rounded: "{rounded.sm}"
    padding: "0.55rem 1rem"
  button-danger-hover:
    backgroundColor: "{colors.safety-wash}"
  button-small:
    rounded: "{rounded.sm}"
    padding: "0.32rem 0.7rem"
  input:
    backgroundColor: "{colors.well}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 0.65rem"
  panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "1.25rem 1.35rem"
  next-box:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "1rem 1.15rem"
  badge-approved:
    backgroundColor: "{colors.leader-wash}"
    textColor: "{colors.leader}"
    rounded: "{rounded.pill}"
    padding: "0.15rem 0.6rem"
  badge-attention:
    backgroundColor: "{colors.pencil-wash}"
    textColor: "{colors.pencil}"
    rounded: "{rounded.pill}"
    padding: "0.15rem 0.6rem"
  badge-failed:
    backgroundColor: "{colors.safety-wash}"
    textColor: "{colors.safety}"
    rounded: "{rounded.pill}"
    padding: "0.15rem 0.6rem"
  badge-running:
    backgroundColor: "{colors.run-wash}"
    textColor: "{colors.run}"
    rounded: "{rounded.pill}"
    padding: "0.15rem 0.6rem"
  strip:
    backgroundColor: "{colors.film}"
    rounded: "{rounded.strip}"
    padding: "14px 6px"
  strip-frame:
    backgroundColor: "{colors.film-frame}"
    rounded: "{rounded.cell}"
    padding: "0.45rem 0.6rem"
  strip-frame-done:
    backgroundColor: "{colors.film-frame-done}"
    textColor: "{colors.leader}"
  strip-frame-current:
    backgroundColor: "{colors.mask}"
    textColor: "{colors.mask-ink}"
  strip-frame-needs-you:
    backgroundColor: "{colors.pencil}"
    textColor: "{colors.pencil-ink}"
  strip-frame-failed:
    backgroundColor: "{colors.safety}"
    textColor: "{colors.safety-ink}"
  preview-frame-portrait:
    backgroundColor: "#000"
    rounded: "{rounded.frame}"
    width: "9fr (shared scale with landscape 16fr)"
  preview-frame-empty:
    backgroundColor: "{colors.film}"
    textColor: "{colors.ink-3}"
    rounded: "{rounded.frame}"
    padding: "1rem"
---

# Design System: Shera Clip

## Overview

**Creative North Star: "The Cutting Room at Midnight"**

Shera Clip is a film editor's bench, not an admin dashboard. A class is a roll of film, the suggested moments are trims pulled from it, and approval is the editor's grease-pencil mark. The interface sits on a near-black stage — a theatre with the projector running — text prints in lavender-white, and the violet screen-light is the one colour you can press. Surfaces stay neutral black; only the screen-light carries saturation. The system rejects the white-card admin panel it replaced; the palette follows the owner's 2026-10-01 indigo reference (D32) and replaces the earlier darkroom-teal world.

Density is a working editor's: compact rows, fixed label grids, three instrument readouts on the class header, and one plain-words "Next" instruction at the top of every page so the operator never has to guess which panel matters. The video and transcript take most of the width on the review page. Decoration comes from the film world itself: sprocket perforations on the step rail and every preview gate, edge-print mono for timecodes, and black letterboxed frames for every preview.

The app runs on the operator's laptop and uses system fonts only. The font stack is chosen for Bangla coverage (Nirmala UI), so type has no display face. Hierarchy comes from weight, size, and tone.

**Key Characteristics:**
- Dark tonal stack (well, ground, panel, raised) instead of shadows.
- One action colour (screen-light violet). Semantic state is shown as a 12% wash with full-strength ink.
- Film-strip step rail with sprocket holes, one frame per pipeline step.
- A sticky cutting bench with portrait 9:16 and landscape 16:9 previews side by side.
- Mono edge-print timecodes and tabular numbers wherever time, money, or rank is read.
- A living room: the page ground carries a slow ambient gradient drift, and the two floating surfaces (review bench, file chooser) hold a soft glow that leans violet, then blue. Both stop under reduced-motion.

## Colors

A near-black stage under lavender-white ink. Screen-light violet is the only accent, and a small set of theatre signal colours (signal blue, grease-pencil yellow, safety red, run violet) carries state.

### Primary
- **Screen-light Violet** (`mask`): primary buttons, the current step frame, focus outlines, text selection, caret, form accents, links (`mask-text`), the reel mark in the header. `mask-hi` is the hover step and `mask-lo` the pressed step; `mask-hi` is a fill, never ink — violet text uses `mask-text` (#8277f2, 5.0–5.4:1 on panel, well, and the in-clip wash). Text on the mask is always `mask-ink`, pure white (5.6:1 on `mask`, 4.6:1 on the `mask-hi` hover).

### Secondary (state signals)
- **Signal Blue** (`leader`): approved and done. Used for the Approve button fill, approved badges, and completed step frames.
- **Grease Pencil** (`pencil`): the operator is needed, including waiting for cost approval, paused jobs, length warnings, and setup gaps.
- **Safety Red** (`safety`): failed, rejected, destructive. Used for the Delete outline button, failure alerts, and export problems.
- **Run Violet** (`run`): work in progress, including the running badge and progress bar fill.

Each signal has a `-wash` (12–14% alpha) for badge and alert backgrounds, and solid fills use a matching dark `-ink` for text.

### Neutral
- **Stage Black** (`ground`): page background.
- **Deep Well** (`well`): recessed surfaces such as the sticky top bar, inputs, the transcript list, readout boxes, and the chooser list.
- **Bench Black** (`panel`): every panel and the chooser dialog.
- **Raised Black** (`raised`, hover `raised-hover`): secondary buttons, the "Next" box, trim-step numerals, row hover.
- **Splice Lines** (`line`, `line-hi`): 1px panel borders and dividers. `line-hi` is for control borders and table headers.
- **Lavender-white** (`ink`), **Greyed Lavender** (`ink-2`), **Faded Indigo** (`ink-3`): primary text, secondary text, and tertiary labels, timestamps, and placeholders (4.6:1 on panel).
- **Film Stock** (`film`, `film-frame`, `film-frame-done`): the near-black of the step strip, its frames, and empty preview frames.

### Named Rules
**The Screen-light Rule.** Filled violet appears only on something you can press or on the current step. Violet ink also marks the editor's own coordinates: the clip rank, timecodes inside the clip span, trim-step numerals, and the reel mark. Violet never shows a status and never decorates — the recorded exceptions are the ambient ground drift and the screening glow's violet lean (D31), which sit behind or around content, never on it.

**The Grease Pencil Rule.** Yellow means "you are needed." Waiting, paused, and warning share it, and nothing else uses it.

**The Wash Rule.** Status shows as a 12% wash with full-strength ink, never as a solid block. Solid signal fills are reserved for the Approve button and the current strip frame.

## Typography

**Body Font:** Segoe UI Variable Text (with Segoe UI, Nirmala UI, system-ui, Noto Sans Bengali)
**Label/Mono Font:** Cascadia Mono (with Cascadia Code, Consolas, ui-monospace)

**Character:** One workhorse system sans with verified Bangla fallback carries everything, and headings get only weight (650) and slight negative tracking. A mono edge-print face carries timecodes, file paths, keys, and numeric inputs, like the frame numbers printed along film stock.

### Hierarchy
- **Display** (650, 2rem, 1.2, -0.02em): the page head on the home page only.
- **Headline** (650, 1.6rem, 1.2): page and clip titles (`h1`).
- **Title** (650, 1.15rem, 1.2): panel headings (`h2`). Trim summaries use 1.05rem.
- **Body** (400, 15px root, 1.5): all running text. The lede is limited to 62ch.
- **Label** (600, 0.82rem): table headers and figure captions in `ink-3` or `ink`. Readout terms use 0.75rem. Badges use 0.8rem.
- **Timecode** (mono, 0.88em, tabular): spans, transcript times, paths, `kbd`, numeric inputs.

### Named Rules
**The Edge-Print Rule.** Every timecode, path, and typed number is set in mono, and every column of numbers uses tabular figures and right alignment.

## Layout

The page is a single column limited to 1240px, with 1.5rem gutters (1rem below 640px). A sticky top bar holds the reel mark and breadcrumbs, blurring the page behind it (86% `well` tint). Panels stack with 1.5rem between them. Rhythm is tight: 0.25 to 0.75rem inside controls and rows, 1 to 1.5rem between groups.

Each page opens with one "Next" box, then the work. The class page header is a title plus three fixed readouts (Step, Spent of cap, Approved), then the film strip. Clip tables use one fixed label grid: rank, span, length, scores, category, and decision.

The review page is a two-column grid. The work column (`minmax(0, 1fr)`) holds source video, transcript, and four numbered trims. The bench column (`minmax(30rem, 42rem)`) is sticky at 4.2rem from the top. Inside the bench, previews use a `9fr | 16fr` grid so 1080 portrait pixels and 1920 landscape pixels sit at one shared scale: portrait 9:16 on the left, landscape 16:9 on the right with the actions stacked under it. Each preview sits in a `.gate`: a film frame with sprocket perforations above and below, matching the step rail.

Breakpoints:
- **1180px:** the review stacks and the bench moves above the work, no longer sticky.
- **900px:** the strip wraps to 4 columns and the export package grid goes to one column.
- **640px:** gutters tighten, forms and previews go to one column, the portrait frame is capped at 16rem, and tables scroll sideways.

## Elevation & Depth

The system is flat and uses tonal layering. Depth comes from four tones: `well` is recessed, `ground` is the floor, `panel` is the bench, and `raised` is a control. Borders are 1px splice lines. Only two surfaces float, so only they get a shadow.

### Shadow Vocabulary
- **Screening glow** (`--glow-a` / `--glow-b`, 2026-10-01 owner direction): the two floating surfaces — the sticky review bench panel and the file-chooser dialog (backdrop `rgba(4,3,12,.72)`) — carry a soft shadow that animates between a violet-tinted and a blue-tinted state (deep lift, offset + blur, plus a 2px contact layer) over 24s. It supersedes the earlier static bench lift. It drifts only while the bench actually floats (above 1180px). The page ground itself drifts two low-alpha radial glows (signal blue, violet) over a darker black wash at the top, over 34s, behind everything; panels stay solid on top of it.

### Named Rules
**The Tonal Stack Rule.** Inputs, lists, and readouts go down into `well`, and controls go up into `raised`. Surfaces at rest take no static depth shadow: depth is the tonal stack, the two floating surfaces carry the animated screening glow, and pressable accents (primary and approve buttons, reel marks) may hold a soft glow in their own colour.

## Shapes

Corners are gentle and consistent. Controls, inputs, alerts, the Next box, and fieldsets use 9px. Panels and the dialog use 14px. Preview frames use 8px. Film-strip frames use tight 3px corners inside a 6px strip. Badges and progress bars are fully round pills with a 0.45rem dot. Trim-step numerals are 1.6rem circles. The trim disclosure chevron is a rotated 2px border corner. The only repeating geometry is the sprocket hole: 3px radial dots in `ground`, tiled every 14px along the top and bottom of the strip.

## Components

### Buttons
Buttons are tactile and plain: weight 600, 0.93rem, `0.55rem 1rem` padding, 9px corners, a 1px border, and an inline 1.1em SVG icon when needed.
- **Primary:** mask fill and border with mask-ink text. Hover goes to `mask-hi` and press to `mask-lo`. A page has one primary.
- **Secondary (default):** `raised` fill, `line-hi` border, lavender-white text. Hover goes to `raised-hover` with an `ink-3` border.
- **Approve:** leader fill with leader-ink text. Hover goes to `leader-hi`. It stays disabled until previews are rendered.
- **Danger:** transparent with a safety-red outline at 45% and red text. Hover adds the safety wash.
- **Icon:** transparent, `ink-2`. Hover is safety red because it is only used to delete a caption.
- **Small:** `0.32rem 0.7rem` at 0.85rem, used for Open, Previous, and Next.
- **States:** all buttons ease colour over 150ms, press down by 1px, go to 42% opacity with a not-allowed cursor when disabled, and go to 75% opacity with a progress cursor plus `aria-busy` when loading. Focus is a 2px mask outline offset by 2px.

### Badges
A pill with a dot drawn in `currentColor`. Default is `raised`/`ink-2` for "To review". Approved and done use leader, waiting, paused, and warn use pencil, failed and rejected use safety, and running uses run with a 1.4s dot pulse. Warn badges drop the dot.

### Cards / Containers
- **Panel:** `panel` fill, 1px `line`, 14px corners, `1.4rem 1.6rem` padding. It is never nested inside another panel.
- **Next box:** the single instruction per page. `raised` fill, `line-hi` border, 9px corners. The `attn` variant adds a pencil wash and a pencil heading. The `fail` variant adds a safety wash and a safety heading.
- **Alert:** 9px, 1px border. `fail` uses a safety wash with pale-red text. `attn` uses a pencil wash.
- **Readouts:** small `well` boxes (min 7.5rem) holding a 0.75rem `ink-3` term over a 650-weight value.

### Inputs / Fields
- **Style:** `well` fill, 1px `line`, 9px corners, `0.5rem 0.65rem` padding. Placeholder uses `ink-3`. Number inputs use mono tabular figures.
- **Hover:** the border steps to `line-hi`.
- **Focus:** the border turns mask, the fill darkens one step, and a 3px `mask-wash` ring appears. There is no outline.
- **Fieldsets** use a 1px `line` border at 9px. Checkboxes and radios take the mask accent.

### Navigation
The top bar holds the reel mark (violet SVG) and "Shera Clip" in bold lavender-white. Breadcrumbs follow in `ink-3` with `/` separators, links in `ink-2` that underline on hover, and the current crumb in `ink`. On the review page, Previous and Next are small buttons with `J`/`K` key hints.

### Film-strip Step Rail (signature)
An 8-frame ordered list printed on `film` stock with sprocket holes along both edges. Each frame shows a mono step number over a plain label at 0.82rem. Pending frames are dim film frames. Done frames show signal-blue text on a dark frame. The current frame is filled screen-light violet in bold and carries `aria-current="step"`. It stays violet in every state; waiting or paused adds a grease-pencil yellow underline and failed a safety red one. The strip wraps to two rows of four at 900px.

### Review Bench (signature)
A sticky panel titled "Preview and decide" with the review status badge and a live hint line. The portrait 9:16 frame and the landscape 16:9 frame are black letterboxes with 8px corners and 1px borders, captioned with their ratio and destinations ("Shorts, Reels" or "YouTube, Facebook feed"). Before rendering, each frame is an empty film-stock slot with a dashed faded border and a centred `ink-3` note. Under the landscape frame are the one violet action, "Save and render previews" (relabelled "Rendering…", "Render again", or "Render previews" by state), then "Save only", a status line, and a divider above the Approve and Reject pair.

### Class Reel (signature)

The whole class drawn as one strip of `film` with sprocket holes top and bottom. Each suggested clip is a numbered frame at its real position and width: screen-light violet, signal blue when approved, dimmed film when rejected. Moments Jev judged to be a played recording sit behind as a faint `run` wash. A time scale (start, middle, end) in edge-print mono sits underneath, with a small key. Marks are links and lift 2px on hover or focus.

### Contact Sheet (signature)

Suggested clips are a sheet of film frames (`.sheet`, auto-fill columns of at least 17.5rem). Each frame is a real still from the clip inside a perforated `.gate`, with the rank printed in a violet chip top-left (signal blue when approved, film-frame grey and a greyscale still when rejected) and the length bottom-right. Under it: the title (the AI draft title, or the opening line in quotes with its English below in `run`), the plain-words reason line, the time span, and the state badge. The frame lifts 3px with a mask ring on hover or focus.

### Other Moments (signature)

Left-out moments share the same contact sheet, inside an open disclosure: each carries a real still, dimmed slightly, with its decision-model score printed in a neutral chip top-left (violet stays reserved for suggested clips), the plain-words reason for being left out, and its state badge. Moments are ordered by score, best first, so the operator rescues the most promising one before scrolling.

### Jev's Answer

Inside "About this clip", a disclosure lists every question Jev answered: its label, its answer in mask-text, confidence, the question as asked, and up to five options as thin probability bars (mask fill on a `line` track). Options Jev gave 0% are hidden.

### Transcript and Trims
The transcript is a scrolling `well` list (max 22rem) of full-width line buttons: a mono time followed by text in `ink-3`. Lines inside the clip span turn lavender-white on a 9% violet wash, with their times in `mask-text`. The four edits below are collapsible `details` panels, each led by a round mono numeral and closed with a rotating chevron. Nudge buttons are small mono chips (`− line`, `− 0.5 s`, `+ 0.5 s`, `+ line`).

## Do's and Don'ts

### Do:
- **Do** keep filled violet for the page's one primary action and the current step. Everything else pressable is `raised` secondary.
- **Do** show every state as a wash plus ink badge, using the same four signals: leader, pencil, safety, run.
- **Do** set time, paths, and typed numbers in the mono edge-print face with tabular figures.
- **Do** put one "Next" box at the top of each page and phrase it as a plain instruction.
- **Do** keep the portrait and landscape previews side by side on the bench, each labelled with its ratio and destinations.
- **Do** keep the ambient motion to the recorded two moments (ground drift, floating-surface glow), keep both slow and low-alpha, and turn all motion off under `prefers-reduced-motion`.

### Don't:
- **Don't** bring back white cards, neutral grey surfaces, or any accent outside the recorded screen-light violet. This world replaced them.
- **Don't** use violet for a status, a chart, or decoration.
- **Don't** use grease-pencil yellow for anything that does not need the operator.
- **Don't** give panels at rest a static drop shadow. Resting depth is the tonal stack; only the floating surfaces glow, and only with the recorded drift.
- **Don't** use a display or web font. The system stack exists for Bangla coverage.
- **Don't** let pending strip-frame text fall below 4.5:1 (`#a09ad0` on the film frame measures about 6.8:1).
