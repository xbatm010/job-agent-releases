"""Independent, conservative entry-level IT Support and Manual QA track.

Data/BI scoring is intentionally untouched. A technical title alone is not
proof of fit: evidence, specific descriptions, seniority and unmet technical
requirements gate automatic preparation. Final Submit remains human-only.
"""
import re

from resume_routes import normalize_title

SUPPORT_PATTERNS = (
    r"\bit support\b",
    r"\b(?:technical|application|software|desktop|user|product) support\b",
    r"\b(?:help ?desk|service ?desk)\b",
    r"\bl1 support\b",
    r"\b(?:it|technicka|uzivatelska) podpora\b",
    r"\b(?:specialista|pracovnik|technik) (?:it )?podpory\b",
)
QA_PATTERNS = (
    r"\b(?:manual|software|qa|quality assurance) test(?:er|ing|engineer|analyst)?\b",
    r"\btester(?:ka)?\b",
    r"\btest (?:analyst|engineer|specialist)\b",
    r"\bqa (?:engineer|analyst|specialist|trainee|intern)\b",
    r"\btestovani (?:softwaru|software|aplikaci)\b",
)
BLOCKED_PATTERNS = (
    r"\b(?:penetration|security|pentest|ethical hacking|cybersecurity)\b",
    r"\b(?:game tester|gaming qa)\b",
    r"\b(?:customer service|call center|telesales|sales support)\b",
)
ENTRY_PATTERNS = (
    r"\b(?:junior|trainee|intern|internship|graduate|entry level|l1|level 1|first line|"
    r"1st line|absolvent|stazista|staz|bez praxe)\b",
)
SUPPORT_SIGNAL_PATTERNS = {
    "troubleshooting": r"\b(?:troubleshoot|diagnos|resolv(?:e|ing)|problem solving|reseni problem|reseni incident)\b",
    "incident_tickets": r"\b(?:ticket(?:ing|s)?|incident|service ?desk|help ?desk|jira|servicenow)\b",
    "technical_support": r"\b(?:windows|macos|operating system|hardware|software support|it support|technicka podpora)\b",
    "user_communication": r"\b(?:user support|uzivatelsk|customer communication|customer support|technical documentation|dokumentace)\b",
    "basic_network": r"\b(?:dns|tcp/?ip|network|sitov|vpn|remote desktop)\b",
}
QA_SIGNAL_PATTERNS = {
    "manual_testing": r"\b(?:manual test|manualni test|rucni test|functional test|funkcni test)\b",
    "regression": r"\b(?:regression|regresni)\b",
    "test_cases": r"\b(?:test cas(?:e|es)|testovaci scenar|test plan|test scenario)\b",
    "defect_tracking": r"\b(?:bug|defect|issue track|reproduc|jira)\b",
    "web_testing": r"\b(?:web app|browser|playwright|selenium|test automation)\b",
    "api_sql": r"\b(?:postman|api test|sql|database test)\b",
}
# These are positive signals supported by the candidate's education and
# Job Agent personal project. Do not imply formal industry employment.
CANDIDATE_FAMILIAR = {
    "support": {"troubleshooting", "user_communication", "technical_support", "incident_tickets"},
    "qa": {"manual_testing", "regression", "defect_tracking", "web_testing", "api_sql"},
}
# Explicit requirements outside the documented candidate skill set force
# manual review. Do not reject a mere optional mention in a longer advert.
ADVANCED_REQUIRED = (
    r"\b(?:required|must have|essential|pozadujeme|vyzadujeme|nutna znalost)"
    r".{0,100}\b(?:active directory|windows server|ccna|istqb advanced|"
    r"selenium webdriver|cypress|java development|c# development|"
    r"kubernetes|vmware administration)\b",
    r"\b(?:active directory|windows server|ccna|istqb advanced|"
    r"kubernetes|vmware administration)\b.{0,100}"
    r"\b(?:required|must have|essential|pozadujeme|vyzadujeme)\b",
)


def support_qa_track(title):
    """Return 'support', 'qa' or None using the real vacancy title only."""
    normalized = normalize_title(title)
    if any(re.search(pattern, normalized) for pattern in BLOCKED_PATTERNS):
        return None
    if any(re.search(pattern, normalized) for pattern in QA_PATTERNS):
        return "qa"
    if any(re.search(pattern, normalized) for pattern in SUPPORT_PATTERNS):
        return "support"
    return None


def support_qa_assessment(job, hard_experience=False):
    """Pure assessment with unambiguous decision and reasons; never uploads."""
    title = str(job.get("actual_title") or job.get("title") or "")
    track = support_qa_track(title)
    if track is None:
        return None
    description = normalize_title(job.get("description") or "")
    evidence = str(job.get("evidence_quality") or "weak").lower()
    patterns = SUPPORT_SIGNAL_PATTERNS if track == "support" else QA_SIGNAL_PATTERNS
    signals = [
        name for name, pattern in patterns.items()
        if re.search(pattern, description)
    ]
    matched = [name for name in signals if name in CANDIDATE_FAMILIAR[track]]
    entry = any(re.search(pattern, normalize_title(title)) for pattern in ENTRY_PATTERNS)
    # Regular unspecified positions may be shortlisted for human evaluation,
    # but only clearly junior adverts can be marked ready for preparation.
    advanced_required = any(re.search(pattern, description) for pattern in ADVANCED_REQUIRED)
    blockers = []
    if evidence != "strong":
        blockers.append("strong description evidence required")
    if hard_experience:
        blockers.append("experience 3+ years requirement")
    if not entry:
        blockers.append("junior/trainee/L1 marker absent")
    if len(signals) < 2:
        blockers.append("fewer than 2 independent role signals")
    if len(matched) < 2:
        blockers.append("fewer than 2 familiar skill signals")
    if advanced_required:
        blockers.append("advanced mandatory technical requirements")
    candidate_fit = min(30, len(matched) * 8)
    role_fit = 40 + (6 if entry else 0)
    experience_fit = 13 if not hard_experience else 0
    score = min(100, role_fit + candidate_fit + experience_fit + (5 if evidence == "strong" else 0))
    ready = not blockers and score >= 66
    # Preserve discovery visibility even when title matches but details are
    # incomplete; such rows must not enter auto-preparation queue.
    if ready:
        decision = "APPLY"
    elif not hard_experience and score >= 42:
        decision = "REVIEW"
    else:
        decision = "SKIP"
    return {
        "score": int(score),
        "decision": decision,
        "role_class": "target",
        "role_track": track,
        "role_fit": role_fit,
        "candidate_fit": candidate_fit,
        "experience_fit": experience_fit,
        "language_fit": 0,
        "location_fit": 0,
        "target_candidate_fit_min": 16,
        "target_apply_blockers": blockers,
        "expanded_role_eligible": False,
        "expanded_candidate_fit_min": None,
        "expanded_apply_blockers": [],
        "expanded_entry_promotion": False,
        "expanded_signal_bonus": 0,
        "expanded_signals": signals,
        "matched": matched,
        "gaps": ["advanced technical requirements"] if advanced_required else [],
        "required_skills": [],
        "preferred_skills": [],
        "hard_experience": bool(hard_experience),
        "soft_experience_penalty": 0,
        "verified_target_promotion": False,
        "entry_role": entry,
        "confidence": {"strong": "high", "medium": "medium", "weak": "low"}.get(evidence, "low"),
        "evidence_verified": evidence == "strong",
        "reasons": [
            f"track={track}", f"entry_role={entry}", f"evidence={evidence}",
            "track_signals=" + (",".join(signals) or "none"),
            "familiar_signals=" + (",".join(matched) or "none"),
            "track_apply_blockers=" + ("; ".join(blockers) or "none"),
        ],
    }
