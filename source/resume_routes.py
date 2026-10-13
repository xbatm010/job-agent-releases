"""Conservative CV selection independent of job scoring or auto-submission.

The primary (existing) PDF is always the data/BI fallback. A secondary
support/QA PDF is selected only for clear support or software QA role titles.
No global profile data, candidate name or CV bytes are stored here.
"""
import re
import unicodedata
from pathlib import Path


SUPPORT_QA_PATTERNS = [
    # English helpdesk / support / application operations titles.
    r"\b(?:it|tech(?:nical)?|customer|desktop|application|software|product|user)\s+support\b",
    r"\b(?:support|service\s*desk|help\s*desk)\s+(?:analyst|specialist|engineer|technician|agent|associate)\b",
    r"\bhelp\s*desk\b", r"\bservice\s*desk\b",
    r"\b(?:l1|level\s*1|first\s*line|1st\s*line)\s+support\b",
    r"\bit\s+(?:technician|technician|administrator)\b",
    # Manual QA / tester titles, avoid penetration/security testers.
    r"\b(?:manual|software|qa|quality\s+assurance)\s+test(?:er|ing|analyst|engineer)?\b",
    r"\b(?:qa|quality\s+assurance)\s+(?:analyst|engineer|specialist|trainee|intern)\b",
    r"\b(?:software|application)\s+tester\b",
    r"\btest\s+analyst\b",
    r"\bmanual\s+qa\b",
    r"\b(?:junior\s+)?tester(?:ka)?\b",
    r"\b(?:junior\s+)?test\s+(?:engineer|specialist)\b",
    # Czech; accents removed before matching.
    r"\bit\s+podpor[ay]\b",
    r"\btechnick[ay]\s+podpor[ay]\b",
    r"\buzivatelsk[ay]\s+podpor[ay]\b",
    r"\b(?:specialista|pracovnik|technik)\s+(?:it\s+)?podpory\b",
    r"\b(?:manualni|softwarov[ye]|junior)\s+tester\b",
    r"\btester(?:ka)?\s+(?:software|aplikaci)\b",
    r"\btestovani\s+(?:software|aplikaci)\b",
]
SECURITY_EXCLUSIONS = [
    r"\bpenetration\s+test(?:er|ing)?\b",
    r"\b(?:security|pentest|ethical\s+hacking)\b",
]


def normalize_title(title):
    value = unicodedata.normalize("NFKD", str(title or "").casefold())
    value = "".join(x for x in value if not unicodedata.combining(x))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def resume_group_for_job(job):
    """Return support_qa for explicit support/QA titles; data for everything else.

    An unfamiliar/ambiguous title keeps the user's existing primary CV,
    avoiding a silent switch to the secondary CV.
    """
    raw_title = job.get("actual_title") or job.get("title") or ""
    title = normalize_title(raw_title)
    if any(re.search(x, title) for x in SECURITY_EXCLUSIONS):
        return "data"
    if any(re.search(x, title) for x in SUPPORT_QA_PATTERNS):
        return "support_qa"
    return "data"


def choose_resume(job, primary_cv_path, support_qa_cv_path=""):
    """Return (category, selected path), or reject missing secondary CV.

    Raises before opening any employer form. Explicit paths are not packaged
    with the app, so a user may change them under Settings > Files.
    """
    group = resume_group_for_job(job or {})
    if group == "support_qa":
        path = str(support_qa_cv_path or "").strip()
        if not path:
            raise ValueError(
                "Для вакансии IT Support / QA укажите отдельное PDF "
                "в Настройки → Файлы → CV для IT Support / QA."
            )
    else:
        path = str(primary_cv_path or "").strip()
    if not path:
        raise ValueError("В Настройки → Файлы укажите PDF-резюме для Data / BI.")
    file = Path(path).expanduser()
    if file.suffix.lower() != ".pdf":
        raise ValueError("Резюме должно быть PDF-файлом.")
    if not file.is_file():
        raise FileNotFoundError("CV file not found: " + str(file))
    return group, str(file)
