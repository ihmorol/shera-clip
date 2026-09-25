# AutoClip Jev-Engine — Stress-Test Addendum v1.1

> Historical analysis only. The authoritative product requirements are in the [Shera Clip PRD](../docs/PRD.md). Do not implement from this document where it differs from the PRD.

- **Status:** Draft for review
- **Continues:** [`autoclip-jev-engine-analysis.md`](autoclip-jev-engine-analysis.md) (v1.0 analysis)
- **Purpose:** Stress-test the three proposed solutions (chunk→slides→score, two reference files, Jev via OpenRouter) instead of accepting them. Includes corrected cost model and two **[v1.0 CORRECTION]** notes where the new architecture changes my earlier math.

---

## 15. Proposal 1 — Chunk → slides → score

> *"take the first full length video, then create 10min windows, and cut the transcript also. and then for each window a sliding length of 15-30s"*

### 15.1 Verdict: **Conditionally approved — but do not send overlapping slides to the model.**

The direction is right and it **reuses the cuts you already want** — a real win. But *"for each window a sliding length of 15-30s"* hides a decision with large consequences:

- A 10-minute chunk with **30s slides at a 15s stride (50% overlap)** → **39 candidates per chunk**.
- Across an 18-chunk, 3-hour class → **~700 near-identical overlapping candidates**.

### 15.2 Stress test — what breaks

| Attack | Result |
|---|---|
| **Model must distinguish overlapping units** | 39 units/chunk differing by only 15s is a *precision* problem, not a recall problem. A 1B-class model cannot reliably pick the exact right overlapping unit — you are asking it to do boundary precision it is bad at. |
| **Blind enumeration** | Asking a small model to return one opaque ID out of "w003_s00…w003_s38" is a known failure mode (index drift, off-by-one, hallucinated IDs). |
| **Cost scaling** | One prompt per 15s slide = ~700 calls/class → latency and cost scale linearly with slide count. |
| **Context loss** | A 15s slide judged *in isolation* loses surrounding dialogue; a hook mid-sentence can score high for the wrong reason. |

### 15.3 Corrected variant (recommended)

**Separate *where* from *exactly when*.** Do not make the model do sub-30s precision.

1. **Coarse grid for scoring.** Score **non-overlapping 30s units** (20/chunk) — or 15s units (40/chunk) — in **one call per chunk** that includes the *full chunk transcript* plus explicit unit IDs. The model's job: **rank units**. Small, bounded, cheap.
2. **Boundary precision in code, not in the model.** Starting from the chosen unit, **snap in/out points to transcript sentence boundaries** inside that unit (reuse the precise set from Proposal 2). Deterministic, free, and better than the model at its weakest task.
3. **Optional refine pass on top-K only.** If quality demands it, run a second call *only on the top 3–5 units per chunk*, feeding **only the shortlist** (IDs + text) — never the whole window again, or input tokens double.

This keeps your chunk model, keeps the cuts you already make, and removes the model's hardest job.

### 15.4 Token & cost math (accurate)

Assumptions: speech ≈ 150 wpm; English ≈ 1.33 tokens/word; 3 hours = 180 min → **18 contiguous 10-min chunks**.

| Quantity | Value |
|---|---|
| Transcript per chunk | 1,500 words ≈ **2,000 tokens** |
| Unit-ID markers (~40/chunk) | ≈ **600 tokens** |
| System prompt + rubric + JSON schema | ≈ **1,000 tokens** |
| **Input per call** | ≈ **3,600 tokens** |
| Rounds (one per chunk) | **18** |
| **Total input** | ≈ **65,000 tokens** |
| Output per call (selected IDs + score) | ≈ 250 tokens |
| **Total output** | ≈ **4,500 tokens** |

Cost = `(in_tokens/1e6 × in_price) + (out_tokens/1e6 × out_price)`.

| Model tier (illustrative — **verify on OpenRouter**) | in $/M | out $/M | Cost per 3h class |
|---|---|---|---|
| 1B ultra-cheap | 0.02 | 0.10 | **≈ $0.0018** |
| 1B typical | 0.05 | 0.20 | **≈ $0.0042** |
| 7B-class | 0.20 | 0.40 | **≈ $0.015** |
| Small mid-tier | 0.30 | 0.60 | **≈ $0.022** |

> **[v1.0 CORRECTION]** My earlier ~104k tokens / 20 overlapping-window estimate was **high for your architecture**. Under **contiguous chunks** the accurate figure is **≈65k tokens / 18 calls**. The spec's original "~50k tokens" was therefore **closer to right than my v1.0 figure** — I overstated it. The spec was mildly low, not 2× low.

### 15.5 Latency

18 sequential calls × ~0.3–0.5s ≈ **5–9s** total. Trivially within NFR-3. (A per-15s-slide design would be ~700 calls → 3.5+ min sequential.)

### 15.6 Prompt caching

The system prompt + rubric + schema (~1,000 tokens) is identical across all 18 calls. Design the prompt with a **byte-identical stable prefix** to enable provider prompt-caching (~10% cost on hits). Small money, free to ask for.

---

## 16. Proposal 2 — Two reference files

> *"keep a reference file for the timestamps, that will have two values of timestamps and the exact video frame. lets keep two files, one to map with the window cuts, and one for the sliding cuts."*

### 16.1 Verdict: **Approved — and this is the single best idea in the set.**

An authoritative time-map is exactly the missing contract from flaw §5.3. But two hand-maintained files will drift. Fix: **one authoritative, the other derived, both validated.**

### 16.2 Stress test — what breaks

| Attack | Result |
|---|---|
| **Timestamp vs. frame drift** | Two fields for one instant diverge. **Rule: `sec` authoritative; `frame` derived = `round(sec × fps)`.** Recompute at load; never trust a stored frame independently. |
| **Unit ambiguity** | Pick **one canonical time unit**: seconds (float) + derived integer frame, with stored `fps`/`timebase`. |
| **PTS vs. wall-clock** | `.vtt` times are wall-clock; container PTS can differ by a start offset. Store `video_start_time_sec` from `ffprobe` and normalize. |
| **Two files drift** | If generated independently, a partial re-run desyncs them. **Derive file 2 from file 1** in one pass; pin both to the same `job_id`/`source_hash`. |
| **Separate cut paths** | Sliding cuts must be **derived from the precise set**, not re-cut from the chunk (which compounds keyframe error). One cutter, one input. |
| **Staleness after recompute** | Version everything with `schema_version`; regenerate downstream artifacts whenever slides change. |

### 16.3 Corrected design

**File 1 — `segments.json` (authoritative, precise).** One entry per transcript cue/sentence, absolute video time, frame derived.

```json
{
  "schema_version": "1.0",
  "job_id": "class-2026-09-23-a1",
  "source": "class.mp4",
  "source_hash": "sha256:...",
  "video_duration_sec": 10800.0,
  "fps": 29.97,
  "timebase": "1/90000",
  "video_start_time_sec": 0.0,
  "segments": [
    { "id": "s000001", "start_sec": 12.40, "end_sec": 14.10,
      "start_frame": 372, "end_frame": 422,
      "text": "Welcome back to today's IELTS writing session." }
  ]
}
```

**File 2 — `windows.json` (derived).** Chunks + 15-30s candidate units, linked to the precise set **by segment ID**, never by timestamp.

```json
{
  "schema_version": "1.0",
  "job_id": "class-2026-09-23-a1",
  "windows": [
    {
      "id": "chunk_003",
      "start_sec": 1200.0, "end_sec": 1800.0,
      "start_frame": 35964, "end_frame": 53946,
      "gop_start_sec": 1200.0,
      "candidates": [
        { "id": "w003_c07", "start_sec": 1380.0, "end_sec": 1410.0,
          "start_frame": 41363, "end_frame": 42254,
          "segment_ids": ["s000812","s000813"] }
      ]
    }
  ]
}
```

**Invariants to enforce in code (fail loudly):**
1. `segment.start_frame == round(segment.start_sec × fps)` within tolerance 1.
2. Every `candidate.segment_ids` resolves to real segments.
3. `candidate.start_sec` within `[window.start_sec, window.end_sec]`.
4. `end_sec > start_sec` and duration within policy bounds.
5. All `start_sec` ∈ `[0, video_duration_sec]`.
6. `source_hash` matches the file being cut.

**Recommended third derived artifact — the seam between decision and cutting.** `final_clips.json` per selected clip: `absolute_start_sec`, `absolute_end_sec`, `start_frame`, `end_frame`, `nearest_keyframe_start_sec`, `segment_ids`, `model_score`, `rationale`. This is **the only input the cutter reads**; it doubles as the run manifest (R-G1) and resume checkpoint (R-G2).

### 16.4 Keyframe reality check

A perfect *map* still cannot make `-c copy` cut at a non-keyframe. `final_clips.json` should record `nearest_keyframe_start_sec` (from `ffprobe -skip_frame nokey`) so the cutter knows **whether the in-point is reachable** in copy mode, and falls back to the short re-encode (ADR-002) when it is not. **The map is authoritative for intent; the keyframe check is authoritative for feasibility.**

---

## 17. Proposal 3 — Jev via OpenRouter + corrected cost

> *"i will use jev model from openrouter to send the sliding 15s-30s transcript to openrouters jev. if the cost is not correct, give me the correct one."*

### 17.1 Disposition of the earlier concern

Routing via OpenRouter gives a standard, authenticated `chat/completions` surface with the model selectable by ID. That **retires my v1.0 objection** that the raw `api.typesafe.ai` endpoint could not be verified. The `DecisionEngine` abstraction (ADR-003) still applies: `JevViaOpenRouterEngine` becomes **one concrete adapter**, keeping a fallback model one config line away.

### 17.2 Corrected cost (the answer you asked for)

Using §15.4 — **≈65,000 input + ≈4,500 output tokens per 3-hour class** (per *class*, not per file):

```
cost = (input_tokens  / 1_000_000 × in_price_per_M)
     + (output_tokens / 1_000_000 × out_price_per_M)
```

| Scenario | in/out price | Decision-engine cost / 3h class |
|---|---|---|
| **Jev-class 1B model, typical** | ~$0.05 / $0.20 | **≈ $0.004** |
| Jev-class 1B model, ultra-cheap | ~$0.02 / $0.10 | **≈ $0.002** |
| With prompt caching on the 1k prefix | — | **−15% to −25%** |
| **Full run, Zoom `.vtt`** | — | **≈ $0.002 – $0.006** |
| **Full run, Whisper fallback** | — | **≈ $1.08 + $0.004 ≈ $1.09** |

**Answers:**
- **Is `<$0.003` correct?** *Approximately — slightly optimistic.* Realistic: **$0.002–$0.006** for a 1B model across the two price tiers. Safe statement: **under $0.01 per class.**
- **Where did the original table go wrong?** Not the decision engine — it **mixed a per-minute metric (Whisper) with a per-token metric (Jev)** in one column and treated the decision engine as a single aggregate call. Your chunk model makes it ~18 calls, but each is small, so the total is still pennies.

> **My per-token unit prices are illustrative.** OpenRouter lists live `$/M` per model; plug the real numbers into the formula. The *structure* (65k in / 4.5k out / 18 calls) is what matters and will not move much.

### 17.3 The economic insight that should drive design

**Text is roughly 1,000× cheaper per second than video.**

- The **only** cost that matters at scale is transcription (Whisper) — **100–200× larger than decisioning**. Prioritize the Zoom `.vtt` path (ADR-004); it is not a "nice to have", it is the budget.
- **Doubling transcript redundancy is nearly free** (~$0.002) — so choose windowing for **accuracy, not cost**.
- **Video re-encoding is the CPU cost, not the dollar cost.** Decisioning is dollars-cheap/CPU-free; cutting is CPU-bound/dollar-free. Optimize separately.

### 17.4 Stress test — robustness of a single small routed model

| Attack | Result | Mitigation |
|---|---|---|
| OpenRouter routes a 1B model inconsistently | Small models are more sensitive to prompt/format drift. | Pin the model **version**; keep a fixed regression transcript with expected output. |
| Rate limits / rolling availability | A 1B endpoint may be busy. | Keep the fallback adapter configured; bounded retry. |
| JSON conformance from a 1B model | Highest-risk point. | Strict JSON schema + one repair retry + hard validation before the guard layer. |
| Precision of timestamps from a small model | Poor. | **Already removed** by §15.3 — code snaps boundaries; the model only ranks. This is what makes a 1B model viable at all. |
| Lock-in to one small model | Quality ceiling. | Provider-agnostic interface; A/B a mid-tier model on the same transcript. |

**Conclusion:** a 1B model is viable **because** boundary precision was moved out of the model into code. Had exact-timestamp generation stayed in the prompt, a 1B model would not be trustworthy.

---

## 18. Revised ADRs

- **ADR-001 (revised) — Chunked windows with absolute-time mapping.** *Accepted:* keep 10-minute chunks (you want the cuts), but **mandate absolute timestamps everywhere** and maintain the `segments.json` ↔ `windows.json` mapping with enforced invariants. Model **ranks coarse units**; code **snaps boundaries**. Supersedes the v1.0 "decide over full timeline" preference — correctness is met by mapping + snapping instead.
- **ADR-002 (revised) — Two-stage cut.** *Accepted:* `-c copy` for the 10-min chunks; for 15–30s slides use `-c copy` where the in-point is keyframe-reachable, else a **short re-encode**. `final_clips.json` records `nearest_keyframe_start_sec` to decide.
- **ADR-003 (revised) — Provider-agnostic engine.** *Accepted:* Jev-via-OpenRouter is the default adapter; a fallback + fake adapter ship alongside. Pin model versions.
- **ADR-004 (unchanged) — VTT-first.** Elevated to budget-critical (§17.3).
- **ADR-005 (revised) — Manifest + cost ledger.** *Accepted:* `manifest.json` = `final_clips.json` + usage + spend.
- **ADR-007 (new) — Authoritative time-map with derived artifacts.** *Accepted:* `segments.json` authoritative (`sec` primary, `frame` derived); `windows.json` and `final_clips.json` derived, versioned, validated. Frames never trusted independently of seconds.
- **ADR-008 (new) — Coarse-grid ranking + code-level boundary snapping.** *Accepted:* the model ranks 30s-or-15s units; sentence-boundary snapping is deterministic in code. Prerequisite for a 1B model.

---

## 19. Open Decisions (need your call before build)

1. **Unit grid for ranking:** non-overlapping **30s** (20/chunk, simple, cheaper) vs **15s** (40/chunk, finer, more tokens)? *Recommend 30s ranking + code snapping to 15–30s output.*
2. **Refine pass:** ship rank-only first, add top-K refine only if quality demands? *Recommend defer.*
3. **Window overlap:** contiguous 18 chunks, or **overlap ~1 min** to avoid losing boundary-straddling moments (§5.4)? *Recommend overlap — near-free in text.*
4. **Canonical time unit:** confirm **seconds (float) + derived integer frames** at `ffprobe` fps.
5. **Exact OpenRouter model ID + live `$/M` prices.**
6. **Artifact set:** approve the 3-file model (authoritative → derived → derived), replacing the 2-file proposal?
7. **`fps` source of truth:** use container `r_frame_rate` (may be 30000/1001) not a rounded 30 — confirm.

---

## 20. Bottom Line for v1.1

- **Proposal 1 — approved with one change:** a **coarse, mostly non-overlapping unit grid for the model to rank**, with **15–30s boundary precision in code**. That single change is what makes the cheap model, low cost, and low latency feasible.
- **Proposal 2 — approved and improved:** **one authoritative file, two derived**; `sec` primary, `frame` derived; link by **segment ID**, not timestamp; add `final_clips.json` as the single cutter input and keyframe-feasibility record.
- **Proposal 3 — corrected.** A 1B Jev-class model puts the decision layer at **≈ $0.002–$0.006 per 3-hour class** (<$0.01); the spec's `<$0.003` was *close but slightly low*. Total run = **≈$0.002–$0.006 (VTT)** or **≈$1.09 (Whisper)**. The budget lever is **transcription, not decisioning.**
- **[v1.0 self-correction]** the earlier ~104k-token estimate was high for your architecture; accurate is **≈65k tokens / 18 calls**.
