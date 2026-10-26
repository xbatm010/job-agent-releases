"""Aggregate-only diagnostics for Job Agent scoring; no applicant or vacancy PII.

This module is deliberately read-only with respect to application decisions.
It is never used to promote REVIEW to APPLY or initiate submissions.
"""
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile


TRACKS = ("data", "support", "qa", "other")
DECISIONS = ("APPLY", "REVIEW", "SKIP")
BLOCKER_LABELS = {
    "location": "местоположение",
    "experience": "обязательный опыт",
    "evidence": "недостаточно данных вакансии",
    "required_skills": "обязательные навыки",
    "skills_fit": "совпадение навыков",
    "entry_level": "нет подтверждения Junior/L1",
    "role_signals": "технические сигналы",
    "advanced_requirements": "сложные обязательные технологии",
    "source": "источник только для просмотра",
    "score": "порог оценки",
    "role": "нерелевантная специализация",
    "manual": "ручное решение",
    "other": "нужна ручная проверка",
}


def blocker_categories(job):
    """Ordered evidence-grounded reasons. No speculative candidate assessment."""
    if str(job.get("decision", "")).upper() == "APPLY":
        return []
    reasons = job.get("reasons") or []
    if not isinstance(reasons, (list, tuple)):
        reasons = []
    combined = " ".join(map(str, reasons)).lower()
    blockers = [
        str(x).lower() for key in ("target_apply_blockers", "expanded_apply_blockers")
        for x in (job.get(key) or []) if isinstance(x, str)
    ]
    txt = " | ".join(blockers)
    location = str(job.get("location_gate") or "").lower()
    cats = []
    def add(name, condition):
        if condition and name not in cats:
            cats.append(name)

    add("manual", "desktop_override:skip" in combined)
    add("location", "location_gate:" in combined
        or "unknown" in location or "outside" in location or "blocked" in location)
    add("experience", bool(job.get("hard_experience"))
        or bool(job.get("junior_experience_requirement"))
        or "years experience requirement" in txt
        or "experience requirement or ambiguous" in txt)
    add("evidence", str(job.get("evidence_quality", "")).lower() != "strong"
        or "strong description evidence required" in txt)
    add("required_skills", "missing_required_skills" in txt
        or "missing_required_skills=" in combined)
    add("skills_fit", "candidate_fit=" in txt or "fewer than 2 familiar skill signals" in txt)
    add("entry_level", "marker absent" in txt)
    add("role_signals", "independent role signals" in txt
        or "no concrete diagnostic/test evidence" in txt
        or "data_signals=" in txt or "no central data signal" in txt)
    add("advanced_requirements", "advanced mandatory" in txt)
    add("source", str(job.get("source", "")).lower() == "startupjobs.cz"
        or "discovery_only_source:" in combined)
    add("score", ("score=" in txt and " < " in txt)
        or not blockers and str(job.get("decision", "")).upper() == "REVIEW")
    add("role", str(job.get("role_class", "")).lower() in {"other", "adjacent", "excluded"})
    if not cats:
        cats.append("other")
    return cats


def summarize_fit(scored, stages, track_fn=None, recorded_at=None):
    """Return a privacy-preserving funnel, across ALL scored jobs, not the shortlist.

    A vacancy contributes at most once per decision/track/primary blocker.
    Secondary blockers are counted separately and may overlap.
    """
    counts = Counter()
    tracks = {track: Counter() for track in TRACKS}
    primary = Counter()
    secondary = Counter()
    for job in scored:
        decision = str(job.get("decision", "")).upper()
        if decision not in DECISIONS:
            continue
        track = (track_fn(job) if track_fn else job.get("track")) or "other"
        if track not in tracks:
            track = "other"
        counts[decision] += 1
        tracks[track][decision] += 1
        if decision == "APPLY":
            continue
        categories = blocker_categories(job)
        primary[categories[0]] += 1
        secondary.update(categories)
    stage_names = ("discovered", "selected_for_enrichment", "deduplicated", "scored", "shortlisted")
    clean_stages = {}
    for name in stage_names:
        value = stages.get(name, 0)
        clean_stages[name] = max(0, int(value)) if isinstance(value, int) and not isinstance(value, bool) else 0
    return {
        "schema": 1,
        "generated_at": recorded_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "stages": clean_stages,
        "decisions": {key: counts[key] for key in DECISIONS},
        "by_track": {track: {key: tracks[track][key] for key in DECISIONS} for track in TRACKS},
        "primary_blockers": dict(sorted(primary.items())),
        "all_blockers": dict(sorted(secondary.items())),
    }


def format_fit_summary(report):
    """Plain-text Desktop summary, never execute or trust remote content."""
    if not isinstance(report, dict) or report.get("schema") != 1:
        return ""
    decisions = report.get("decisions") or {}
    primary = report.get("primary_blockers") or {}
    if not isinstance(decisions, dict) or not isinstance(primary, dict):
        return ""
    top = sorted(
        ((name, n) for name, n in primary.items()
         if name in BLOCKER_LABELS and type(n) is int and n > 0),
        key=lambda item: (-item[1], item[0]),
    )[:3]
    blockers = ", ".join(f"{BLOCKER_LABELS[name]}: {n}" for name, n in top) or "не обнаружены"
    counts = [max(0, int(decisions.get(name, 0))) if type(decisions.get(name, 0)) is int else 0
              for name in DECISIONS]
    return (f"Диагностика последнего поиска: APPLY {counts[0]} · "
            f"REVIEW {counts[1]} · SKIP {counts[2]} "
            f"  |  Главные причины: {blockers}")


def save_fit_report(report, path):
    """Atomic local-only JSON. Save a fixed aggregate schema, never raw jobs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".fit-report-", suffix=".tmp", delete=False,
        ) as fh:
            temporary = Path(fh.name)
            json.dump(report, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
