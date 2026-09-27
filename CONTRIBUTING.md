# Contributing and documentation maintenance

This project is at the phase-1 prototype stage (local import). Use GitHub Issues for work and decisions and pull requests for changes. Do not treat the historical plans as current instructions.

## Sources of truth

1. `docs/PRD.md` defines product behavior and scope.
2. `docs/decisions.md` records confirmed owner decisions and limits on agent choice.
3. `docs/acceptance.md` defines proof required for claims.
4. `PRODUCT.md` holds durable UI product context; `docs/ui-theme.md` holds the current UI direction once approved.
5. `plans/` and `.omx/plans/` are historical research.

When a product decision changes, link an owner-approved `Decision:` issue. Update the PRD, decision record, acceptance checks, and UI direction together wherever affected. A PR description must say what changed, why, how it was checked, and what remains unverified. Do not replace an unpassed acceptance gate with an easier one after a failed run.

## Issue flow

Use `needs-info` for missing owner or external input, `ready-for-agent` for a bounded task with prerequisites available, `ready-for-human` for work requiring the operator, and `wontfix` for rejected scope. An implementation issue needs a product outcome, acceptance criterion, dependencies, and evidence expected. Keep one bounded deliverable per issue; link it to the PRD and its parent milestone or tracking issue.

## Repository hygiene

Do not commit source recordings, transcripts, exports, labels with personal information, credentials, authenticated URLs, job databases, generated caches, or installed third-party skill bundles. Use `skills-lock.json` to identify optional agent tools. Keep fixture descriptions and redacted evidence in Git; keep real class media in an operator-controlled local directory.

Before a release claim, check the current external API contracts and prices, run the relevant automated checks, complete the real browser/media pilot, and attach the evidence described in `docs/acceptance.md`. Record any unavailable credential, class sample, or platform preview as a blocker, not a passed test.

Run `python scripts/check_docs.py` before pushing documentation. GitHub runs the same check on pushes and pull requests.
