"""Paid providers. Each returns (result_dict, cost_usd_or_None) for ledger.call. Never fabricate output."""
import json
from pathlib import Path

import httpx

from shera import config
from shera.ledger import ProviderError

JEV_URL = "https://openrouter.ai/api/alpha/decisions"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
STT_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
CATEGORIES = {
    "exam_tip": "A tip or strategy for the IELTS exam itself.",
    "worked_example": "The teacher works through a concrete example or sample answer.",
    "common_mistake": "A common learner mistake and its correction.",
    "vocabulary": "A word, phrase, or collocation and how to use it.",
    "practice_exercise": "An exercise or question learners can try.",
    "other": "None of the above.",
}
JEV_QUESTIONS = {
    "value": {"type": "score",
              "instructions": "How much educational value does `excerpt` (from an IELTS class transcript) give IELTS learners?",
              "criteria": [
                  "No teaching value: small talk, logistics, or silence.",
                  "Little value: vague or very basic remarks.",
                  "Some value: one useful but ordinary point.",
                  "Clear value: a specific, correct, useful teaching point.",
                  "High value: a specific, memorable point learners can apply right away.",
              ]},
    "clarity": {"type": "score",
                "instructions": "Does `excerpt` stand alone for a viewer who did not see the rest of the class?",
                "criteria": [
                    "Cannot be understood without the missing context.",
                    "Mostly depends on earlier context or unseen material.",
                    "Understandable, but some references are unclear.",
                    "Stands alone with minor gaps.",
                    "Fully self-contained and complete.",
                ]},
    "opening": {"type": "score",
                "instructions": "Is the first sentence of `excerpt` a useful hook into its teaching point?",
                "criteria": [
                    "Starts mid-thought or with filler.",
                    "Weak start that does not point to the topic.",
                    "Acceptable start that names the topic.",
                    "Good start that sets up the point clearly.",
                    "Strong start that makes the viewer want the answer.",
                ]},
    "category": {"type": "choice",
                 "instructions": "Which primary category best fits the teaching in `excerpt`?",
                 "criteria": CATEGORIES},
}
DRAFT_SYSTEM = (
    "You write short posting drafts for a clip from an IELTS class taught in Bangla and English. "
    "Use only what the excerpt says. Write in the same language mix as the excerpt. "
    "Never invent band scores, admissions, results, or any outcome claims. "
    "Do not include logos, handles, @mentions, hashtags of brands, or URLs. Keep the call to action modest. "
    'Reply with JSON only: {"facebook":{"title":"","description":"","cta":""},'
    '"youtube":{"title":"","description":"","cta":""}}'
)


def _key(name, value):
    if not value:
        raise ProviderError(f"{name} not set")
    return value


def _openrouter(url, body):
    key = _key("OPENROUTER_API_KEY", config.openrouter_key())
    r = httpx.post(url, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=120)
    r.raise_for_status()
    data = r.json()
    return data, (data.get("usage") or {}).get("cost")


def jev_score(excerpt):
    data, cost = _openrouter(JEV_URL, {"model": "typesafe/jev-1.13", "state": {"excerpt": excerpt},
                                       "questions": JEV_QUESTIONS})
    try:
        a = data["answers"]
        out = {q: round(float(a[q]["score"]), 2) for q in ("value", "clarity", "opening")}
        out["category"] = a["category"]["choice"]
        if out["category"] not in CATEGORIES or not all(0 <= out[q] <= 4 for q in ("value", "clarity", "opening")):
            raise ValueError(out)
    except (KeyError, TypeError, ValueError) as e:
        raise ProviderError(f"jev: unexpected answer shape ({e!r})", billed=True, cost=cost) from e
    return out, cost


def _stt(path, model):
    key = _key("OPENROUTER_API_KEY", config.openrouter_key())
    with path.open("rb") as f:
        return httpx.post(STT_URL, headers={"Authorization": f"Bearer {key}"},
                          data={"model": model, "response_format": "verbose_json",
                                "timestamp_granularities[]": "segment"},
                          files={"file": (path.name, f, "audio/mpeg")}, timeout=600)


def transcribe(path):
    """Timestamped speech-to-text via OpenRouter. A 400 (provider rejects timestamps; not billed)
    is retried once with whisper-1, whose provider supports them."""
    path, model = Path(path), config.STT_MODEL
    r = _stt(path, model)
    if r.status_code == 400 and model != config.STT_FALLBACK_MODEL:
        model = config.STT_FALLBACK_MODEL
        r = _stt(path, model)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data.get("segments"), list):
        raise ProviderError(f"{model}: response has no timestamped segments", billed=True,
                            cost=(data.get("usage") or {}).get("cost"))
    data["model"] = model
    cost = (data.get("usage") or {}).get("cost")
    return data, cost if cost is not None else data.get("duration", 0) / 60 * config.STT_USD_PER_MIN


def draft_post(excerpt, category):
    data, cost = _openrouter(CHAT_URL, {
        "model": config.DRAFT_MODEL,
        "response_format": {"type": "json_object"},
        "usage": {"include": True},
        "messages": [{"role": "system", "content": DRAFT_SYSTEM},
                     {"role": "user", "content": f"Category: {category}\n\nExcerpt:\n{excerpt}"}],
    })
    try:
        out = json.loads(data["choices"][0]["message"]["content"])
        out = {p: {f: out[p][f] for f in ("title", "description", "cta")} for p in ("facebook", "youtube")}
        if not all(isinstance(v, str) for p in out.values() for v in p.values()):
            raise ValueError("fields must be strings")
    except (KeyError, TypeError, IndexError, ValueError) as e:
        raise ProviderError(f"draft: unexpected answer shape ({e!r})", billed=True, cost=cost) from e
    return out, cost
