import copy
import hashlib
import json
import math


_COMMON = {
    "min_s": 60,
    "target_s": 75,
    "max_s": 90,
    "weights": {"value": 0.30, "clarity": 0.20, "opening": 0.10, "postable": 0.40},
    "minimums": {"value": 2, "clarity": 2, "postable": 2},
    "criteria": [],
    "suggest_criteria": False,
    "criteria_proposed": False,
    "criteria_confirmed": False,
}

PRESETS = {
    "general": {
        "label": "Best moments",
        "intent": "Find complete, compelling moments that are useful or enjoyable without the rest of the video.",
        "categories": {"insight": "A useful insight.", "demonstration": "A demonstration or example.",
                       "reaction": "A strong reaction or exchange.", "story": "A self-contained story beat.",
                       "highlight": "Another notable highlight.", "other": "None of the above."},
    },
    "education": {
        "label": "Education",
        "intent": "Find clear, accurate teaching moments with a practical takeaway.",
        "categories": {"explanation": "A clear explanation.", "worked_example": "A worked example.",
                       "tip": "A practical tip.", "common_mistake": "A mistake and correction.",
                       "exercise": "A question or exercise.", "other": "None of the above."},
    },
    "interview": {
        "label": "Interview",
        "intent": "Find memorable answers, stories, opinions, and advice that stand alone.",
        "categories": {"answer": "A strong direct answer.", "story": "A personal or reported story.",
                       "insight": "A notable insight.", "advice": "Actionable advice.",
                       "debate": "A disagreement or provocative view.", "other": "None of the above."},
    },
    "product": {
        "label": "Product",
        "intent": "Find product moments that clearly show a problem, capability, workflow, or result.",
        "categories": {"feature_demo": "A feature demonstration.", "problem_solution": "A problem and solution.",
                       "workflow": "A useful workflow.", "proof": "Evidence or a result.",
                       "announcement": "A product announcement.", "other": "None of the above."},
    },
    "story": {
        "label": "Story",
        "intent": "Find emotionally or narratively complete moments with a strong setup and payoff.",
        "categories": {"hook": "A strong setup.", "tension": "Conflict or rising tension.",
                       "turning_point": "A meaningful turn.", "reveal": "A reveal or realization.",
                       "emotion": "An emotionally strong moment.", "resolution": "A payoff or resolution.",
                       "other": "None of the above."},
    },
    "ielts": {
        "label": "IELTS lesson",
        "intent": "Find complete, useful IELTS teaching moments for learners.",
        "categories": {"exam_tip": "A tip or strategy for the IELTS exam itself.",
                       "worked_example": "The teacher works through an example or sample answer.",
                       "common_mistake": "A learner mistake and its correction.",
                       "vocabulary": "A word, phrase, or collocation and how to use it.",
                       "practice_exercise": "An exercise or question learners can try.",
                       "other": "None of the above."},
    },
}


def resolve(profile=None, default="general"):
    if profile is None:
        profile = {"preset": default}
    elif isinstance(profile, str):
        profile = {"preset": profile}
    if not isinstance(profile, dict):
        raise ValueError("profile must be a preset name or object")
    preset = profile.get("preset", default)
    if preset not in PRESETS:
        raise ValueError(f"unknown profile preset: {preset}")
    out = {**_COMMON, **copy.deepcopy(PRESETS[preset]), **copy.deepcopy(profile), "preset": preset}
    out["intent"] = str(out.get("intent") or "").strip()
    if not out["intent"]:
        raise ValueError("profile intent is required")
    criteria = out.get("criteria") or []
    if not isinstance(criteria, list) or not all(isinstance(v, str) and v.strip() for v in criteria):
        raise ValueError("profile criteria must be a list of non-empty strings")
    out["criteria"] = [v.strip() for v in criteria][:12]
    for key in ("suggest_criteria", "criteria_proposed", "criteria_confirmed"):
        if not isinstance(out.get(key), bool):
            raise ValueError(f"profile {key} must be true or false")
    categories = out.get("categories")
    if not isinstance(categories, dict) or not categories or not all(
            isinstance(k, str) and k and isinstance(v, str) and v.strip() for k, v in categories.items()):
        raise ValueError("profile categories must be a non-empty object")
    out["categories"] = {k: v.strip() for k, v in categories.items()}
    try:
        out["min_s"], out["target_s"], out["max_s"] = (int(out[k]) for k in ("min_s", "target_s", "max_s"))
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError("profile durations must be whole seconds") from e
    if not 5 <= out["min_s"] <= out["target_s"] <= out["max_s"] <= 600:
        raise ValueError("profile durations must satisfy 5 <= min <= target <= max <= 600")
    weights = out.get("weights") or {}
    keys = ("value", "clarity", "opening", "postable")
    try:
        weights = {k: float(weights[k]) for k in keys}
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"profile weights must contain {', '.join(keys)}") from e
    total = sum(weights.values())
    if total <= 0 or any(not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError("profile weights must be non-negative and total more than zero")
    out["weights"] = {k: v / total for k, v in weights.items()}
    minimums = out.get("minimums") or {}
    try:
        minimums = {k: float(minimums[k]) for k in ("value", "clarity", "postable")}
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError("profile minimums must contain value, clarity, and postable") from e
    if any(not math.isfinite(v) or not 0 <= v <= 4 for v in minimums.values()):
        raise ValueError("profile minimums must be between zero and four")
    out["minimums"] = minimums
    return out


def fingerprint(profile):
    data = json.dumps(resolve(profile), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(data.encode()).hexdigest()[:12]
