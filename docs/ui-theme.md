# UI direction: the lesson review desk

**Status:** proposed design seed for owner review, 2026-09-25. This is an `impeccable` **Operate** surface brief, not a claim that screens or tokens have been implemented. [Product context](../PRODUCT.md) and the [PRD](PRD.md) control the content and behavior. Exact Rimons IELTS colors, logo, and typography remain open until real assets are supplied or the owner approves a visual identity.

## Thesis

Make a three-hour class feel like a small, reviewable set of teaching decisions. The interface should show source evidence beside each proposed clip, keep the next action obvious, and spend visual emphasis on lesson content rather than analytics decoration. Its distinctive visual structure is an **annotated timeline and clip review ledger**, carried consistently from import through export.

## First useful screen and flow

1. **Import:** a searchable list of completed Zoom recording occurrences with date, host, duration, MP4 layouts, transcript status, and expected local size. One primary action imports the selected class. Connection, missing transcript, expired permission, and insufficient disk states have direct remedies.
2. **Prepare:** a persistent stage rail shows import, transcript, selection, review, and export. Progress names the current stage and records spend against the USD 1.50 cap. Resume returns to the last durable decision, not a new blank dashboard.
3. **Review:** a large, readable source preview and transcript/timeline occupy the working area. A shortlist of about ten candidates remains visible. Each selection shows the source span, score factors, category, editable boundaries, captions, and a portrait phone preview. The screen content must be legible at phone size; the teacher inset is secondary to slides or Word text.
4. **Export:** approved clips and unresolved warnings are distinct. The package view shows exactly what Facebook and YouTube will receive: video, captions, thumbnail, editable copy, provenance, and ready state. Rejected or incomplete clips cannot masquerade as ready.

## Visual character

The built visual system, including tokens, components, and rules, is recorded in [DESIGN.md](../DESIGN.md), which replaces the provisional neutral/blue direction that used to be here.

- **World:** a film cutting room. The ground is dark darkroom teal, panels are one tone lighter, and text is warm film-base ivory.
- **Accent:** colour-negative orange marks only pressable actions and the current step. Leader green means approved, grease-pencil yellow means the operator is needed, safety red means failed, and cyan means working.
- **Signatures:** a sprocket-holed film-strip step rail, mono edge-print timecodes, and a sticky review bench with portrait 9:16 and landscape 16:9 previews side by side.
- **Type and motion:** system sans with Bangla coverage, 150ms state feedback, one slow ambient ground drift with a matching glow on the floating panels (2026-10-01 owner direction), and no motion under reduced-motion.

## Interaction contract

- Every action has visible default, hover, keyboard focus, active, disabled, loading, success, and error states. Keyboard and screen-reader users can navigate recording selection, candidate review, boundary editing alternatives, approval, and export.
- A candidate can be approved only after its video, caption, and posting text states are clear. Use inline fixes and a compact warning summary instead of interruptive modal chains.
- Batch rejection and next-candidate navigation reduce manual work; approval remains explicit per clip. Preserve review decisions after refresh or restart.
- At narrow laptop widths, keep the source preview usable and let the shortlist collapse. At phone widths, the interface may inspect status and a portrait preview, but full editing may use a wider workspace; do not fake a usable mobile editor by shrinking controls.
- Empty, unavailable-provider, bad-transcript, budget-stop, and failed-render states explain the next safe action. Never imply that a failed ranking or export succeeded.

## Before visual implementation

Confirm whether the owner wants Rimons IELTS visual identity or a separate tool identity; check actual brand assets rather than inventing them. Choose and record the application stack. Design and test the portrait composition on a real slide-heavy recording before fixing tokens or layouts. When code exists, use `$impeccable document` to capture actual tokens and components into `DESIGN.md`; this brief remains the product-specific UI direction.
