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
SKILLS = {
    "listening": "IELTS Listening.",
    "reading": "IELTS Reading.",
    "writing": "IELTS Writing (Task 1 or Task 2).",
    "speaking": "IELTS Speaking.",
    "general": "Vocabulary, grammar, or the exam in general.",
}
SCORES = ("value", "clarity", "opening", "postable")
NOULS = ("teacher", "complete", "takeaway", "offtopic", "private")
JEV_QUESTIONS = {
    "value": {"type": "score",
              "instructions": "How much educational value does `excerpt` (from an IELTS class transcript; the teacher "
                              "speaks Bangla and English, shown here in English translation) give IELTS learners?",
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
    "teacher": {"type": "noul",
                "instructions": "Is `excerpt` the class teacher talking to the students (explaining, discussing, "
                                "correcting, giving instructions), rather than a pre-recorded audio or video being "
                                "played in class, such as an IELTS listening-test recording, a lecture or news clip, "
                                "or a narrator reading a passage?",
                "criteria": {"true": "The teacher is speaking to the class.",
                             "false": "A recording, test audio, or narrated passage is being played."}},
    "complete": {"type": "noul",
                 "instructions": "Does `excerpt` finish the point it makes, rather than stopping in the middle of "
                                 "an explanation or example?",
                 "criteria": {"true": "The point is finished by the end of the excerpt.",
                              "false": "It stops before the point is finished."}},
    "postable": {"type": "score",
                 "instructions": "How useful would `excerpt` be on its own as a short YouTube or Facebook video "
                                 "for IELTS learners who never attended this class?",
                 "criteria": [
                     "Not useful: nothing a viewer could learn from it alone.",
                     "Weak: a fragment or a point too thin to post.",
                     "Usable: one ordinary point, fine as filler.",
                     "Good: a clear, specific point viewers would save.",
                     "Excellent: a strong, practical lesson worth sharing.",
                 ]},
    "takeaway": {"type": "noul",
                 "instructions": "Does `excerpt` leave the viewer with a concrete takeaway they can use: a tip, a "
                                 "rule, a model answer, a correction, a useful phrase, or a practice question?",
                 "criteria": {"true": "There is a concrete takeaway.", "false": "No concrete takeaway."}},
    "offtopic": {"type": "noul",
                 "instructions": "Is `excerpt` mainly class logistics or chatter: greetings, attendance, audio or "
                                 "screen problems, asking students to type in the chat, announcements, or small talk?",
                 "criteria": {"true": "Mainly logistics or chatter.", "false": "Mainly teaching content."}},
    "private": {"type": "noul",
                "instructions": "Does `excerpt` mention a real student's personal details, such as a named "
                                "student's score, phone number, or private situation?",
                "criteria": {"true": "It mentions a student's personal details.",
                             "false": "No personal details about a student."}},
    "skill": {"type": "choice",
              "instructions": "Which IELTS part is `excerpt` mainly about?",
              "criteria": SKILLS},
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


def jev_score(excerpt, original=None):
    """Jev reads the English excerpt; the words as spoken ride along when they differ.
    -> scores, the teacher/complete probabilities, the category, and Jev's full answers ("raw")."""
    state = {"excerpt": excerpt, **({"original": original} if original and original != excerpt else {})}
    data, cost = _openrouter(JEV_URL, {"model": "typesafe/jev-1.13", "state": state, "questions": JEV_QUESTIONS})
    try:
        a = data["answers"]
        out = {q: round(float(a[q]["score"]), 2) for q in SCORES}
        out.update({q: round(float(a[q]["noul"]), 3) for q in NOULS})
        out["category"], out["skill"] = a["category"]["choice"], a["skill"]["choice"]
        out["raw"] = a
        if (out["category"] not in CATEGORIES or out["skill"] not in SKILLS
                or not all(0 <= out[q] <= 4 for q in SCORES) or not all(0 <= out[q] <= 1 for q in NOULS)):
            raise ValueError({k: v for k, v in out.items() if k != "raw"})
    except (KeyError, TypeError, ValueError) as e:
        raise ProviderError(f"jev: unexpected answer shape ({e!r})", billed=True, cost=cost) from e
    return out, cost


def _stt(path, model):
    key = _key("OPENROUTER_API_KEY", config.openrouter_key())
    with path.open("rb") as f:
        return httpx.post(STT_URL, headers={"Authorization": f"Bearer {key}"},
                          data={"model": model, "response_format": "verbose_json",
                                "timestamp_granularities[]": ["segment", "word"]},
                          files={"file": (path.name, f, "audio/mpeg")}, timeout=600)


def transcribe(path):
    """Timestamped speech-to-text via OpenRouter, in the language(s) spoken. A 400 (provider rejects timestamps;
    not billed) is retried once with the fallback model."""
    path, model = Path(path), config.STT_MODEL
    r = _stt(path, model)
    if r.status_code == 400 and model != config.STT_FALLBACK_MODEL:
        model = config.STT_FALLBACK_MODEL
        r = _stt(path, model)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data.get("segments"), list) and not isinstance(data.get("words"), list):
        raise ProviderError(f"{model}: response has no timestamped segments", billed=True,
                            cost=(data.get("usage") or {}).get("cost"))
    data["model"] = model
    cost = (data.get("usage") or {}).get("cost")
    return data, cost if cost is not None else data.get("duration", 0) / 60 * config.STT_USD_PER_MIN


TRANSLATE_SYSTEM = (
    "You translate lines from an IELTS class transcript into natural, accurate English. The teacher mixes Bangla "
    "and English. Translate the meaning faithfully; keep English words, IELTS terms, names and numbers as they "
    "are; return a line that is already English unchanged. Never add, explain, or merge lines. "
    'Reply with JSON only: {"en": ["...", ...]} with exactly one string per input line, in the same order.'
)


def translate(lines):
    """English for each as-spoken transcript line, one-to-one."""
    data, cost = _openrouter(CHAT_URL, {
        "model": config.TRANSLATE_MODEL,
        "response_format": {"type": "json_object"},
        "usage": {"include": True},
        "messages": [{"role": "system", "content": TRANSLATE_SYSTEM},
                     {"role": "user", "content": json.dumps({"lines": lines}, ensure_ascii=False)}],
    })
    try:
        en = json.loads(data["choices"][0]["message"]["content"])["en"]
        if len(en) != len(lines) or not all(isinstance(t, str) for t in en):
            raise ValueError(f"{len(en)} lines back for {len(lines)} sent")
    except (KeyError, TypeError, IndexError, ValueError) as e:
        raise ProviderError(f"translate: unexpected answer shape ({e!r})", billed=True, cost=cost) from e
    return {"en": [t.strip() for t in en]}, cost


def draft_post(excerpt, category, english=None):
    help_en = f"\n\nEnglish translation (for understanding only):\n{english}" if english and english != excerpt else ""
    data, cost = _openrouter(CHAT_URL, {
        "model": config.DRAFT_MODEL,
        "response_format": {"type": "json_object"},
        "usage": {"include": True},
        "messages": [{"role": "system", "content": DRAFT_SYSTEM},
                     {"role": "user", "content": f"Category: {category}\n\nExcerpt:\n{excerpt}{help_en}"}],
    })
    try:
        out = json.loads(data["choices"][0]["message"]["content"])
        out = {p: {f: out[p][f] for f in ("title", "description", "cta")} for p in ("facebook", "youtube")}
        if not all(isinstance(v, str) for p in out.values() for v in p.values()):
            raise ValueError("fields must be strings")
    except (KeyError, TypeError, IndexError, ValueError) as e:
        raise ProviderError(f"draft: unexpected answer shape ({e!r})", billed=True, cost=cost) from e
    return out, cost
