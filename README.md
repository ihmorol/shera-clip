# Shera Clip

Shera Clip is a planned local tool for turning Rimons IELTS Zoom classes into reviewed Facebook and YouTube clips. This repository currently contains the product specification and project guidance; it does not contain the application or class recordings.

## Start here

1. [Product requirements](docs/PRD.md) are the sole product authority.
2. [Confirmed decisions](docs/decisions.md) records owner choices and agent decision limits.
3. [Acceptance plan](docs/acceptance.md) defines what evidence is required before calling the product publish-ready.
4. [Zoom setup](docs/zoom-setup.md) is the account-owner checklist for direct cloud-recording import.
5. [Product context](PRODUCT.md) and [UI direction](docs/ui-theme.md) guide future interface work.

The analyses in `plans/` and the earlier MVP v2 plan are historical references. Where they differ from the PRD, the PRD controls. No API secrets, source recordings, transcripts, exports, or human labels belong in Git.

## Project status

**Phase-1 working prototype: local MP4/VTT import (D15).** Phase 2 adds Zoom cloud-recording import; it is tested against a simulated Zoom only until the read-only Zoom app exists ([#2](https://github.com/ihmorol/shera-clip/issues/2)). Nothing here is publish-ready until the gates in [acceptance](docs/acceptance.md) pass on real classes. Zoom credentials, consent-cleared class samples, and brand assets are still implementation inputs; their absence does not authorize anyone to fabricate evidence.

## Run it

Requirements:
- Python 3.12 or later.
- FFmpeg and ffprobe on `PATH`, built with libass.
- A Bangla-capable font. On Windows, "Nirmala UI" is used.

```bash
pip install -e .
```

Copy `.env.example` to `.env` and fill in `OPENROUTER_API_KEY`. That one key covers ranking (Jev), posting drafts, and speech-to-text when the class has no usable VTT.

```bash
python -m shera
```

The app opens at `http://127.0.0.1:8765`. Put `class.mp4` and `class.vtt` (same file name) in `data/inbox/`, or paste their paths on the home page. With the four `ZOOM_*` values in `.env`, **Choose from Zoom cloud recordings** lists the teacher's cloud recordings a month at a time and downloads the chosen one. Then import the class and authorize paid work, which is capped at USD 1.50 per class. Review the shortlist, render a phone preview, and approve. Finally, export; packages land in `data/exports/<job>/`.

## Drive it from a terminal (D29)

The same pipeline runs headlessly with JSON output, so a script or an AI agent can do the machine stages while a human still approves every clip in the review UI:

```bash
shera import class.mp4 --vtt class.vtt   # runs until the job waits for a human
shera authorize <job-id>                 # show the cost estimate
shera authorize <job-id> --yes           # authorize paid calls up to the USD 1.50 cap
shera candidates <job-id> --all          # ranked candidates, scores, and why weak ones are out
shera export <job-id>                    # package approved clips into data/exports/<job>/
shera zoom list                          # cloud recordings, when the ZOOM_* values are set
```

`shera --help` lists every command (`job`, `run`, `calls`, `resolve`, `delete`, `zoom import`, ...). Every valid command prints one JSON object; a failure — including a usage error — exits 1 with the error named in the JSON (`--help` prints plain text). The CLI has no approve/reject command: approval stays a human act in the review UI. Pass `--data` (or set `SHERA_DATA`) to point a run at a different data folder.

Run the tests with `pip install -e .[test]` and then `python -m pytest -q`. They generate their own synthetic media.

See [contributing and maintenance](CONTRIBUTING.md) before changing product decisions.
