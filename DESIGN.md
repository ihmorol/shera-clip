---
name: Shera Clip
description: A film cutting room for turning a long Zoom class into approved portrait and landscape teaching clips.
colors:
  ground: "#0a1d20"
  panel: "#0f282c"
  raised: "#153439"
  raised-hover: "#1c4148"
  well: "#081619"
  line: "#234950"
  line-hi: "#33646c"
  ink: "#f3e8d9"
  ink-2: "#a8c4c1"
  ink-3: "#7fa19e"
  mask: "#ff8a3d"
  mask-hi: "#ffa262"
  mask-lo: "#e8702a"
  mask-ink: "#221004"
  mask-wash: "rgba(255, 138, 61, .12)"
  leader: "#7fdc9c"
  leader-hi: "#9be8b3"
  leader-ink: "#062212"
  leader-wash: "rgba(127, 220, 156, .12)"
  pencil: "#f4c95d"
  pencil-ink: "#231a02"
  pencil-wash: "rgba(244, 201, 93, .12)"
  safety: "#ff7466"
  safety-ink: "#2a0703"
  safety-wash: "rgba(255, 116, 102, .12)"
  run: "#7ad6dc"
  run-wash: "rgba(122, 214, 220, .12)"
  film: "#140f0b"
  film-frame: "#231c16"
  film-frame-done: "#1d2a22"
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
  sm: "7px"
  frame: "8px"
  md: "10px"
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

**Creative North Star: "The Cutting Room"**

Shera Clip is a film editor's bench, not an admin dashboard. A class is a roll of film, the suggested moments are trims pulled from it, and approval is the editor's grease-pencil mark. The whole interface sits in a dark darkroom teal (the cyan cast of a colour negative's shadows), text is printed in warm film-base ivory, and the negative's orange mask is the one colour you can press. The system rejects the white-card, blue-accent admin panel it replaced.

Density is a working editor's: compact rows, fixed label grids, three instrument readouts on the class header, and one plain-words "Next" instruction at the top of every page so the operator never has to guess which panel matters. The video and transcript take most of the width on the review page. Decoration comes from the film world itself: sprocket perforations on the step rail and every preview gate, edge-print mono for timecodes, and black letterboxed frames for every preview.

The app runs on the operator's laptop and uses system fonts only. The font stack is chosen for Bangla coverage (Nirmala UI), so type has no display face. Hierarchy comes from weight, size, and tone.

**Key Characteristics:**
- Dark tonal stack (well, ground, panel, raised) instead of shadows.
- One action colour (orange mask). Semantic state is shown as a 12% wash with full-strength ink.
- Film-strip step rail with sprocket holes, one frame per pipeline step.
- A sticky cutting bench with portrait 9:16 and landscape 16:9 previews side by side.
- Mono edge-print timecodes and tabular numbers wherever time, money, or rank is read.

## Colors

A dark, cool teal ground under warm ivory ink. Colour-negative orange is the only accent, and a small set of darkroom signal colours (leader green, grease-pencil yellow, safety red, run cyan) carries state.

### Primary
- **Negative Orange Mask** (`mask`): primary buttons, the current step frame, focus outlines, text selection, caret, form accents, links (`mask-hi`), the reel mark in the header. `mask-hi` is the hover step and `mask-lo` the pressed step. Text on the mask is always `mask-ink`, a near-black brown (7.8:1).

### Secondary (state signals)
- **Leader Green** (`leader`): approved and done. Used for the Approve button fill, approved badges, and completed step frames.
- **Grease Pencil** (`pencil`): the operator is needed, including waiting for cost approval, paused jobs, length warnings, and setup gaps.
- **Safety Red** (`safety`): failed, rejected, destructive. Used for the Delete outline button, failure alerts, and export problems.
- **Run Cyan** (`run`): work in progress, including the running badge and progress bar fill.

Each signal has a `-wash` (12% alpha) for badge and alert backgrounds, and solid fills use a matching dark `-ink` for text.

### Neutral
- **Darkroom Teal** (`ground`): page background.
- **Deep Well** (`well`): recessed surfaces such as the sticky top bar, inputs, the transcript list, readout boxes, and the chooser list.
- **Bench Teal** (`panel`): every panel and the chooser dialog.
- **Raised Teal** (`raised`, hover `raised-hover`): secondary buttons, the "Next" box, trim-step numerals, row hover.
- **Splice Lines** (`line`, `line-hi`): 1px panel borders and dividers. `line-hi` is for control borders and table headers.
- **Film-base Ivory** (`ink`), **Fixer Grey-teal** (`ink-2`), **Faded Teal** (`ink-3`): primary text, secondary text, and tertiary labels, timestamps, and placeholders (5.5:1 on panel).
- **Film Stock** (`film`, `film-frame`, `film-frame-done`): the warm near-black of the step strip, its frames, and empty preview frames.

### Named Rules
**The Orange Mask Rule.** Filled orange appears only on something you can press or on the current step. Orange ink also marks the editor's own coordinates: the clip rank, timecodes inside the clip span, trim-step numerals, and the reel mark. Orange never shows a status and never decorates.

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

The page is a single column limited to 1480px, with 1.5rem gutters (1rem below 640px). A sticky top bar in `well` holds the reel mark and breadcrumbs. Panels stack with 1.25rem between them. Rhythm is tight: 0.25 to 0.75rem inside controls and rows, 1 to 1.5rem between groups.

Each page opens with one "Next" box, then the work. The class page header is a title plus three fixed readouts (Step, Spent of cap, Approved), then the film strip. Clip tables use one fixed label grid: rank, span, length, scores, category, and decision.

The review page is a two-column grid. The work column (`minmax(0, 1fr)`) holds source video, transcript, and four numbered trims. The bench column (`minmax(30rem, 42rem)`) is sticky at 4.2rem from the top. Inside the bench, previews use a `9fr | 16fr` grid so 1080 portrait pixels and 1920 landscape pixels sit at one shared scale: portrait 9:16 on the left, landscape 16:9 on the right with the actions stacked under it. Each preview sits in a `.gate`: a film frame with sprocket perforations above and below, matching the step rail.

Breakpoints:
- **1180px:** the review stacks and the bench moves above the work, no longer sticky.
- **900px:** the strip wraps to 4 columns and the export package grid goes to one column.
- **640px:** gutters tighten, forms and previews go to one column, the portrait frame is capped at 16rem, and tables scroll sideways.

## Elevation & Depth

The system is flat and uses tonal layering. Depth comes from four tones: `well` is recessed, `ground` is the floor, `panel` is the bench, and `raised` is a control. Borders are 1px splice lines. Only two surfaces float, so only they get a shadow.

### Shadow Vocabulary
- **Bench lift** (`box-shadow: 0 10px 30px -12px rgba(0,0,0,.55), 0 2px 6px -2px rgba(0,0,0,.35)`): the sticky review bench panel and the file-chooser dialog, which has a `rgba(3,10,11,.72)` backdrop.

### Named Rules
**The Tonal Stack Rule.** Inputs, lists, and readouts go down into `well`, and controls go up into `raised`. Only a surface that floats above scrolling content gets a shadow.

## Shapes

Corners are gentle and consistent. Controls, inputs, alerts, the Next box, and fieldsets use 7px. Panels and the dialog use 10px. Preview frames use 8px. Film-strip frames use tight 3px corners inside a 6px strip. Badges and progress bars are fully round pills with a 0.45rem dot. Trim-step numerals are 1.6rem circles. The trim disclosure chevron is a rotated 2px border corner. The only repeating geometry is the sprocket hole: 3px radial dots in `ground`, tiled every 14px along the top and bottom of the strip.

## Components

### Buttons
Buttons are tactile and plain: weight 600, 0.93rem, `0.55rem 1rem` padding, 7px corners, a 1px border, and an inline 1.1em SVG icon when needed.
- **Primary:** mask fill and border with mask-ink text. Hover goes to `mask-hi` and press to `mask-lo`. A page has one primary.
- **Secondary (default):** `raised` fill, `line-hi` border, ivory text. Hover goes to `raised-hover` with an `ink-3` border.
- **Approve:** leader fill with leader-ink text. Hover goes to `leader-hi`. It stays disabled until previews are rendered.
- **Danger:** transparent with a safety-red outline at 45% and red text. Hover adds the safety wash.
- **Icon:** transparent, `ink-2`. Hover is safety red because it is only used to delete a caption.
- **Small:** `0.32rem 0.7rem` at 0.85rem, used for Open, Previous, and Next.
- **States:** all buttons ease colour over 150ms, press down by 1px, go to 42% opacity with a not-allowed cursor when disabled, and go to 75% opacity with a progress cursor plus `aria-busy` when loading. Focus is a 2px mask outline offset by 2px.

### Badges
A pill with a dot drawn in `currentColor`. Default is `raised`/`ink-2` for "To review". Approved and done use leader, waiting, paused, and warn use pencil, failed and rejected use safety, and running uses run with a 1.4s dot pulse. Warn badges drop the dot.

### Cards / Containers
- **Panel:** `panel` fill, 1px `line`, 10px corners, `1.25rem 1.35rem` padding. It is never nested inside another panel.
- **Next box:** the single instruction per page. `raised` fill, `line-hi` border, 7px corners. The `attn` variant adds a pencil wash and a pencil heading. The `fail` variant adds a safety wash and a safety heading.
- **Alert:** 7px, 1px border. `fail` uses a safety wash with pale-red text. `attn` uses a pencil wash.
- **Readouts:** small `well` boxes (min 7.5rem) holding a 0.75rem `ink-3` term over a 650-weight value.

### Inputs / Fields
- **Style:** `well` fill, 1px `line`, 7px corners, `0.5rem 0.65rem` padding. Placeholder uses `ink-3`. Number inputs use mono tabular figures.
- **Hover:** the border steps to `line-hi`.
- **Focus:** the border turns mask, the fill darkens one step, and a 3px `mask-wash` ring appears. There is no outline.
- **Fieldsets** use a 1px `line` border at 7px. Checkboxes and radios take the mask accent.

### Navigation
The top bar holds the reel mark (orange SVG) and "Shera Clip" in bold ivory. Breadcrumbs follow in `ink-3` with `/` separators, links in `ink-2` that underline on hover, and the current crumb in ivory. On the review page, Previous and Next are small buttons with `J`/`K` key hints.

### Film-strip Step Rail (signature)
An 8-frame ordered list printed on `film` stock with sprocket holes along both edges. Each frame shows a mono step number over a plain label at 0.82rem. Pending frames are dim film frames. Done frames show leader-green text on a dark green frame. The current frame is filled mask orange in bold and carries `aria-current="step"`. It stays orange in every state; waiting or paused adds a grease-pencil yellow underline and failed a safety red one. The strip wraps to two rows of four at 900px.

### Review Bench (signature)
A sticky panel titled "Preview and decide" with the review status badge and a live hint line. The portrait 9:16 frame and the landscape 16:9 frame are black letterboxes with 8px corners and 1px borders, captioned with their ratio and destinations ("Shorts, Reels" or "YouTube, Facebook feed"). Before rendering, each frame is an empty film-stock slot with a dashed warm border and a centred `ink-3` note. Under the landscape frame are the one orange action, "Save and render previews" (relabelled "Rendering…", "Render again", or "Render previews" by state), then "Save only", a status line, and a divider above the Approve and Reject pair.

### Class Reel (signature)

The whole class drawn as one strip of `film` with sprocket holes top and bottom. Each suggested clip is a numbered frame at its real position and width: mask orange, leader green when approved, dimmed film when rejected. Moments Jev judged to be a played recording sit behind as a faint `run` wash. A time scale (start, middle, end) in edge-print mono sits underneath, with a small key. Marks are links and lift 2px on hover or focus.

### Contact Sheet (signature)

Suggested clips are a sheet of film frames (`.sheet`, auto-fill columns of at least 17.5rem). Each frame is a real still from the clip inside a perforated `.gate`, with the rank printed in a mask-orange chip top-left (leader green when approved, film brown and a greyscale still when rejected) and the length bottom-right. Under it: the title (the AI draft title, or the opening line in quotes with its English below in `run`), the plain-words reason line, the time span, and the state badge. The frame lifts 3px with a mask ring on hover or focus.

### Jev's Answer

Inside "About this clip", a disclosure lists every question Jev answered: its label, its answer in mask-hi, confidence, the question as asked, and up to five options as thin probability bars (mask fill on a `line` track). Options Jev gave 0% are hidden.

### Transcript and Trims
The transcript is a scrolling `well` list (max 22rem) of full-width line buttons: a mono time followed by text in `ink-3`. Lines inside the clip span turn ivory on a 7% orange wash, with their times in `mask-hi`. The four edits below are collapsible `details` panels, each led by a round mono numeral and closed with a rotating chevron. Nudge buttons are small mono chips (`− line`, `− 0.5 s`, `+ 0.5 s`, `+ line`).

## Do's and Don'ts

### Do:
- **Do** keep filled orange for the page's one primary action and the current step. Everything else pressable is `raised` secondary.
- **Do** show every state as a wash plus ink badge, using the same four signals: leader, pencil, safety, run.
- **Do** set time, paths, and typed numbers in the mono edge-print face with tabular figures.
- **Do** put one "Next" box at the top of each page and phrase it as a plain instruction.
- **Do** keep the portrait and landscape previews side by side on the bench, each labelled with its ratio and destinations.
- **Do** show state changes with colour transitions of about 150ms, and turn all motion off under `prefers-reduced-motion`.

### Don't:
- **Don't** bring back white cards, neutral grey surfaces, or a blue accent. This world replaced them.
- **Don't** use orange for a status, a chart, or decoration.
- **Don't** use grease-pencil yellow for anything that does not need the operator.
- **Don't** add shadows to panels at rest. Depth comes from the tonal stack.
- **Don't** use a display or web font. The system stack exists for Bangla coverage.
- **Don't** let pending strip-frame text fall below 4.5:1 (`#a1937f` on the film frame measures about 5.6:1).
