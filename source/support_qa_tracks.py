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
    r"\b(?:customer service|call center|telesales|sales support|presales)\b",
    # Czech commercial/technical sales support is not IT helpdesk.
    r"\b(?:technicka podpora prodeje|podpora prodeje|obchodni podpora|"
    r"technicke nabidky|obchodnich nabidek)\b",
    r"\btechnical sales(?: support)?\b",
)
ENTRY_PATTERNS = (
    r"\b(?:junior|trainee|intern|internship|graduate|entry level|l1|level 1|first line|"
    r"1st line|absolvent|stazista|staz|bez praxe)\b",
)
SUPPORT_SIGNAL_PATTERNS = {
    "troubleshooting": r"\b(?:troubleshoot(?:ing|er|s)?|diagnos(?:e|is|tic|ing)?|resolv(?:e|ing)|problem solving|reseni problemu?|reseni incidentu?)\b",
    "incident_tickets": r"\b(?:ticket(?:ing|s)?|incident|service ?desk|help ?desk|jira|servicenow)\b",
    "technical_support": r"\b(?:windows|macos|operating system|hardware|software support|it support|technicka podpora)\b",
    "user_communication": r"\b(?:user support|uzivatelsk|customer communication|customer support|technical documentation|dokumentace)\b",
    "basic_network": r"\b(?:dns|tcp/?ip|network|sitov|vpn|remote desktop)\b",
}
QA_SIGNAL_PATTERNS = {
    "manual_testing": r"\b(?:manual test(?:ing|s|er)?|manualni testovani|manualni testy?|rucni testovani|rucni testy?|functional test(?:ing|s)?|funkcni testovani|funkcni testy?)\b",
    "regression": r"\b(?:regression|regresni)\b",
    "test_cases": r"\b(?:test cas(?:e|es)|testovaci scenar|test plan|test scenario)\b",
    "defect_tracking": r"\b(?:bug|defect|issue track|reproduc|jira)\b",
    "web_testing": r"\b(?:web app|browser|playwright|selenium|test automation)\b",
    "api_sql": r"\b(?:postman|api test|sql|database test)\b",
}
# These are positive signals supported by the candidate's education and
# Job Agent personal project. Do not imply formal industry employment.
# Generic IT and communications vocabulary alone is not hands-on technical
# evidence. A concrete diagnostic / ticket / network / test signal is required
# before preparing a user-facing form; otherwise the job stays for review.
PRACTICAL_SIGNALS = {
    "support": {"troubleshooting", "incident_tickets", "basic_network"},
    "qa": {"manual_testing", "regression", "test_cases", "defect_tracking", "web_testing", "api_sql"},
}

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


# Only explicit, affirmative employer statements may replace an entry-level
# marker in the title. A generic "training" benefit or mention of graduates
# elsewhere in a full HTML page cannot by itself qualify a vacancy.
DESCRIPTION_ENTRY_PATTERNS = (
    r"\b(?:no|without)\s+(?:(?:prior|previous|professional|commercial|work)\s+){0,2}"
    r"experience\s+(?:is\s+)?(?:required|necessary|needed)\b",
    r"\b(?:prior|previous|professional|commercial|work)\s+experience\s+"
    r"(?:is\s+)?(?:not|isnt)\s+(?:required|necessary|needed)\b",
    r"\bexperience\s+(?:is\s+)?(?:not|isnt)\s+(?:required|necessary|needed)\b",
    r"\b(?:graduates?\s+(?:are\s+)?welcome|welcome\s+(?:new\s+)?graduates?|"
    r"open\s+to\s+(?:new\s+)?graduates?|suitable\s+for\s+graduates?)\b",
    r"\b(?:vhodn[aeo]?\s+(?:i\s+)?pro\s+absolventy|"
    r"vitame\s+(?:i\s+)?absolventy|"
    r"absolventy\s+radi\s+zaucime)\b",
    r"\b(?:praxe\s+neni\s+(?:nutna|podminkou|vyzadovana|potreba)|"
    r"predchozi\s+praxe\s+neni\s+(?:nutna|vyzadovana)|"
    r"neni\s+(?:nutna|vyzadovana)\s+(?:predchozi\s+)?praxe|"
    r"bez\s+(?:predchozi\s+)?praxe)\b",
)
# A negative phrase is never positive evidence for entry level.
DESCRIPTION_ENTRY_NEGATIONS = (
    r"\b(?:not\s+suitable\s+for|not\s+open\s+to)\s+graduates?\b",
    r"\b(?:nevhodne\s+pro|neni\s+vhodne\s+pro)\s+absolventy\b",
    r"\b(?:graduates?\s+not\s+accepted|absolventy\s+neprijimame)\b",
)
# Even an explicitly "graduate-friendly" ad must stay REVIEW when it makes
# commercial experience a mandatory requirement. Optional experience phrases
# like "two years is a plus" are deliberately excluded from these patterns.
MANDATORY_JUNIOR_EXPERIENCE = (
    r"\b(?:at\s+least|minimum(?:\s+of)?|min|minimally)\s+"
    r"(?:1|2)\s+years?\s+(?:of\s+)?(?:professional\s+|commercial\s+|work\s+)?experience\b",
    r"\b(?:[12])\s*\+\s*years?\s+(?:of\s+)?(?:professional\s+|commercial\s+|work\s+)?experience\b",
    r"\b(?:min|minimalne|alespon|nejmene)\s*\.?\s*[12]\s*"
    r"(?:rok|roky|roku|let)\s+(?:praxe|zkusenosti)\b",
    r"\b(?:pozadujeme|vyzadujeme|nutna|nutne)\s+(?:alespon\s+)?"
    r"[12]\s*(?:rok|roky|roku|let)\s+(?:praxe|zkusenosti)\b",
    r"\b(?:must\s+have|required|essential|requirements?)\s+"
    r"(?:\w+\s+){0,5}[12]\s+(?:years?\s+(?:of\s+)?)experience\b",
)
# Broad years ranges like "1-2 years of experience" are ambiguous as to
# mandatory vs nice-to-have: do not mark them auto-ready.
AMBIGUOUS_EXPERIENCE = (
    r"\b(?:1\s*(?:-|to|az)?\s+2)\s+(?:years?|rok|roky|roku|let)\s+"
    r"(?:of\s+)?(?:experience|praxe|zkusenosti)\b",
)


def support_qa_entry_evidence(title, description):
    """Return (entry_ok, basis, mandatory_1_2_years).

    Title markers are legacy behavior. Description promotion needs an explicit
    no-experience / graduate welcome statement, not just a generic benefit.
    """
    name = normalize_title(title)
    body = normalize_title(description)
    title_entry = any(re.search(pattern, name) for pattern in ENTRY_PATTERNS)
    positive = any(re.search(pattern, body) for pattern in DESCRIPTION_ENTRY_PATTERNS)
    negative = any(re.search(pattern, body) for pattern in DESCRIPTION_ENTRY_NEGATIONS)
    required = any(re.search(pattern, body) for pattern in MANDATORY_JUNIOR_EXPERIENCE)
    ambiguous = any(re.search(pattern, body) for pattern in AMBIGUOUS_EXPERIENCE)
    # Normalization strips the plus sign: inspect source for explicit 1+/2+.
    plus_required = bool(re.search(
        r"\b[12]\s*\+\s*(?:years?|rok(?:y|u)?|let)\s+"
        r"(?:of\s+)?(?:experience|praxe|zkusenosti)\b",
        str(description or ""), re.I
    ))
    # A clear mandatory requirement or contradictory senior signal blocks
    # auto-preparation even if "Junior" is in the actual job title.
    return (
        (title_entry or positive) and not negative,
        ("none" if negative else
         "title" if title_entry else
         "description" if positive else "none"),
        required or ambiguous or plus_required,
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
    entry, entry_basis, required_junior_experience = support_qa_entry_evidence(
        title, job.get("description") or ""
    )
    # A non-Junior title may now qualify only with explicit, affirmative
    # graduate/no-experience language in the verified vacancy description.
    advanced_required = any(re.search(pattern, description) for pattern in ADVANCED_REQUIRED)
    blockers = []
    if evidence != "strong":
        blockers.append("strong description evidence required")
    if hard_experience:
        blockers.append("experience 3+ years requirement")
    if not entry:
        blockers.append("junior/trainee/L1 marker absent")
    if required_junior_experience:
        blockers.append("1-2 years experience requirement or ambiguous range")
    if len(signals) < 2:
        blockers.append("fewer than 2 independent role signals")
    if len(matched) < 2:
        blockers.append("fewer than 2 familiar skill signals")
    if not PRACTICAL_SIGNALS[track].intersection(signals):
        blockers.append("no concrete diagnostic/test evidence")
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
    # A REVIEW with a generic Support description must never outrank a fully
    # qualified APPLY simply because generic words inflated its raw score.
    if decision == "REVIEW":
        score = min(score, 69)
    elif decision == "SKIP":
        score = min(score, 39)
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
        "entry_evidence": entry_basis,
        "junior_experience_requirement": required_junior_experience,
        "confidence": {"strong": "high", "medium": "medium", "weak": "low"}.get(evidence, "low"),
        "evidence_verified": evidence == "strong",
        "reasons": [
            f"track={track}", f"entry_role={entry}",
            f"entry_evidence={entry_basis}",
            f"junior_experience_requirement={required_junior_experience}",
            f"evidence={evidence}",
            "track_signals=" + (",".join(signals) or "none"),
            "familiar_signals=" + (",".join(matched) or "none"),
            "track_apply_blockers=" + ("; ".join(blockers) or "none"),
        ],
    }
