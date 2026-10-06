
import asyncio
import csv
import json
import os
import time
import re
import hashlib
import unicodedata
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

AUTO_SUBMIT = os.getenv("AUTO_SUBMIT", "false").lower() == "true"
CONFIRMATION_GATE = os.getenv("CONFIRMATION_GATE", "false").lower() == "true"
ALLOW_JOBS_HANDOFF = os.getenv("ALLOW_JOBS_HANDOFF", "false").lower() == "true"
WORKDAY_MANUAL_BOOTSTRAP = os.getenv("WORKDAY_MANUAL_BOOTSTRAP", "true").lower() == "true"
WORKDAY_WAIT_SECONDS = int(os.getenv("WORKDAY_WAIT_SECONDS", "300"))
PWC_FUTURE_RECRUITMENT_CONSENT = os.getenv("PWC_FUTURE_RECRUITMENT_CONSENT", "").strip().lower()
PWC_EVENTS_CONSENT = os.getenv("PWC_EVENTS_CONSENT", "").strip().lower()
PWC_WORKED_BEFORE = os.getenv("PWC_WORKED_BEFORE", "").strip().lower()
PWC_COUNTRY = os.getenv("PWC_COUNTRY", "").strip()
PWC_CITY = os.getenv("PWC_CITY", "").strip()
PWC_GENDER = os.getenv("PWC_GENDER", "").strip()
PWC_MANUAL_CHOICES_WAIT_SECONDS = int(os.getenv("PWC_MANUAL_CHOICES_WAIT_SECONDS", "180"))
MANUAL_SUBMIT_HOLD = os.getenv("MANUAL_SUBMIT_HOLD", "true").lower() == "true"
MANUAL_SUBMIT_WAIT_SECONDS = int(os.getenv("MANUAL_SUBMIT_WAIT_SECONDS", "600"))
STATE_DIR = Path(os.path.expanduser(os.getenv("STATE_DIR", "~/.job_agent")))
STATE_DIR.mkdir(parents=True, exist_ok=True)
APPLICATIONS_FILE = STATE_DIR / "applications.csv"
VACANCIES_FILE = STATE_DIR / "vacancies.jsonl"
OVERRIDES_FILE = STATE_DIR / "job_overrides.json"
LOGIN_BOOTSTRAP = os.getenv("LOGIN_BOOTSTRAP", "true").lower() == "true"
LOGIN_WAIT_SECONDS = int(os.getenv("LOGIN_WAIT_SECONDS", "240"))
MANUAL_CV_FALLBACK = os.getenv("MANUAL_CV_FALLBACK", "true").lower() == "true"
MANUAL_CV_WAIT_SECONDS = int(os.getenv("MANUAL_CV_WAIT_SECONDS", "180"))
APPLICATION_DEBUG = os.getenv("APPLICATION_DEBUG", "true").lower() == "true"
MIN_APPLY_SCORE = int(os.getenv("MIN_APPLY_SCORE", "73"))
ENTRY_APPLY_SCORE = int(os.getenv("ENTRY_APPLY_SCORE", "68"))
EXPANDED_APPLY_SCORE = int(os.getenv("EXPANDED_APPLY_SCORE", "74"))
EXPANDED_REVIEW_SCORE = int(os.getenv("EXPANDED_REVIEW_SCORE", "62"))
EXPANDED_MIN_DATA_SIGNALS = int(os.getenv(
    "EXPANDED_MIN_DATA_SIGNALS", "3"
))
EXPANDED_MIN_CANDIDATE_FIT = int(os.getenv(
    "EXPANDED_MIN_CANDIDATE_FIT", "12"
))
VERIFIED_TARGET_APPLY_SCORE = int(os.getenv("VERIFIED_TARGET_APPLY_SCORE", "70"))
VERIFIED_TARGET_MIN_CANDIDATE_FIT = int(os.getenv(
    "VERIFIED_TARGET_MIN_CANDIDATE_FIT", "10"
))
MAX_APPLICATIONS_PER_RUN = int(os.getenv("MAX_APPLICATIONS_PER_RUN", "3"))
CONTINUE_AFTER_APPLICATION_ERROR = os.getenv(
    "CONTINUE_AFTER_APPLICATION_ERROR", "true"
).lower() == "true"
BROWSER_EVIDENCE_RECOVERY = os.getenv(
    "BROWSER_EVIDENCE_RECOVERY", "true"
).lower() == "true"
MAX_BROWSER_EVIDENCE_JOBS = int(os.getenv(
    "MAX_BROWSER_EVIDENCE_JOBS", "8"
))
BROWSER_EVIDENCE_WAIT_MS = int(os.getenv(
    "BROWSER_EVIDENCE_WAIT_MS", "1800"
))
BROWSER_EVIDENCE_LEVELS = {
    x.strip().lower() for x in os.getenv(
        "BROWSER_EVIDENCE_LEVELS", "weak"
    ).split(",") if x.strip()
}
STRICT_APPLICATION_ROUTE_VALIDATION = os.getenv(
    "STRICT_APPLICATION_ROUTE_VALIDATION", "true"
).lower() == "true"
AUTO_CZECH_COVER_LETTER = os.getenv(
    "AUTO_CZECH_COVER_LETTER", "true"
).lower() == "true"
COVER_LETTER_LANGUAGE = os.getenv(
    "COVER_LETTER_LANGUAGE", "cs"
).strip().lower()
COVER_LETTER_MAX_CHARS = int(os.getenv(
    "COVER_LETTER_MAX_CHARS", "1200"
))
MICROSITE_CTA_WAIT_MS = int(os.getenv(
    "MICROSITE_CTA_WAIT_MS", "3500"
))
MICROSITE_CTA_RETRIES = int(os.getenv(
    "MICROSITE_CTA_RETRIES", "3"
))
ALLOW_SAME_HOST_REPLY_FALLBACK = os.getenv(
    "ALLOW_SAME_HOST_REPLY_FALLBACK", "true"
).lower() == "true"
MIN_REVIEW_SCORE = int(os.getenv("MIN_REVIEW_SCORE", "60"))
MANUAL_REVIEW_APPLY_MIN_SCORE = int(os.getenv("MANUAL_REVIEW_APPLY_MIN_SCORE", "65"))
MAX_DISCOVERY_ITEMS = int(os.getenv("MAX_DISCOVERY_ITEMS", "30"))
MAX_JOBS_TO_REVIEW = int(os.getenv("MAX_JOBS_TO_REVIEW", "10"))
CV_PATH = os.getenv("CV_PATH", "").strip()
BROWSER_PROFILE_DIR = os.getenv("BROWSER_PROFILE_DIR", "./browser_profile")
SOURCE_JOBS_CZ = os.getenv("SOURCE_JOBS_CZ", "true").lower() == "true"
SOURCE_PRACE_CZ = os.getenv("SOURCE_PRACE_CZ", "true").lower() == "true"
MAX_DISCOVERY_PER_SOURCE = int(os.getenv("MAX_DISCOVERY_PER_SOURCE", "60"))
LOCATION_MODE = os.getenv("LOCATION_MODE", "prague").strip().lower()
ALLOWED_LOCATION_TERMS = [x.strip() for x in os.getenv(
    "ALLOWED_LOCATION_TERMS",
    "Praha,Prague,Stodůlky,Stodulky,Praha-východ,Praha-západ,Říčany,Ricany"
).split(",") if x.strip()]
ALLOW_FULL_REMOTE_OUTSIDE_PRAGUE = os.getenv(
    "ALLOW_FULL_REMOTE_OUTSIDE_PRAGUE", "true"
).lower() == "true"
BLOCKED_LOCATION_TERMS = [x.strip() for x in os.getenv(
    "BLOCKED_LOCATION_TERMS",
    "Brno,Ostrava,Olomouc,Plzeň,Plzen,České Budějovice,Ceske Budejovice,Hradec Králové,Hradec Kralove,Pardubice,Zlín,Zlin,Liberec"
).split(",") if x.strip()]

BASE = "https://www.jobs.cz"
PRACE_BASE = "https://www.prace.cz"

PRACE_SEARCH_ROUTES = [
    ("Datový analytik", "/nabidky/datovy-analytik/"),
    ("Business analytik", "/nabidky/business-analytik/"),
    ("IT analytik Praha", "/nabidky/praha/it-analytik/"),
    ("Data scientist / reporting", "/nabidky/data-scientist/"),
]


KNOWN_EXTERNAL_ROUTES = {
    "2001397904": "https://jobs-cee.pwc.com/ce/en/job/755532WD/Data-Analyst-Financial-Crime-team?utm_source=jobs.cz",
}

KNOWN_COMPANIES = {
    "2001397904": "PricewaterhouseCoopers Česká republika, s.r.o.",
}

SEARCH_QUERIES = [
    # Core target roles
    "Data Analyst",
    "Junior Data Analyst",
    "Business Data Analyst",
    "Reporting Analyst",
    "BI Analyst",
    "Data Reporting Analyst",

    # Broader discovery only; strict full-description gates apply later.
    "Data Specialist",
    "Reporting Specialist",
    "Junior Business Analyst",
    "Data Quality Analyst",
    "Data Quality Specialist",
    "Master Data Specialist",
    "Operations Analyst",
    "CRM Analyst",
    "CRM Data Analyst",
    "Data Operations Analyst",
    "Junior Reporting Specialist",
]

CANDIDATE = {
    "first_name": os.getenv("CANDIDATE_FIRST_NAME", "").strip(),
    "last_name": os.getenv("CANDIDATE_LAST_NAME", "").strip(),
    "email": os.getenv("CANDIDATE_EMAIL", "").strip(),
    "phone": os.getenv("CANDIDATE_PHONE", "").strip(),
    "experience_years": int(os.getenv("CANDIDATE_EXPERIENCE_YEARS", "0")),
    "skills": {
        "sql": "strong",
        "postgresql": "strong",
        "statistical analysis": "strong",
        "spss": "working",
        "excel": "working",
        "data visualization": "working",
        "research": "strong",
        "python": "basic",
        "power bi": "basic",
        "tableau": None,
        "snowflake": None,
        "pandas": None,
        "r": None,
    },
}

EXCLUDED_TITLE_PATTERNS = [
    r"\bsenior\b", r"\bmedior\b", r"\blead\b", r"\bmanager\b",
    r"\bvedouc[íi]\b", r"\bteam\s*lead",
    r"\bprincipal\b", r"\bdirector\b", r"\bhead of\b",
]

TARGET_TITLE_PATTERNS = [
    r"\bdata analyst\b",
    r"\bdata\s+analyt",
    r"\bdatov(?:ý|á|e|ého|ému)?\s*(?:/\s*á)?\s*analyt",
    r"\bdatov.*analyt",
    r"\bbusiness\s*/?\s*datov.*analyt",
    r"\bbusiness\s+analyt",
    r"\breport.*analyt",
    r"\bbi\s+analyt",
    r"\bbusiness data analyst\b",
    r"\breporting analyst\b",
    r"\bdata reporting analyst\b",
    r"\bbi analyst\b",
    r"\bbusiness intelligence analyst\b",
    r"\bdata insight analyst\b",
    r"\bfinancial data analyst\b",
    r"\bsales data analyst\b",
    r"\bmarketing data analyst\b",
    r"\bcustomer data\b.*\banalyst\b",
]

EXPANDED_TITLE_PATTERNS = [
    r"\bdata\s+specialist\b",
    r"\bdatov.*specialist",
    r"\bspecialist.*dat",
    r"\breporting\s+specialist\b",
    r"\bspecialist.*report",
    r"\breportingov.*specialist",
    r"\bdata\s+quality\s+(?:analyst|specialist)\b",
    r"\b(?:analytik|specialista).*kvalit.*dat",
    r"\bmaster\s+data\s+(?:analyst|specialist)\b",
    r"\b(?:specialista|spravce).*kmenov.*dat",
    r"\boperations\s+analyst\b",
    r"\boperational\s+analyst\b",
    r"\bprovozn.*analyt",
    r"\bdata\s+operations\s+(?:analyst|specialist)\b",
    r"\bcrm\s+(?:data\s+)?analyst\b",
    r"\bcrm\s+analyt",
    r"\bdata\s+governance\s+(?:analyst|specialist)\b",
    r"\bdata\s+coordinator\b",
]

ADJACENT_TITLE_PATTERNS = [
    r"\bit analyst\b",
    r"\banalytik.*systém",
    r"\bfinancial analyst\b",
    r"\brisk analyst\b",
    r"\bvaluation analyst\b",
    r"\bsecurity analyst\b",
]

def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_key_text(text):
    text = clean(text).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return clean(text)


def source_from_url(url):
    low = (url or "").lower()
    if "prace.cz" in low:
        return "prace.cz"
    if "jobs.cz" in low:
        return "jobs.cz"
    return "external"


def prace_job_id_from_url(url):
    m = re.search(r"/nabidka/([0-9a-f-]{20,})", url or "", re.I)
    if m:
        return m.group(1).lower()
    m = re.search(r"/odpovedni-formular/([0-9a-f-]{20,})", url or "", re.I)
    return m.group(1).lower() if m else None


def stable_external_id(url):
    digest = hashlib.sha1((url or "").encode("utf-8")).hexdigest()[:16]
    return f"ext-{digest}"


def source_job_id(url):
    source = source_from_url(url)
    if source == "jobs.cz":
        jid = job_id_from_url(url)
        return jid or stable_external_id(url)
    if source == "prace.cz":
        jid = prace_job_id_from_url(url)
        return jid or stable_external_id(url)
    return stable_external_id(url)


def history_key(job):
    return f"{job.get('source', source_from_url(job.get('url', '')))}:{job.get('job_id', '')}"



def canonical_history_key(job):
    """
    Numeric Alma job IDs are shared across Jobs.cz / Prace.cz employer routes.
    Treat them as one application globally, regardless of source portal.
    UUID-native Prace jobs remain source-qualified.
    """
    jid = str(job.get("job_id", "") or "").strip()

    if jid.isdigit():
        return f"job:{jid}"

    url_jid = job_id_from_url(job.get("url", ""))
    if url_jid and str(url_jid).isdigit():
        return f"job:{url_jid}"

    return history_key(job)


def canonicalize_saved_history_id(raw):
    raw = clean(raw or "")
    if not raw:
        return ""

    if raw.startswith("job:") and raw[4:].isdigit():
        return raw

    if raw.isdigit():
        return f"job:{raw}"

    m = re.fullmatch(r"(?:jobs\.cz|prace\.cz):(\d+)", raw, re.I)
    if m:
        return f"job:{m.group(1)}"

    return raw


def browser_evidence_key(job):
    key = canonical_history_key(job)
    if key.startswith("job:"):
        return key

    return "|".join([
        normalize_key_text(job.get("actual_title") or job.get("title", "")),
        normalize_key_text(job.get("company", "")),
        normalize_key_text(job.get("location", "")),
    ])

def dedupe_key(job):
    company = normalize_key_text(job.get("company", ""))
    title = normalize_key_text(job.get("actual_title") or job.get("title", ""))
    location = normalize_key_text(job.get("location", ""))

    # Same employer + same normalized title is treated as the same posting
    # across Alma Career portals. This intentionally favors avoiding duplicate
    # applications over distinguishing same-title city variants.
    if company:
        return f"{company}|{title}"
    return f"{title}|{location}"


def parse_prace_card_company(text):
    text = clean(text)
    m = re.search(
        r"Název\s+firmy:\s*(.+?)(?=\s+(?:Typ\s+úvazku:|Plat:|Dnešní|Včerejší|Méně|Nová|Jen\s+pár|$))",
        text,
        re.I,
    )
    return clean(m.group(1)).rstrip(" ,;") if m else ""


def parse_prace_card_location(text):
    text = clean(text)
    m = re.search(
        r"Lokalita:\s*(.+?)(?=\s+Název\s+firmy:|\s+Typ\s+úvazku:|$)",
        text,
        re.I,
    )
    return clean(m.group(1)) if m else ""


def prace_candidate_href(href):
    low = (href or "").lower()
    if "/nabidka/" in low:
        return True
    # Prace.cz often surfaces employer microsites on *.jobs.cz directly.
    if "jobs.cz" in low and any(x in low for x in [
        "/rpd/", "/pd/", "/job/", "/jobs/", "/pozice/", "/position/"
    ]):
        return True
    return False



def prace_card_text_for_anchor(a):
    """
    Prace.cz cards are not always wrapped in <article>. Walk upwards and use
    the smallest ancestor containing the standard card metadata.
    """
    candidates = []
    node = a

    for _ in range(7):
        node = getattr(node, "parent", None)
        if node is None:
            break
        try:
            text = clean(node.get_text(" ", strip=True))
        except Exception:
            continue
        if not text:
            continue

        signals = sum(
            marker.lower() in text.lower()
            for marker in ["Lokalita:", "Název firmy:", "Typ úvazku:", "Plat:"]
        )
        if signals:
            candidates.append((len(text), -signals, text))

    if candidates:
        candidates.sort()
        return candidates[0][2]

    try:
        return clean(a.parent.get_text(" ", strip=True)) if a.parent else ""
    except Exception:
        return ""



def normalize_loc(text):
    text = clean(text).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text)


def explicit_location_text(job):
    loc = clean(job.get("location", ""))
    if loc:
        return loc

    for source_text in [
        clean(job.get("card_text", "")),
        clean(job.get("description", ""))[:2500],
    ]:
        if not source_text:
            continue
        m = re.search(
            r"(?:Lokalita|Místo pracoviště|Místo|Location)\s*:\s*(.{1,140}?)(?=\s+(?:Název firmy|Firma|Typ úvazku|Plat|Pracovní poměr|Smluvní vztah|$))",
            source_text,
            re.I,
        )
        if m:
            return clean(m.group(1))
    return ""


def is_full_remote(job):
    text = normalize_loc(
        " ".join([
            job.get("location", ""),
            job.get("card_text", ""),
            job.get("description", "")[:3500],
        ])
    )
    patterns = [
        r"\b100\s*%\s*remote\b",
        r"\bfully\s+remote\b",
        r"\bfull\s+remote\b",
        r"\bremote\s+only\b",
        r"\bprace\s+na\s+dalku\b",
        r"\bprace\s+z\s+domova\s+odkudkoliv\b",
        r"\bhome\s*office\s+odkudkoliv\b",
    ]
    return any(re.search(p, text, re.I) for p in patterns)


def location_gate(job):
    if LOCATION_MODE in {"off", "any", "all"}:
        return True, "location_gate_disabled", explicit_location_text(job)

    loc = explicit_location_text(job)
    norm_loc = normalize_loc(loc)
    allowed_norm = [normalize_loc(x) for x in ALLOWED_LOCATION_TERMS]
    blocked_norm = [normalize_loc(x) for x in BLOCKED_LOCATION_TERMS]

    if norm_loc and any(term and term in norm_loc for term in allowed_norm):
        return True, "prague_area", loc

    combined = normalize_loc(
        " ".join([
            loc,
            job.get("title", ""),
            job.get("card_text", ""),
            job.get("description", "")[:2500],
        ])
    )

    # A listing that explicitly offers Prague among multiple office locations is allowed.
    for original, term in zip(ALLOWED_LOCATION_TERMS, allowed_norm):
        if term and term in combined:
            resolved = loc or f"{original} (listing text)"
            return True, "prague_area_mentioned", resolved

    if ALLOW_FULL_REMOTE_OUTSIDE_PRAGUE and is_full_remote(job):
        return True, "full_remote", loc or "remote"

    if norm_loc and any(term and term in norm_loc for term in blocked_norm):
        return False, f"outside_prague:{loc}", loc

    for original, term in zip(BLOCKED_LOCATION_TERMS, blocked_norm):
        if term and term in combined:
            return False, "outside_prague_detected", loc or f"{original} (listing text)"

    # Unknown location must never automatically APPLY.
    return None, "location_unknown", loc


EXPANDED_DATA_SIGNAL_PATTERNS = {
    "sql": r"\bsql\b|postgres|postgresql|mssql|mysql|oracle",
    "excel": r"\bexcel\b|power\s*query|kontingen|pivot",
    "bi_reporting": (
        r"power\s*bi|tableau|business\s+intelligence|reporting|"
        r"dashboard|report(?:y|ů|u|ing)"
    ),
    "analytics": (
        r"data\s+analytics|datov.*anal[yý]z|anal[yý]za\s+dat|"
        r"statistic|statistik"
    ),
    "database_etl": (
        r"\betl\b|\bdwh\b|data\s+warehouse|datab[aá]z|database|"
        r"data\s+mart"
    ),
    "data_quality": (
        r"data\s+quality|kvalit.*dat|master\s+data|kmenov.*dat|"
        r"data\s+governance|spr[aá]va\s+dat"
    ),
    "python": r"\bpython\b|pandas",
    "data_modeling": (
        r"data\s+model|datov.*model|dimensional|star\s+schema"
    ),
}


def expanded_data_signals(text):
    low = clean(text).lower()
    found = []
    for name, pattern in EXPANDED_DATA_SIGNAL_PATTERNS.items():
        if re.search(pattern, low, re.I):
            found.append(name)
    return found


def expanded_signal_bonus(signals):
    """
    Broader titles receive score credit only from independent, concrete data
    signals in the full description. This makes a rich Data Quality role
    competitive without relaxing title thresholds for generic Operations jobs.
    """
    if not signals:
        return 0
    return min(10, max(0, (len(signals) - 2) * 3))


def expanded_role_eligible(
    title,
    text,
    evidence,
    candidate_fit,
    hard_experience,
):
    if role_class(title) != "expanded":
        return False, []

    signals = expanded_data_signals(text)

    if evidence != "strong":
        return False, signals
    if hard_experience:
        return False, signals
    if candidate_fit < EXPANDED_MIN_CANDIDATE_FIT:
        return False, signals
    if len(signals) < EXPANDED_MIN_DATA_SIGNALS:
        return False, signals

    central = {
        "sql",
        "bi_reporting",
        "analytics",
        "database_etl",
        "python",
        "data_modeling",
    }
    if not central.intersection(signals):
        return False, signals

    norm_title = normalize_key_text(title)
    if (
        "operations analyst" in norm_title
        or "operational analyst" in norm_title
        or "crm analyst" in norm_title
        or "crm data analyst" in norm_title
    ):
        if len(signals) < EXPANDED_MIN_DATA_SIGNALS + 1:
            return False, signals

    return True, signals

def discovery_priority(job):
    """
    Cheap title/card ranking before we spend requests enriching detail pages.
    Exact junior/trainee data roles should beat unrelated results that happen
    to appear earlier on broad Prace.cz category pages.
    """
    title = clean(job.get("actual_title") or job.get("title", ""))
    card = clean(job.get("card_text", ""))
    text = f"{title} {card}".lower()

    rc = role_class(title)
    score = {
        "target": 100,
        "expanded": 60,
        "adjacent": 25,
        "other": -20,
        "excluded": -200,
    }.get(rc, -20)

    if re.search(
        r"\bjunior\b|\btrainee\b|\bintern(?:ship)?\b|\babsolvent\b|\bstáž\b|\bstudent",
        title,
        re.I,
    ):
        score += 45

    if re.search(
        r"power\s*bi|reporting|business\s*intelligence|sql|"
        r"data\s+analytics|datov|data\s+quality|master\s+data|"
        r"data\s+governance|dashboard",
        text,
        re.I,
    ):
        score += 15

    if re.search(
        r"praha|prague|stodůlky|stodulky|říčany|ricany",
        text,
        re.I,
    ):
        score += 30

    if re.search(
        r"\bbrno\b|\bostrava\b|\bolomouc\b|\bplzeň\b|\bplzen\b|"
        r"\bzlín\b|\bzlin\b|\bliberec\b|\bpardubice\b",
        text,
        re.I,
    ):
        score -= 80

    if re.search(
        r"\bcad\b|security|bezpečnost|\bjava\b|android|"
        r"\bdeveloper\b|\barchitect\b|\bsales\b|obchodník|účetní|accountant",
        title,
        re.I,
    ):
        score -= 35

    return score

def parse_prace_search(html, query):
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    seen = set()

    # Prefer card headings, then fall back to all relevant job links.
    anchors = list(soup.select("article h2 a[href], article h3 a[href]"))
    if not anchors:
        anchors = [
            a for a in soup.select("a[href]")
            if prace_candidate_href(a.get("href", ""))
        ]

    for a in anchors:
        raw_href = a.get("href", "")
        href = urljoin(PRACE_BASE, raw_href)
        if not prace_candidate_href(href):
            continue

        title = clean(a.get_text(" ", strip=True))
        if not title:
            continue

        jid = source_job_id(href)
        signature = f"{jid}|{normalize_key_text(title)}"
        if signature in seen:
            continue
        seen.add(signature)

        card = prace_card_text_for_anchor(a)
        company = parse_prace_card_company(card)
        location = parse_prace_card_location(card)

        jobs.append({
            "source": "prace.cz",
            "job_id": jid,
            "title": title,
            "actual_title": title,
            "url": href,
            "company": company,
            "location": location,
            "description": "",
            "card_text": card,
            "search_query": query,
        })

    return jobs


def extract_prace_company_from_text(text):
    text = clean(text)

    # Native Prace detail pages expose "Firma: <company> (zaměstnavatel)".
    m = re.search(
        r"Firma:\s*(.+?)(?:\s*\(zaměstnavatel\)|\s+Místo\s+pracoviště:)",
        text,
        re.I,
    )
    if m:
        name = clean(m.group(1))
        if valid_company(name, "search_card"):
            return name

    # Contact section often repeats company after the recruiter's name.
    m = re.search(
        r"Kontaktní\s+údaje\s+.+?\s+([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ0-9][^+]{2,120}?(?:s\.r\.o\.|a\.s\.|s\.p\.|spol\.\s*s\s*r\.o\.))",
        text,
        re.I,
    )
    if m:
        name = clean(m.group(1))
        if valid_company(name, "search_card"):
            return name

    return ""


def extract_prace_location_from_text(text):
    text = clean(text)
    m = re.search(
        r"Místo\s+pracoviště:\s*(.+?)(?=\s+Pracovní\s+poměr:|\s+Smluvní\s+vztah:|$)",
        text,
        re.I,
    )
    return clean(m.group(1)) if m else ""

def job_id_from_url(url):
    m = re.search(r"/(?:rpd|pd)/(\d+)", url or "", re.I)
    return m.group(1) if m else None

def title_excluded(title):
    low = clean(title).lower()
    return any(re.search(p, low, re.I) for p in EXCLUDED_TITLE_PATTERNS)

def role_class(title):
    low = clean(title).lower()
    if title_excluded(title):
        return "excluded"
    if any(re.search(p, low, re.I) for p in TARGET_TITLE_PATTERNS):
        return "target"
    if any(re.search(p, low, re.I) for p in EXPANDED_TITLE_PATTERNS):
        return "expanded"
    if any(re.search(p, low, re.I) for p in ADJACENT_TITLE_PATTERNS):
        return "adjacent"
    return "other"

def valid_company(name, source="generic"):
    if not name:
        return False
    name = clean(name)
    low = name.lower()
    if len(low) > 140 or len(low) < 2:
        return False

    bad = [
        "pracovní nabídka", "volná místa", "o nás",
        "podívejte se na profil firmy", "company profile",
        "kontakt", "contact person", "recruiter", "náborář",
        "číst více", "zobrazit více", "více informací", "detail",
        "profil firmy", "learn more", "read more", "show more",
    ]
    if any(x in low for x in bad):
        return False

    # Corporate/legal suffixes and brand-like names are safe even when short.
    corp_markers = [
        "s.r.o", "s. r. o", "a.s", "a. s", "spol.", "group", "bank",
        "services", "solutions", "consulting", "republic", "česká republika",
        "czech republic", "cz", "se", "gmbh", "ag", "llc", "ltd",
    ]
    if any(x in low for x in corp_markers):
        return True

    # From generic DOM selectors, reject a likely Czech/European personal name
    # such as "Tereza Vytlačilová". Structured hiringOrganization is trusted.
    if source not in {"structured", "url_slug", "search_card"}:
        words = name.split()
        if 2 <= len(words) <= 4:
            alpha_words = [w for w in words if re.fullmatch(r"[A-Za-zÀ-ž'’.-]+", w)]
            title_words = [w for w in alpha_words if w[:1].isupper()]
            if len(alpha_words) == len(words) and len(title_words) == len(words):
                return False

    return True

def extract_company(soup):
    for script in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            org = item.get("hiringOrganization")
            if isinstance(org, dict):
                name = clean(str(org.get("name", "")))
                if valid_company(name, "structured"):
                    return name
            elif isinstance(org, list):
                for o in org:
                    if isinstance(o, dict):
                        name = clean(str(o.get("name", "")))
                        if valid_company(name, "structured"):
                            return name
    for sel in [
        "[itemprop='hiringOrganization']",
        "[data-testid*='company']",
        "[class*='company']",
        "[class*='Company']",
        "[class*='employer']",
    ]:
        for el in soup.select(sel):
            name = clean(el.get_text(" ", strip=True))
            if valid_company(name):
                return name
    return ""

def parse_search(html, query):
    soup = BeautifulSoup(html, "html.parser")
    jobs, seen = [], set()
    for a in soup.select("article h2 a[href]"):
        href = urljoin(BASE, a.get("href", ""))
        jid = job_id_from_url(href)
        title = clean(a.get_text(" ", strip=True))
        if not jid or not title or jid in seen:
            continue
        seen.add(jid)
        article = a.find_parent("article")
        jobs.append({
            "job_id": jid,
            "title": title,
            "actual_title": title,
            "url": href,
            "company": "",
            "description": "",
            "card_text": clean(article.get_text(" ", strip=True) if article else ""),
            "search_query": query,
        })
    return jobs

def enrich_job(job, session):
    try:
        r = session.get(job["url"], timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        structured = jsonld_jobposting(soup)

        h1 = soup.find("h1")
        if h1:
            job["actual_title"] = clean(h1.get_text(" ", strip=True))

        if structured:
            if structured.get("title") and not job.get("actual_title"):
                job["actual_title"] = clean(str(structured.get("title")))

            org = structured.get("hiringOrganization")
            if isinstance(org, dict) and org.get("name") and not job.get("company"):
                job["company"] = clean(str(org.get("name")))

            structured_loc = jsonld_location(structured)
            if structured_loc and not job.get("location"):
                job["location"] = structured_loc

        job["company"] = job.get("company") or extract_company(soup)
        body_main = soup.find("main") or soup.body
        visible_description = clean(
            body_main.get_text(" ", strip=True) if body_main else ""
        )

        structured_description = ""
        if structured and structured.get("description"):
            structured_description = clean(
                BeautifulSoup(
                    str(structured.get("description")),
                    "html.parser",
                ).get_text(" ", strip=True)
            )

        # Structured JobPosting is often much better on *.jobs.cz microsites.
        job["description"] = (
            structured_description
            if len(structured_description) > len(visible_description)
            else visible_description
        )

        if job.get("source") == "prace.cz":
            if not job.get("company"):
                job["company"] = extract_prace_company_from_text(job["description"])
            if not job.get("location"):
                job["location"] = extract_prace_location_from_text(job["description"])
    except Exception as exc:
        job["enrich_error"] = str(exc)
    n = len(job.get("description", ""))
    job["evidence_quality"] = "strong" if n >= 1500 else "medium" if n >= 500 else "weak"
    job["evidence_source"] = job.get("evidence_source") or "http"
    job["evidence_length"] = n
    job["role_class"] = role_class(job.get("actual_title") or job["title"])
    return job

def skill_required(text, skill):
    t = (text or "").lower()
    s = re.escape(skill.lower())
    patterns = [
        rf"(required|must have|must|požadujeme|požadavky|expect|we need|experience|proficiency|znalost|vyžad).{{0,350}}\b{s}\b",
        rf"\b{s}\b.{{0,350}}(required|must have|must|požadujeme|požadavky|expect|we need|experience|proficiency|znalost|vyžad)",
    ]
    return any(re.search(p, t, re.I) for p in patterns)

def experience_penalties(text):
    patterns = [
        (r"\bminimum\s+3\s+years\b", -25),
        (r"\bat\s+least\s+3\s+years\b", -25),
        (r"\b3\s*\+\s*years\b", -25),
        (r"\b4\s*\+\s*years\b", -30),
        (r"\b5\s*\+\s*years\b", -35),
        (r"\b[3-9]\s+years\s+(?:of\s+)?experience\b", -25),
        (r"\bminimálně\s+3\s+roky\b", -25),
        (r"\balespoň\s+3\s+roky\b", -25),
        (r"\b3\s*\+\s*roky\b", -25),
        (r"\b[3-9]\s+let\s+praxe\b", -25),
        (r"\b[3-9]\s+roky\s+praxe\b", -25),
    ]
    return [(pts, pat) for pat, pts in patterns if re.search(pat, text or "", re.I)]



def soft_experience_penalty(text):
    patterns = [
        (r"\bminimum\s+2\s+years\b", -5),
        (r"\bat\s+least\s+2\s+years\b", -5),
        (r"\b2\s*\+\s*years\b", -5),
        (r"\b2\s+years\s+(?:of\s+)?experience\b", -5),
        (r"\bminimálně\s+2\s+roky\b", -5),
        (r"\balespoň\s+2\s+roky\b", -5),
        (r"\b2\s*\+\s*roky\b", -5),
        (r"\b2\s+roky\s+praxe\b", -5),
        (r"\b2\s+let\s+praxe\b", -5),
        (r"\b1[-–]\s*2\s+years\b", -2),
        (r"\b1[-–]\s*2\s+roky\b", -2),
    ]
    for pat, points in patterns:
        if re.search(pat, text or "", re.I):
            return points
    return 0


def verified_target_apply_eligible(
    rc,
    evidence,
    hard_experience,
    entry_signal,
    score,
    candidate_fit,
):
    """
    Conservative near-threshold promotion:
    - target role only
    - strong evidence only
    - no hard 3+ years conflict
    - not needed for explicit entry roles (they have their own threshold)
    - candidate must have a real skills match
    - score must be at least VERIFIED_TARGET_APPLY_SCORE
    """
    return (
        rc == "target"
        and evidence == "strong"
        and not hard_experience
        and not entry_signal
        and candidate_fit >= VERIFIED_TARGET_MIN_CANDIDATE_FIT
        and score >= VERIFIED_TARGET_APPLY_SCORE
    )

def is_entry_role(title):
    return bool(re.search(
        r"\bjunior\b|\bentry[- ]level\b|\bgraduate\b|\btrainee\b|"
        r"\bintern(?:ship)?\b|\babsolvent\b|\bstáž\b|\bstaz\b|"
        r"\bstudent\b|\bzačínaj|\bzacinaj",
        title or "",
        re.I,
    ))


SKILL_ALIASES = {
    "sql": ["sql"],
    "postgresql": ["postgresql", "postgres"],
    "statistical analysis": [
        "statistical analysis",
        "statistická analýza",
        "statisticka analyza",
        "statistické analýzy",
        "statisticke analyzy",
        "statistika",
    ],
    "spss": ["spss"],
    "excel": ["excel", "ms excel", "microsoft excel"],
    "data visualization": [
        "data visualization",
        "data visualisation",
        "vizualizace dat",
        "datová vizualizace",
        "datova vizualizace",
    ],
    "research": [
        "research",
        "výzkum",
        "vyzkum",
        "výzkumn",
        "vyzkumn",
        "research methodology",
        "metodologie výzkumu",
        "metodologie vyzkumu",
    ],
    "python": ["python"],
    "power bi": ["power bi", "powerbi"],
    "tableau": ["tableau"],
    "snowflake": ["snowflake"],
    "pandas": ["pandas"],
    "r": [" r ", "jazyk r", "programovací jazyk r", "programovaci jazyk r"],
}


def skill_present(text, skill):
    low = f" {clean(text).lower()} "
    for alias in SKILL_ALIASES.get(skill, [skill]):
        a = alias.lower()
        if a.strip() == "r":
            if re.search(r"\br\b", low):
                return True
        elif a in low:
            return True
    return False


def mixed_role_penalty(title):
    """
    Avoid allowing a partially-data title to win just because it contains
    'junior'. Example: PPC specialista / Datový analytik (junior).
    """
    t = clean(title).lower()
    penalty = 0
    if re.search(r"\bppc\b|\bmarketing\b|\bseo\b|\bcrm\b", t):
        penalty -= 8
    if re.search(r"\bdeveloper\b|\bengineer\b", t) and re.search(r"\banalyt", t):
        penalty -= 4
    return penalty


def jsonld_jobposting(soup):
    """
    Pull structured JobPosting content from employer microsites when normal
    page text is sparse/dynamic.
    """
    found = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        queue = data if isinstance(data, list) else [data]
        while queue:
            item = queue.pop(0)
            if isinstance(item, list):
                queue.extend(item)
                continue
            if not isinstance(item, dict):
                continue

            graph = item.get("@graph")
            if isinstance(graph, list):
                queue.extend(graph)

            typ = item.get("@type")
            types = typ if isinstance(typ, list) else [typ]
            if any(str(x).lower() == "jobposting" for x in types if x):
                found.append(item)

    return found[0] if found else None


def jsonld_location(jobposting):
    loc = jobposting.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if not isinstance(loc, dict):
        return ""

    address = loc.get("address", {})
    if not isinstance(address, dict):
        return ""

    parts = [
        address.get("addressLocality"),
        address.get("addressRegion"),
    ]
    return clean(", ".join(str(x) for x in parts if x))

def score_job(job):
    title = clean(job.get("actual_title") or job.get("title", ""))
    text = clean(" ".join([
        title,
        job.get("description", ""),
        job.get("card_text", ""),
    ])).lower()

    rc = role_class(title)
    evidence = job.get("evidence_quality", "weak")

    if rc == "excluded":
        return {
            "score": 0, "decision": "SKIP", "role_fit": 0,
            "candidate_fit": 0, "experience_fit": 0,
            "language_fit": 0, "location_fit": 0,
            "confidence": "high", "reasons": ["excluded seniority"],
        }

    role_fit = (
        40 if rc == "target"
        else 34 if rc == "expanded"
        else 12 if rc == "adjacent"
        else 0
    )

    entry_signal = is_entry_role(title)
    if rc == "target" and entry_signal:
        role_fit = min(45, role_fit + 3)

    role_fit = max(0, role_fit + mixed_role_penalty(title))

    level_points = {"strong": 6, "working": 4, "basic": 2}
    matched = []
    candidate_fit = 0
    for skill, level in CANDIDATE["skills"].items():
        if level and skill_present(text, skill):
            matched.append(skill)
            candidate_fit += level_points[level]

    marker = re.search(
        r"(requirements|required|must have|what we expect|požadujeme|požadavky|your profile)(.{0,2200})",
        text, re.I
    )
    requirement_zone = marker.group(2) if marker else text

    gaps = []
    for skill in ["python", "power bi", "tableau", "snowflake", "pandas", "r"]:
        level = CANDIDATE["skills"].get(skill)
        if skill_required(requirement_zone, skill):
            if level is None:
                gaps.append(skill)
            elif level == "basic":
                gaps.append(f"{skill} (basic)")

    candidate_fit = max(0, min(35, candidate_fit - min(8, len(gaps) * 2)))

    experience_fit = 13
    hard_experience = False
    for pts, _ in experience_penalties(text):
        experience_fit += pts
        hard_experience = True

    soft_exp_penalty = soft_experience_penalty(text)
    experience_fit += soft_exp_penalty

    if entry_signal:
        experience_fit += 2
    experience_fit = max(0, min(15, experience_fit))

    language_fit = 2
    if "english" in text:
        language_fit += 1
    if "czech" in text or "češt" in text:
        language_fit += 1
    language_fit = min(5, language_fit)

    location_fit = 2
    if "prague" in text or "praha" in text:
        location_fit += 2
    if "hybrid" in text or "remote" in text:
        location_fit += 1
    location_fit = min(5, location_fit)

    pre_expanded_signals = (
        expanded_data_signals(text)
        if rc == "expanded"
        else []
    )
    expanded_bonus = (
        expanded_signal_bonus(pre_expanded_signals)
        if rc == "expanded"
        else 0
    )

    score = max(
        0,
        min(
            100,
            role_fit
            + candidate_fit
            + experience_fit
            + language_fit
            + location_fit
            + expanded_bonus,
        ),
    )

    expanded_eligible, expanded_signals = expanded_role_eligible(
        title=title,
        text=text,
        evidence=evidence,
        candidate_fit=candidate_fit,
        hard_experience=hard_experience,
    )

    # Safety policy: weak evidence can be REVIEW but never APPLY.
    confidence = {"strong": "high", "medium": "medium", "weak": "low"}[evidence]

    verified_target_promotion = verified_target_apply_eligible(
        rc=rc,
        evidence=evidence,
        hard_experience=hard_experience,
        entry_signal=entry_signal,
        score=score,
        candidate_fit=candidate_fit,
    )

    if (
        rc == "target"
        and not hard_experience
        and evidence == "strong"
        and (
            score >= MIN_APPLY_SCORE
            or (entry_signal and score >= ENTRY_APPLY_SCORE)
            or verified_target_promotion
        )
    ):
        decision = "APPLY"

    elif (
        rc == "expanded"
        and expanded_eligible
        and score >= EXPANDED_APPLY_SCORE
    ):
        decision = "APPLY"

    elif (
        rc == "target"
        and not hard_experience
        and score >= MIN_REVIEW_SCORE
    ):
        decision = "REVIEW"

    elif (
        rc == "expanded"
        and not hard_experience
        and evidence == "strong"
        and len(expanded_signals) >= 2
        and score >= EXPANDED_REVIEW_SCORE
    ):
        decision = "REVIEW"

    else:
        decision = "SKIP"

    reasons = [
        f"role_fit={role_fit}",
        f"candidate_fit={candidate_fit}",
        f"experience_fit={experience_fit}",
        f"language_fit={language_fit}",
        f"location_fit={location_fit}",
        f"evidence={evidence}",
        f"confidence={confidence}",
        f"entry_role={entry_signal}",
        f"soft_experience_penalty={soft_exp_penalty}",
        f"verified_target_promotion={verified_target_promotion}",
        f"expanded_role_eligible={expanded_eligible}",
        f"expanded_signal_bonus={expanded_bonus}",
        f"expanded_signals={','.join(expanded_signals) if expanded_signals else '-'}",
    ]
    if matched:
        reasons.append("matched=" + ", ".join(matched))
    if gaps:
        reasons.append("gaps=" + ", ".join(gaps))
    if hard_experience:
        reasons.append("3+ years experience risk")
    if evidence != "strong":
        reasons.append("weak/medium evidence blocks APPLY")

    return {
        "score": int(score),
        "decision": decision,
        "role_fit": role_fit,
        "candidate_fit": candidate_fit,
        "experience_fit": experience_fit,
        "language_fit": language_fit,
        "location_fit": location_fit,
        "confidence": confidence,
        "matched": matched,
        "gaps": gaps,
        "hard_experience": hard_experience,
        "soft_experience_penalty": soft_exp_penalty,
        "verified_target_promotion": verified_target_promotion,
        "expanded_role_eligible": expanded_eligible,
        "expanded_signal_bonus": expanded_bonus,
        "expanded_signals": expanded_signals,
        "reasons": reasons,
    }

def load_processed():
    p = APPLICATIONS_FILE
    if not p.exists():
        return set()

    terminal_statuses = {
        "SUBMITTED",
        "SUBMITTED_MANUALLY",
        "APPLICATION_CONFIRMED",
    }

    out = set()
    with p.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            jid = row.get("job_id", "")
            if not jid or row.get("status") not in terminal_statuses:
                continue

            canonical = canonicalize_saved_history_id(jid)
            if canonical:
                out.add(canonical)
    return out

def load_job_overrides():
    if not OVERRIDES_FILE.exists():
        return {}
    try:
        payload = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def manual_review_apply_eligible(job, loc_allowed):
    try:
        score = int(job.get("score", 0))
    except Exception:
        score = 0

    return (
        str(job.get("decision", "")).upper() == "REVIEW"
        and score >= MANUAL_REVIEW_APPLY_MIN_SCORE
        and str(job.get("role_class", "")).lower() in {"target", "expanded"}
        and str(job.get("evidence_quality", "")).lower() == "strong"
        and not bool(job.get("hard_experience"))
        and loc_allowed is True
    )


def save_status(job, status, score, reason):
    p = APPLICATIONS_FILE
    exists = p.exists()
    fields = [
        "job_id", "title", "company", "url", "score",
        "role_class", "decision", "status", "reason"
    ]
    canonical_id = canonical_history_key(job)
    with p.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        w.writerow({
            "job_id": canonical_id,
            "title": job.get("actual_title") or job.get("title", ""),
            "company": job.get("company", ""),
            "url": job.get("url", ""),
            "score": score,
            "role_class": job.get("role_class", ""),
            "decision": job.get("decision", ""),
            "status": status,
            "reason": reason,
        })

    # Rich local snapshot for Desktop Dashboard. This file stays on the user's
    # Mac and is not uploaded to the public release repository.
    snapshot = {
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "job_id": canonical_id,
        "title": job.get("actual_title") or job.get("title", ""),
        "company": job.get("company", ""),
        "url": job.get("url", ""),
        "source": job.get("source", ""),
        "location": job.get("location", ""),
        "score": score,
        "role_class": job.get("role_class", ""),
        "decision": job.get("decision", ""),
        "status": status,
        "reason": reason,
        "description": job.get("description", ""),
        "reasons": job.get("reasons", []),
    }
    try:
        if AUTO_CZECH_COVER_LETTER and snapshot["decision"] in {"APPLY", "REVIEW"}:
            snapshot["cover_letter"] = generate_czech_cover_letter(job)
        else:
            snapshot["cover_letter"] = ""
    except Exception:
        snapshot["cover_letter"] = ""

    try:
        with VACANCIES_FILE.open("a", encoding="utf-8") as vf:
            vf.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    except Exception:
        pass

def discover_jobs_cz(session):
    if not SOURCE_JOBS_CZ:
        return []

    jobs, seen = [], set()

    for query in SEARCH_QUERIES:
        url = f"{BASE}/prace/praha/?q%5B%5D={quote(query)}"
        try:
            r = session.get(
                url,
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            r.raise_for_status()

            for job in parse_search(r.text, query):
                job["source"] = "jobs.cz"
                key = history_key(job)
                if key in seen:
                    continue
                seen.add(key)
                jobs.append(job)

        except Exception as exc:
            print(f"⚠️ Jobs.cz search failed for '{query}': {exc}")

    jobs.sort(key=discovery_priority, reverse=True)
    return jobs[:MAX_DISCOVERY_PER_SOURCE]


def discover_prace_cz(session):
    if not SOURCE_PRACE_CZ:
        return []

    jobs, seen = [], set()

    for query, route in PRACE_SEARCH_ROUTES:
        url = urljoin(PRACE_BASE, route)

        try:
            r = session.get(
                url,
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            r.raise_for_status()

            for job in parse_prace_search(r.text, query):
                key = history_key(job)
                if key in seen:
                    continue
                seen.add(key)
                jobs.append(job)

        except Exception as exc:
            print(f"⚠️ Prace.cz search failed for '{query}': {exc}")

    # Important: truncate only AFTER relevance/junior prioritization.
    jobs.sort(key=discovery_priority, reverse=True)
    return jobs[:MAX_DISCOVERY_PER_SOURCE]

def interleave_sources(a, b):
    out = []
    max_len = max(len(a), len(b)) if (a or b) else 0
    for i in range(max_len):
        if i < len(a):
            out.append(a[i])
        if i < len(b):
            out.append(b[i])
    return out


def discover_all(session):
    jobs_cz = discover_jobs_cz(session)
    prace_cz = discover_prace_cz(session)

    print(f"🔎 Jobs.cz discovery: {len(jobs_cz)} candidate(s)")
    print(f"🔎 Prace.cz discovery: {len(prace_cz)} candidate(s)")

    merged = interleave_sources(jobs_cz, prace_cz)

    # Exact source/url duplicate guard. Semantic company/title dedupe happens
    # after enrichment in main().
    out, seen = [], set()
    for job in merged:
        exact = history_key(job)
        if exact in seen:
            continue
        seen.add(exact)
        out.append(job)

    return out

def is_login_url(url):
    low = (url or "").lower()
    return any(x in low for x in ["/prihlasit-se", "/prihlaseni", "/prihlasit", "/login", "/signin"])


def company_from_fp_url(url):
    """Conservative employer fallback from Jobs.cz /fp/<company-slug-id>/<job-id>/ URL."""
    m = re.search(r"/fp/([^/?#]+)/\d+", url or "", re.I)
    if not m:
        return ""
    slug = m.group(1)
    # Remove trailing numeric company id.
    slug = re.sub(r"-\d+$", "", slug)
    if not slug:
        return ""
    name = slug.replace("-", " ")
    # Light humanization only; do not invent Czech diacritics or punctuation.
    special = {
        "s r o": "s.r.o.",
        "a s": "a.s.",
    }
    low = name.lower()
    for old, new in special.items():
        if low.endswith(old):
            name = name[: len(name) - len(old)].rstrip() + " " + new
            break
    name = " ".join(w if w.lower() in {"s.r.o.", "a.s."} else w.capitalize() for w in name.split())
    return clean(name)


def legacy_browser_profiles():
    """Allow v29 to reuse authenticated browser profiles from earlier versions."""
    cwd = Path.cwd()
    return [
        cwd / "../../job_agent_v32/job_agent_v32/browser_profile",
        cwd / "../job_agent_v32/browser_profile",
        cwd / "../../job_agent_v31/job_agent_v31/browser_profile",
        cwd / "../job_agent_v31/browser_profile",
        cwd / "../../job_agent_v30/job_agent_v30/browser_profile",
        cwd / "../job_agent_v30/browser_profile",
        cwd / "../../job_agent_v29/job_agent_v29/browser_profile",
        cwd / "../job_agent_v29/browser_profile",
cwd / "../../job_agent_v28/job_agent_v28/browser_profile",
        cwd / "../job_agent_v28/browser_profile",
        cwd / "../../job_agent_v27/job_agent_v27/browser_profile",
        cwd / "../job_agent_v27/browser_profile",
        cwd / "../../job_agent_v26/job_agent_v26/browser_profile",
    ]


def resolve_browser_profile_dir():
    configured = Path(BROWSER_PROFILE_DIR).expanduser()
    if configured.exists():
        return configured
    for candidate in legacy_browser_profiles():
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        if resolved.exists():
            print(f"♻️ Reusing authenticated browser profile: {resolved}")
            return resolved
    configured.mkdir(parents=True, exist_ok=True)
    return configured


async def page_contexts(page):
    # page.frames already includes the main frame and any application iframe.
    return list(page.frames)


async def extract_company_from_page(page):
    # 1. Structured JobPosting data is the best source.
    try:
        company = await page.evaluate("""
        () => {
          const scripts = [...document.querySelectorAll('script[type="application/ld+json"]')];
          for (const s of scripts) {
            try {
              const data = JSON.parse(s.textContent || '');
              const stack = Array.isArray(data) ? [...data] : [data];
              while (stack.length) {
                const item = stack.shift();
                if (!item || typeof item !== 'object') continue;
                if (Array.isArray(item['@graph'])) stack.push(...item['@graph']);
                const org = item.hiringOrganization;
                if (org && typeof org === 'object' && !Array.isArray(org) && org.name) {
                  return String(org.name).trim();
                }
                if (Array.isArray(org)) {
                  for (const x of org) {
                    if (x && typeof x === 'object' && x.name) {
                      return String(x.name).trim();
                    }
                  }
                }
              }
            } catch (e) {}
          }
          return '';
        }
        """)
        if company and valid_company(company, "structured"):
            return clean(company), "browser_structured_data"
    except Exception:
        pass

    # 2. The authenticated Jobs.cz route often contains the employer slug:
    #    /fp/<employer-slug-id>/<job-id>/
    # Prefer this over broad DOM links, which may contain "Číst více".
    fp_name = company_from_fp_url(page.url)
    if fp_name and valid_company(fp_name, "url_slug"):
        return fp_name, "fp_url_slug"

    # 3. Try metadata/title. We only accept candidates that look company-like.
    meta_candidates = []
    try:
        for sel in [
            'meta[property="og:title"]',
            'meta[name="twitter:title"]',
            'meta[name="description"]',
        ]:
            loc = page.locator(sel).first
            if await loc.count():
                value = clean(await loc.get_attribute("content") or "")
                if value:
                    meta_candidates.append(value)
    except Exception:
        pass

    try:
        title = clean(await page.title())
        if title:
            meta_candidates.append(title)
    except Exception:
        pass

    # Extract plausible company segment after separators.
    for raw in meta_candidates:
        parts = [clean(x) for x in re.split(r"\s+[|–—-]\s+", raw) if clean(x)]
        for cand in reversed(parts):
            if valid_company(cand, "meta"):
                low = cand.lower()
                if any(mark in low for mark in [
                    "s.r.o", "a.s", "group", "bank", "services",
                    "solutions", "consulting", "česká republika",
                    "czech republic", "gmbh", "llc", "ltd",
                ]):
                    return cand, "browser_meta"

    # 4. Employer links. Reject generic labels and personal names.
    try:
        h1_text = clean(await page.locator("h1").first.inner_text())
    except Exception:
        h1_text = ""

    employer_selectors = [
        'a[href*="/fp/"]',
        'a[href*="/firma/"]',
        'a[href*="/zamestnavatel/"]',
        '[itemprop="hiringOrganization"] a',
        '[itemprop="hiringOrganization"]',
        '[data-testid*="employer"]',
        '[data-test*="employer"]',
    ]
    for frame in await page_contexts(page):
        for sel in employer_selectors:
            try:
                loc = frame.locator(sel)
                for i in range(min(await loc.count(), 20)):
                    el = loc.nth(i)
                    txt = clean(await el.inner_text())
                    if not valid_company(txt, "employer_link"):
                        continue
                    if h1_text and (txt.lower() == h1_text.lower() or h1_text.lower() in txt.lower()):
                        continue
                    href = (await el.get_attribute("href") or "")
                    # If the href itself is /fp/, its slug is safer than link text.
                    href_name = company_from_fp_url(urljoin(page.url, href))
                    if href_name and valid_company(href_name, "url_slug"):
                        return href_name, "employer_href_slug"
                    return txt, "browser_employer_link"
            except Exception:
                pass

    return "", "not_detected"


async def looks_like_application_form(page):
    signals = 0
    for frame in await page_contexts(page):
        for sel in [
            'input[type="email"]',
            'input[type="tel"]',
            'input[type="file"]',
            'button[type="submit"]',
            'input[type="submit"]',
        ]:
            try:
                if await frame.locator(sel).count():
                    signals += 1
            except Exception:
                pass
    return signals >= 2



def should_browser_recover_evidence(job):
    """
    Only spend a browser render on promising target vacancies whose HTTP
    evidence is incomplete.
    """
    if not BROWSER_EVIDENCE_RECOVERY:
        return False

    if job.get("role_class") not in {"target", "expanded"}:
        return False

    evidence = (job.get("evidence_quality") or "weak").lower()
    if evidence not in BROWSER_EVIDENCE_LEVELS:
        return False

    # Explicit excluded/senior title is never worth rendering.
    title = job.get("actual_title") or job.get("title", "")
    if role_class(title) in {"excluded", "other", "adjacent"}:
        return False

    return True


def evidence_quality_for_text(text):
    n = len(clean(text))
    if n >= 1500:
        return "strong"
    if n >= 500:
        return "medium"
    return "weak"


def merge_browser_evidence(
    job,
    rendered_html,
    rendered_text,
    current_url="",
    browser_company="",
    browser_company_source="",
):
    """
    Pure merge step used by the Playwright evidence pass and by smoke tests.
    It never changes application state or clicks anything.
    """
    before_len = len(job.get("description", ""))
    before_quality = job.get("evidence_quality", "weak")

    soup = BeautifulSoup(rendered_html or "", "html.parser")
    structured = jsonld_jobposting(soup)

    # Rendered title.
    h1 = soup.find("h1")
    if h1:
        rendered_title = clean(h1.get_text(" ", strip=True))
        if rendered_title:
            job["actual_title"] = rendered_title
    elif structured and structured.get("title"):
        rendered_title = clean(str(structured.get("title")))
        if rendered_title:
            job["actual_title"] = rendered_title

    # Rendered/structured company.
    if browser_company:
        job["company"] = browser_company
        job["company_source"] = browser_company_source or "browser_render"
    elif structured:
        org = structured.get("hiringOrganization")
        if isinstance(org, dict) and org.get("name"):
            company = clean(str(org.get("name")))
            if company:
                job["company"] = company
                job["company_source"] = "browser_jsonld"

    # Structured location.
    if structured:
        loc = jsonld_location(structured)
        if loc:
            job["location"] = loc

    # Rendered visible text is primary. JSON-LD description can be cleaner and
    # longer on employer microsites, so compare both.
    visible = clean(rendered_text or "")
    structured_text = ""

    if structured and structured.get("description"):
        structured_text = clean(
            BeautifulSoup(
                str(structured.get("description")),
                "html.parser",
            ).get_text(" ", strip=True)
        )

    best_rendered = (
        structured_text
        if len(structured_text) > len(visible)
        else visible
    )

    # Never replace better HTTP evidence with a shorter rendered page.
    if len(best_rendered) > before_len:
        job["description"] = best_rendered

    # Prace.cz fallback extraction from the richer rendered text.
    if job.get("source") == "prace.cz":
        if not job.get("company"):
            company = extract_prace_company_from_text(
                job.get("description", "")
            )
            if company:
                job["company"] = company
                job["company_source"] = "browser_text"

        if not job.get("location"):
            loc = extract_prace_location_from_text(
                job.get("description", "")
            )
            if loc:
                job["location"] = loc

    after_len = len(job.get("description", ""))
    after_quality = evidence_quality_for_text(job.get("description", ""))

    job["evidence_quality"] = after_quality
    job["evidence_length"] = after_len
    job["role_class"] = role_class(
        job.get("actual_title") or job.get("title", "")
    )

    if after_len > before_len:
        job["evidence_source"] = "browser_render"
    else:
        job["evidence_source"] = job.get("evidence_source") or "http"

    job["browser_evidence_url"] = current_url or job.get("url", "")
    job["browser_evidence_before"] = {
        "quality": before_quality,
        "length": before_len,
    }
    job["browser_evidence_after"] = {
        "quality": after_quality,
        "length": after_len,
    }

    return job


async def browser_recover_weak_evidence(jobs):
    """
    Second-pass evidence recovery.

    Important safety property: this function only navigates/read pages.
    It does not click application CTAs, fill fields, upload files, or submit.
    """
    candidates = [
        job for job in jobs
        if should_browser_recover_evidence(job)
    ]

    candidates.sort(
        key=lambda j: (
            discovery_priority(j),
            is_entry_role(j.get("actual_title") or j.get("title", "")),
            j.get("source") == "jobs.cz",
            j.get("evidence_length", 0),
        ),
        reverse=True,
    )

    unique_candidates = []
    seen_evidence = set()
    for job in candidates:
        key = browser_evidence_key(job)
        if key in seen_evidence:
            continue
        seen_evidence.add(key)
        unique_candidates.append(job)

    candidates = unique_candidates[:MAX_BROWSER_EVIDENCE_JOBS]

    if not candidates:
        print("🧠 Browser evidence pass: 0 candidate(s)")
        return jobs

    print(
        f"🧠 Browser evidence pass: {len(candidates)} candidate(s) "
        f"(read-only JavaScript render)"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
            locale="cs-CZ",
        )
        page = await context.new_page()

        for index, job in enumerate(candidates, 1):
            title = job.get("actual_title") or job.get("title", "")
            before_quality = job.get("evidence_quality", "weak")
            before_len = len(job.get("description", ""))

            try:
                await page.goto(
                    job["url"],
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await page.wait_for_timeout(BROWSER_EVIDENCE_WAIT_MS)

                # Give client-side apps one short network-idle chance, but never
                # fail the pass if analytics/ads keep the page busy.
                try:
                    await page.wait_for_load_state(
                        "networkidle",
                        timeout=2500,
                    )
                except Exception:
                    pass

                rendered_html = await page.content()

                visible = ""
                for selector in ["main", "[role='main']", "body"]:
                    try:
                        locator = page.locator(selector).first
                        if await locator.count():
                            candidate_text = clean(
                                await locator.inner_text(timeout=2500)
                            )
                            if len(candidate_text) > len(visible):
                                visible = candidate_text
                    except Exception:
                        pass

                browser_company = ""
                browser_company_source = ""
                try:
                    browser_company, browser_company_source = (
                        await extract_company_from_page(page)
                    )
                except Exception:
                    pass

                merge_browser_evidence(
                    job,
                    rendered_html,
                    visible,
                    current_url=page.url,
                    browser_company=browser_company,
                    browser_company_source=browser_company_source,
                )

                after_quality = job.get("evidence_quality", "weak")
                after_len = len(job.get("description", ""))

                marker = "⬆️" if (
                    after_quality != before_quality
                    or after_len > before_len
                ) else "↔️"

                print(
                    f"   {marker} {index}/{len(candidates)} "
                    f"{title[:72]} | "
                    f"{before_quality}:{before_len} → "
                    f"{after_quality}:{after_len}"
                )

            except Exception as exc:
                job["browser_evidence_error"] = (
                    f"{type(exc).__name__}: {exc}"
                )
                print(
                    f"   ⚠️ {index}/{len(candidates)} {title[:72]} | "
                    f"render failed: {type(exc).__name__}"
                )

        await context.close()
        await browser.close()

    upgraded = sum(
        1 for job in candidates
        if job.get("evidence_source") == "browser_render"
    )
    strong_after = sum(
        1 for job in candidates
        if job.get("evidence_quality") == "strong"
    )

    print(
        f"🧠 Browser evidence result: "
        f"{upgraded}/{len(candidates)} enriched, "
        f"{strong_after}/{len(candidates)} now strong"
    )

    return jobs

async def collect_application_debug(page):
    data = {"url": page.url, "title": await page.title(), "frames": []}

    for frame in await page_contexts(page):
        row = {
            "url": frame.url,
            "controls": [],
            "inputs": [],
            "textareas": [],
            "selects": [],
        }

        # Buttons / links
        try:
            loc = frame.locator('a, button, [role="button"], input[type="submit"]')
            for i in range(min(await loc.count(), 160)):
                el = loc.nth(i)
                try:
                    if not await el.is_visible():
                        continue
                    row["controls"].append({
                        "tag": await el.evaluate("(e) => e.tagName"),
                        "text": clean(await el.inner_text())[:200],
                        "href": (await el.get_attribute("href") or "")[:500],
                        "aria": (await el.get_attribute("aria-label") or "")[:200],
                        "title": (await el.get_attribute("title") or "")[:200],
                        "type": (await el.get_attribute("type") or "")[:80],
                        "name": (await el.get_attribute("name") or "")[:160],
                        "id": (await el.get_attribute("id") or "")[:160],
                    })
                except Exception:
                    pass
        except Exception:
            pass

        # Inputs including hidden/file controls.
        try:
            loc = frame.locator("input")
            for i in range(min(await loc.count(), 200)):
                el = loc.nth(i)
                try:
                    labels = await el.evaluate("""
                        (e) => e.labels ? [...e.labels].map(x => x.innerText || x.textContent || '').join(' ') : ''
                    """)
                    row["inputs"].append({
                        "type": (await el.get_attribute("type") or "")[:80],
                        "name": (await el.get_attribute("name") or "")[:160],
                        "id": (await el.get_attribute("id") or "")[:160],
                        "placeholder": (await el.get_attribute("placeholder") or "")[:200],
                        "aria": (await el.get_attribute("aria-label") or "")[:200],
                        "autocomplete": (await el.get_attribute("autocomplete") or "")[:100],
                        "accept": (await el.get_attribute("accept") or "")[:200],
                        "labels": clean(labels)[:300],
                        "visible": await el.is_visible(),
                        "disabled": await el.is_disabled(),
                    })
                except Exception:
                    pass
        except Exception:
            pass

        try:
            loc = frame.locator("textarea")
            for i in range(min(await loc.count(), 80)):
                el = loc.nth(i)
                try:
                    row["textareas"].append({
                        "name": (await el.get_attribute("name") or "")[:160],
                        "id": (await el.get_attribute("id") or "")[:160],
                        "placeholder": (await el.get_attribute("placeholder") or "")[:200],
                        "aria": (await el.get_attribute("aria-label") or "")[:200],
                    })
                except Exception:
                    pass
        except Exception:
            pass

        try:
            loc = frame.locator("select")
            for i in range(min(await loc.count(), 80)):
                el = loc.nth(i)
                try:
                    row["selects"].append({
                        "name": (await el.get_attribute("name") or "")[:160],
                        "id": (await el.get_attribute("id") or "")[:160],
                        "aria": (await el.get_attribute("aria-label") or "")[:200],
                    })
                except Exception:
                    pass
        except Exception:
            pass

        data["frames"].append(row)

    if APPLICATION_DEBUG:
        Path("application_debug.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        try:
            await page.screenshot(path="application_debug.png", full_page=True)
        except Exception:
            pass

    return data



APPLICATION_CTA_TEXT_PATTERNS = [
    re.compile(r"^\s*odpovědět\s*$", re.I),
    re.compile(r"^\s*odpovědět\s+na\s+(?:tuto\s+)?(?:nabídku|pozici)\s*$", re.I),
    re.compile(r"^\s*reagovat\s*$", re.I),
    re.compile(r"^\s*reagovat\s+na\s+(?:tuto\s+)?(?:nabídku|pozici)\s*$", re.I),
    re.compile(r"^\s*mám\s+zájem\s*$", re.I),
    re.compile(r"^\s*mám\s+zájem\s+o\s+(?:tuto\s+)?(?:práci|pozici)\s*$", re.I),
    re.compile(r"^\s*tuhle\s+práci\s+chci\s*$", re.I),
    re.compile(r"^\s*tuto\s+práci\s+chci\s*$", re.I),
    re.compile(r"^\s*chci\s+tuto\s+práci\s*$", re.I),
    re.compile(r"^\s*chci\s+se\s+přihlásit\s*$", re.I),
    re.compile(r"^\s*chci\s+odpovědět\s*$", re.I),
    re.compile(r"^\s*poslat\s+odpověď\s*$", re.I),
    re.compile(r"^\s*odeslat\s+životopis\s*$", re.I),
    re.compile(r"^\s*poslat\s+životopis\s*$", re.I),
    re.compile(r"^\s*přihlásit\s+se\s*$", re.I),
    re.compile(r"^\s*přihlásit\s+se\s+na\s+(?:tuto\s+)?pozici\s*$", re.I),
    re.compile(r"^\s*apply\s*$", re.I),
    re.compile(r"^\s*apply\s+now\s*$", re.I),
    re.compile(r"^\s*apply\s+for\s+this\s+(?:job|position)\s*$", re.I),
    re.compile(r"^\s*submit\s+application\s*$", re.I),
    re.compile(r"^\s*respond\s*$", re.I),
    re.compile(r"^\s*respond\s+now\s*$", re.I),
]

APPLICATION_HREF_PATTERNS = [
    re.compile(r"/odpoved(?:/|[-_.?&#]|$)", re.I),
    re.compile(r"/odpovedni-formular(?:/|[-_.?&#]|$)", re.I),
    re.compile(r"/reakce(?:/|[-_.?&#]|$)", re.I),
    re.compile(r"/reply(?:/|[-_.?&#]|$)", re.I),
    re.compile(r"/respond(?:/|[-_.?&#]|$)", re.I),
    re.compile(r"/apply(?:/|[-_.?&#]|$)", re.I),
    re.compile(r"/application(?:/|[-_.?&#]|$)", re.I),
    re.compile(r"/candidate(?:/|[-_.?&#]|$)", re.I),
    re.compile(r"[?&](?:apply|application|reply|response|candidate)=", re.I),
]

ARTICLE_PATH_PATTERNS = [
    re.compile(r"/(?:clanek|clanky|article|articles|blog|news|novinky|press|media)/", re.I),
    re.compile(r"/nejodpovedn", re.I),
]


def exact_application_cta_text(text):
    text = clean(text or "")
    return any(p.fullmatch(text) for p in APPLICATION_CTA_TEXT_PATTERNS)


def application_href_match(href):
    href = clean(href or "")
    if not href:
        return False
    return any(p.search(href) for p in APPLICATION_HREF_PATTERNS)


def article_like_url(url):
    return any(p.search(url or "") for p in ARTICLE_PATH_PATTERNS)


def is_jobs_employer_microsite(url):
    low = (url or "").lower()
    return bool(
        re.search(r"https?://[^/]+\.jobs\.cz(?:/|$)", low)
        and "www.jobs.cz" not in low
    )


async def strong_application_form(page):
    for frame in await page_contexts(page):
        try:
            if await frame.locator('input[type="file"]').count():
                return True
        except Exception:
            pass

        try:
            email = await frame.locator(
                'input[type="email"], input[name*="email" i]'
            ).count()
            submit = await frame.locator(
                'button[type="submit"], input[type="submit"]'
            ).count()
            names = await frame.locator(
                'input[name*="first" i], input[name*="last" i], '
                'input[id*="first" i], input[id*="last" i], '
                'input[name*="jmeno" i], input[name*="prijmeni" i], '
                'input[name*="jméno" i], input[name*="příjmení" i]'
            ).count()

            if email and submit and names:
                return True

            cvish = await frame.locator(
                'input[type="file"], '
                'input[name*="cv" i], input[id*="cv" i], '
                'input[name*="resume" i], input[id*="resume" i]'
            ).count()
            phoneish = await frame.locator(
                'input[type="tel"], input[name*="telefon" i], '
                'input[id*="telefon" i], input[name*="phone" i]'
            ).count()

            if email and submit and (cvish or phoneish):
                return True
        except Exception:
            pass

    return False


async def valid_application_destination(page, origin_url):
    if not STRICT_APPLICATION_ROUTE_VALIDATION:
        return True, "strict_validation_disabled"

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass

    await page.wait_for_timeout(500)
    url = page.url or ""
    low = url.lower()

    if is_login_url(url):
        return True, "login_route"

    if "/externi-jof/" in low:
        return True, "jobs_handoff"

    if "/odpovedni-formular/" in low or "/odpoved/" in low:
        return True, "portal_application_route"

    if (
        is_jobs_employer_microsite(url)
        and "/vacancy-detail/reply-form" in low
        and await strong_application_form(page)
    ):
        return True, "jobs_microsite_reply_form"

    if is_workday_url(url) or is_pwc_careers_url(url):
        return True, "known_ats"

    if application_href_match(url) and not article_like_url(url):
        return True, "application_url_pattern"

    if await strong_application_form(page):
        return True, "strong_application_form"

    if url == origin_url and await looks_like_application_form(page):
        return True, "same_page_application_form"

    if article_like_url(url):
        return False, "article_like_destination"

    return False, "no_application_signals"


def same_host_reply_form_url(current_url, job_id=""):
    """
    Safe fallback for Alma employer microsites only.

    /vacancy-detail?r=detail&id=2001414351
      -> /vacancy-detail/reply-form?r=reply&id=2001414351

    The destination must stay on the exact same *.jobs.cz employer host and
    must reuse a numeric job ID already present in the source URL.
    """
    if not ALLOW_SAME_HOST_REPLY_FALLBACK:
        return ""
    if not is_jobs_employer_microsite(current_url):
        return ""

    try:
        parsed = urlparse(current_url)
        qs = parse_qs(parsed.query)
        jid = str(job_id or "").strip()
        if not jid:
            vals = qs.get("id", [])
            if vals:
                jid = str(vals[0]).strip()
        if not jid.isdigit():
            return ""

        path = parsed.path or "/"
        if path.endswith("/reply-form"):
            return current_url
        if "/vacancy-detail" not in path:
            return ""

        new_path = path.rstrip("/") + "/reply-form"
        new_qs = {}
        for key, vals in qs.items():
            if vals and key in {"id", "rps", "impressionId", "searchId"}:
                new_qs[key] = vals[-1]
        new_qs["r"] = "reply"
        new_qs["id"] = jid

        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            new_path,
            "",
            urlencode(new_qs),
            "",
        ))
    except Exception:
        return ""


async def microsite_wait_for_cta(page):
    """Wait for client-side employer microsite hydration."""
    if not is_jobs_employer_microsite(page.url):
        return

    for attempt in range(1, MICROSITE_CTA_RETRIES + 1):
        try:
            await page.wait_for_timeout(MICROSITE_CTA_WAIT_MS)
        except Exception:
            pass
        try:
            await page.wait_for_load_state("networkidle", timeout=2500)
        except Exception:
            pass
        try:
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(350)
            await page.evaluate("() => window.scrollTo(0, 0)")
        except Exception:
            pass

        try:
            loc = page.locator('a, button, [role="button"], input[type="submit"]')
            count = min(await loc.count(), 260)
            for i in range(count):
                el = loc.nth(i)
                try:
                    if not await el.is_visible():
                        continue
                    try:
                        txt = clean(await el.inner_text())
                    except Exception:
                        txt = clean(await el.get_attribute("value") or "")
                    href = clean(await el.get_attribute("href") or "")
                    if (
                        exact_application_cta_text(txt)
                        or application_href_match(urljoin(page.url, href) if href else href)
                    ):
                        print(
                            f"🧭 Microsite CTA became available after wait "
                            f"attempt {attempt}/{MICROSITE_CTA_RETRIES}"
                        )
                        return
                except Exception:
                    pass
        except Exception:
            pass

async def click_application_control(page):
    """
    Strict application CTA finder.

    No broad substring matching: this deliberately avoids false positives such
    as Czech words containing 'odpověd' (for example 'nejodpovědnější').
    """
    origin_url = page.url

    if is_jobs_employer_microsite(origin_url):
        await microsite_wait_for_cta(page)

    candidates = []

    for frame in await page_contexts(page):
        try:
            loc = frame.locator(
                'a, button, [role="button"], input[type="submit"]'
            )
            count = min(await loc.count(), 240)

            for i in range(count):
                el = loc.nth(i)
                try:
                    if not await el.is_visible():
                        continue

                    text = ""
                    try:
                        text = clean(await el.inner_text())
                    except Exception:
                        text = clean(await el.get_attribute("value") or "")

                    href = clean(await el.get_attribute("href") or "")
                    aria = clean(await el.get_attribute("aria-label") or "")
                    title = clean(await el.get_attribute("title") or "")
                    data_action = clean(
                        await el.get_attribute("data-action") or ""
                    )
                    data_testid = clean(
                        await el.get_attribute("data-testid") or ""
                    )
                    onclick = clean(await el.get_attribute("onclick") or "")
                    cls = clean(await el.get_attribute("class") or "")
                    eid = clean(await el.get_attribute("id") or "")

                    score = 0
                    reasons = []

                    if exact_application_cta_text(text):
                        score += 100
                        reasons.append("exact_text")

                    if exact_application_cta_text(aria):
                        score += 90
                        reasons.append("exact_aria")

                    if exact_application_cta_text(title):
                        score += 80
                        reasons.append("exact_title")

                    absolute_href = urljoin(origin_url, href) if href else ""
                    if application_href_match(absolute_href or href):
                        score += 70
                        reasons.append("application_href")

                    attrs = " ".join([
                        data_action,
                        data_testid,
                        onclick,
                        cls,
                        eid,
                    ]).lower()

                    if re.search(
                        r"(?:^|[-_\s])(apply|application|respond|reply|"
                        r"candidate|odpoved|odpověd|reaction)(?:$|[-_\s])",
                        attrs,
                        re.I,
                    ):
                        score += 40
                        reasons.append("application_attribute")

                    if (
                        is_jobs_employer_microsite(origin_url)
                        and exact_application_cta_text(text)
                    ):
                        score += 20
                        reasons.append("jobs_microsite_exact_text")

                    if absolute_href and article_like_url(absolute_href):
                        score -= 200
                        reasons.append("article_penalty")

                    if score <= 0:
                        continue

                    candidates.append({
                        "score": score,
                        "el": el,
                        "text": text,
                        "href": absolute_href or href,
                        "reason": "+".join(reasons),
                    })
                except Exception:
                    pass
        except Exception:
            pass

    if not candidates:
        if is_jobs_employer_microsite(origin_url):
            await save_stage_debug(
                page,
                "employer_microsite_cta_debug.json",
                "employer_microsite_cta_debug.png",
            )

            fallback_url = same_host_reply_form_url(origin_url)
            if fallback_url:
                print(
                    "🧭 No rendered CTA found; trying safe same-host "
                    f"reply-form fallback: {fallback_url}"
                )
                try:
                    await page.goto(
                        fallback_url,
                        wait_until="domcontentloaded",
                        timeout=20000,
                    )
                    await page.wait_for_timeout(700)
                    valid, route_reason = await valid_application_destination(
                        page, origin_url
                    )
                    if valid:
                        return page, (
                            "same_host_reply_fallback:"
                            f"{route_reason}"
                        )

                    await save_stage_debug(
                        page,
                        "reply_fallback_invalid_debug.json",
                        "reply_fallback_invalid_debug.png",
                    )
                    return None, (
                        "invalid_destination:"
                        f"same_host_reply_fallback:{route_reason}:"
                        f"{page.url}"
                    )
                except Exception as exc:
                    return None, (
                        "reply_fallback_failed:"
                        f"{type(exc).__name__}"
                    )

            return None, "not_found:employer_microsite_debug_saved"

        return None, "not_found"

    candidates.sort(key=lambda x: x["score"], reverse=True)
    candidate = candidates[0]

    print(
        "🖱️ Application CTA candidate: "
        f"text={candidate['text']!r} | "
        f"score={candidate['score']} | "
        f"reason={candidate['reason']}"
    )

    before = set(page.context.pages)

    try:
        await candidate["el"].click(timeout=8000)
    except Exception as exc:
        return None, f"cta_click_failed:{type(exc).__name__}"

    await page.wait_for_timeout(900)

    after = list(page.context.pages)
    new_pages = [p for p in after if p not in before]
    active = new_pages[-1] if new_pages else page

    if new_pages:
        try:
            await active.wait_for_load_state(
                "domcontentloaded",
                timeout=15000,
            )
        except Exception:
            pass

    valid, route_reason = await valid_application_destination(
        active,
        origin_url,
    )

    if not valid:
        await save_stage_debug(
            active,
            "invalid_application_destination_debug.json",
            "invalid_application_destination_debug.png",
        )
        print(
            f"🛡️ Rejected non-application destination: "
            f"{active.url} ({route_reason})"
        )
        return None, (
            "invalid_destination:"
            f"{route_reason}:"
            f"{active.url}"
        )

    return active, (
        f"strict_cta:{candidate['reason']}:"
        f"{route_reason}"
    )

async def bootstrap_login(page, job_url):
    if not LOGIN_BOOTSTRAP:
        return None

    print("\n🔑 LOGIN REQUIRED")
    print("   Complete the portal login in the opened Chromium window.")
    print("   The agent will detect the completed login and continue automatically.")
    print("   The persistent browser profile will be reused on future runs.")

    for _ in range(max(1, LOGIN_WAIT_SECONDS)):
        await page.wait_for_timeout(1000)
        if not is_login_url(page.url):
            # Prefer the URL selected by Jobs.cz after auth; it may be an /fp/ job page.
            await page.wait_for_timeout(1200)
            return page
    return None


async def input_metadata(el):
    """
    Rich metadata for dynamically generated ATS/microsite inputs.

    Some employer pages do not connect <label for=...> to the input, so
    e.labels is empty even though the visible label says "Jméno". We inspect
    nearby DOM text as a fallback.
    """
    try:
        labels = await el.evaluate("""
            (e) => e.labels
              ? [...e.labels]
                  .map(x => x.innerText || x.textContent || '')
                  .join(' ')
              : ''
        """)
    except Exception:
        labels = ""

    parts = []

    for attr in [
        "type",
        "name",
        "id",
        "placeholder",
        "aria-label",
        "autocomplete",
        "data-testid",
        "data-qa",
        "data-cy",
        "data-name",
        "data-field",
        "formcontrolname",
        "ng-reflect-name",
        "class",
    ]:
        try:
            value = await el.get_attribute(attr)
            if value:
                parts.append(value)
        except Exception:
            pass

    if labels:
        parts.append(labels)

    # Visible text immediately around the field.
    try:
        nearby = await el.evaluate("""
            (e) => {
              const selectors = [
                '.form-group',
                '.form-field',
                '.field',
                '.control',
                '.input-group',
                '.input-wrapper',
                '.form-item',
                '[class*="field"]',
                '[class*="control"]'
              ];

              let holder = null;
              for (const sel of selectors) {
                holder = e.closest(sel);
                if (holder) break;
              }

              if (!holder) holder = e.parentElement;

              const chunks = [];

              if (holder) {
                const label = holder.querySelector(
                  'label, .label, [class*="label"], legend'
                );
                if (label) {
                  chunks.push(label.innerText || label.textContent || '');
                }

                const text = holder.innerText || holder.textContent || '';
                if (text) chunks.push(text.slice(0, 450));
              }

              const prev = e.previousElementSibling;
              if (prev) {
                const t = prev.innerText || prev.textContent || '';
                if (t) chunks.push(t.slice(0, 220));
              }

              return chunks.join(' ');
            }
        """)
        if nearby:
            parts.append(nearby)
    except Exception:
        pass

    return clean(" ".join(parts)).lower()


async def find_semantic_input(page, keywords, negative=()):
    scored = []

    norm_keywords = [
        normalize_key_text(x) for x in keywords if normalize_key_text(x)
    ]
    norm_negative = [
        normalize_key_text(x) for x in negative if normalize_key_text(x)
    ]

    for frame in await page_contexts(page):
        try:
            loc = frame.locator("input")
            for i in range(min(await loc.count(), 260)):
                el = loc.nth(i)
                try:
                    if not await el.is_visible() or await el.is_disabled():
                        continue

                    typ = (await el.get_attribute("type") or "text").lower()
                    if typ in {
                        "hidden",
                        "file",
                        "submit",
                        "button",
                        "checkbox",
                        "radio",
                    }:
                        continue

                    raw_meta = await input_metadata(el)
                    meta = normalize_key_text(raw_meta)

                    if any(x and x in meta for x in norm_negative):
                        continue

                    score = 0
                    for keyword in norm_keywords:
                        if not keyword:
                            continue

                        if meta == keyword:
                            score += 20
                        elif re.search(
                            rf"(?:^|\s){re.escape(keyword)}(?:$|\s)",
                            meta,
                        ):
                            score += 10
                        elif keyword in meta:
                            score += 4

                    if typ == "tel":
                        score += 8
                    if "autocomplete tel" in meta or " tel " in f" {meta} ":
                        score += 5

                    if score > 0:
                        scored.append(
                            (score, frame, el, raw_meta)
                        )
                except Exception:
                    pass
        except Exception:
            pass

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0] if scored else None


def name_field_role(meta):
    """
    Return: first / last / full / unknown.

    Uses normalized Czech and English label/attribute text. This intentionally
    distinguishes `Jméno` from `Příjmení`, including disconnected labels.
    """
    norm = normalize_key_text(meta or "")
    padded = f" {norm} "

    full_patterns = [
        "full name",
        "cele jmeno",
        "jmeno a prijmeni",
        "jmeno prijmeni",
        "name surname",
        "first and last name",
    ]
    if any(x in norm for x in full_patterns):
        return "full"

    last_patterns = [
        "family name",
        "family-name",
        "last name",
        "lastname",
        "last_name",
        "surname",
        "prijmeni",
    ]
    if any(normalize_key_text(x) in norm for x in last_patterns):
        return "last"

    first_patterns = [
        "given name",
        "given-name",
        "first name",
        "firstname",
        "first_name",
        "forename",
        "krestni jmeno",
        "krestni",
        "jmeno",
    ]
    if any(normalize_key_text(x) in norm for x in first_patterns):
        return "first"

    return "unknown"


async def find_name_input(page, kind):
    scored = []

    for frame in await page_contexts(page):
        try:
            loc = frame.locator("input")
            for i in range(min(await loc.count(), 260)):
                el = loc.nth(i)
                try:
                    if not await el.is_visible() or await el.is_disabled():
                        continue

                    typ = (await el.get_attribute("type") or "text").lower()
                    if typ in {
                        "hidden",
                        "file",
                        "submit",
                        "button",
                        "checkbox",
                        "radio",
                        "email",
                        "tel",
                    }:
                        continue

                    meta = await input_metadata(el)
                    role = name_field_role(meta)

                    if role != kind:
                        continue

                    norm = normalize_key_text(meta)
                    score = 50

                    autocomplete = normalize_key_text(
                        await el.get_attribute("autocomplete") or ""
                    )

                    if kind == "first" and "given name" in autocomplete:
                        score += 50
                    if kind == "last" and "family name" in autocomplete:
                        score += 50

                    if kind == "first":
                        for cue in [
                            "first name",
                            "firstname",
                            "krestni jmeno",
                            "given name",
                        ]:
                            if normalize_key_text(cue) in norm:
                                score += 20
                        # Plain Czech "Jméno" is still a strong first-name cue
                        # when surname/full-name terms are absent.
                        if re.search(r"(?:^|\s)jmeno(?:$|\s)", norm):
                            score += 12
                    else:
                        for cue in [
                            "last name",
                            "lastname",
                            "surname",
                            "prijmeni",
                            "family name",
                        ]:
                            if normalize_key_text(cue) in norm:
                                score += 20

                    scored.append((score, frame, el, meta))
                except Exception:
                    pass
        except Exception:
            pass

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0] if scored else None



async def positional_name_fallback(page, kind, value):
    """
    Last-resort conservative fallback for employer microsites.

    It only activates when exactly two plausible plain-text inputs remain
    after excluding obvious non-name fields.
    """
    if not is_jobs_employer_microsite(page.url):
        return False, "not_microsite"

    candidates = []
    for frame in await page_contexts(page):
        try:
            loc = frame.locator("input")
            for i in range(min(await loc.count(), 260)):
                el = loc.nth(i)
                try:
                    if not await el.is_visible() or await el.is_disabled():
                        continue
                    typ = (await el.get_attribute("type") or "text").lower()
                    if typ not in {"text", ""}:
                        continue
                    meta = await input_metadata(el)
                    norm = normalize_key_text(meta)
                    if any(x in norm for x in [
                        "email", "telefon", "phone", "mobile", "search",
                        "company", "firma", "city", "mesto", "address",
                        "adresa", "zip", "psc", "linkedin",
                    ]):
                        continue
                    candidates.append((frame, el, meta))
                except Exception:
                    pass
        except Exception:
            pass

    if len(candidates) != 2:
        return False, f"ambiguous_text_inputs:{len(candidates)}"

    index = 0 if kind == "first" else 1
    _, el, meta = candidates[index]
    try:
        await el.fill(value)
        await el.press("Tab")
        actual = await el.input_value()
        ok = value.lower() in (actual or "").lower()
        return ok, f"positional_microsite:{meta}"
    except Exception as exc:
        return False, f"positional_fill_failed:{type(exc).__name__}:{meta}"

async def fill_semantic_name(page, kind, value):
    candidate = await find_name_input(page, kind)

    # Backward-compatible generic fallback.
    if candidate is None:
        if kind == "first":
            keywords = [
                "given-name",
                "first name",
                "firstname",
                "first_name",
                "jméno",
                "jmeno",
                "křestní",
                "krestni",
                "forename",
            ]
            negative = [
                "last",
                "surname",
                "family",
                "příjmen",
                "prijmen",
                "email",
                "phone",
                "telefon",
                "mobile",
            ]
        else:
            keywords = [
                "family-name",
                "last name",
                "lastname",
                "last_name",
                "surname",
                "příjmen",
                "prijmen",
            ]
            negative = [
                "first",
                "given",
                "křestní",
                "krestni",
                "email",
                "phone",
                "telefon",
                "mobile",
            ]

        candidate = await find_semantic_input(
            page,
            keywords=keywords,
            negative=negative,
        )

    if candidate is None:
        ok, source = await positional_name_fallback(
            page, kind, value
        )
        if ok:
            return True, source
        return False, source

    _, _, el, meta = candidate

    try:
        await el.fill(value)
        await el.press("Tab")
        actual = await el.input_value()
        ok = value.lower() in (actual or "").lower()
        return ok, meta
    except Exception as exc:
        return False, f"{meta} | fill_failed:{type(exc).__name__}"


async def fill_phone_adaptive(page):
    candidate = await find_semantic_input(
        page,
        keywords=["phone", "telefon", "telephone", "mobile", "mobil", "tel"],
        negative=["email", "first", "last", "surname", "name"],
    )
    if candidate is None:
        return False, ""

    _, frame, el, meta = candidate
    expected = re.sub(r"\D", "", CANDIDATE["phone"])
    local = expected[-9:]
    variants = [
        CANDIDATE["phone"],
        "+420" + local,
        "420" + local,
        local,
        " ".join([local[:3], local[3:6], local[6:]]),
    ]

    for value in variants:
        try:
            await el.fill(value)
            await el.press("Tab")
            await page.wait_for_timeout(150)
            actual = await el.input_value()
            digits = re.sub(r"\D", "", actual)
            if digits.endswith(local):
                return True, meta
        except Exception:
            pass

    return False, meta


async def direct_file_upload(page):
    """Attach the configured local PDF only through a real file input."""
    if not Path(CV_PATH).exists():
        return False

    for frame in await page_contexts(page):
        try:
            loc = frame.locator('input[type="file"]')
            for i in range(await loc.count()):
                el = loc.nth(i)
                try:
                    if await el.is_disabled():
                        continue
                    await el.set_input_files(CV_PATH)
                    await page.wait_for_timeout(300)
                    count = await el.evaluate("(e) => e.files ? e.files.length : 0")
                    if count and int(count) > 0:
                        return True
                except Exception:
                    pass
        except Exception:
            pass
    return False


async def cv_filename_visible(page):
    wanted = Path(CV_PATH).name.lower()
    stem = Path(CV_PATH).stem.lower()
    for frame in await page_contexts(page):
        try:
            body = (await frame.locator("body").inner_text()).lower()
            if wanted in body or stem in body:
                return True
        except Exception:
            pass
    return False


def is_resume_profile_url(url):
    low = (url or "").lower()
    return any(x in low for x in [
        "/osobni/zivotopis",
        "/profil/zivotopis",
        "/cvonline/",
    ])


def cv_positive_text(text):
    low = clean(text).lower()
    if not low:
        return False

    negatives = [
        "bez životopisu", "bez zivotopisu", "bez cv",
        "without cv", "no cv", "skip cv",
        "nepřiložit", "neprilozit", "nepřikládat", "neprikladat",
        "nechci přiložit", "nechci prilozit",
    ]
    if any(x in low for x in negatives):
        return False

    return any(x in low for x in [
        "životopis", "zivotopis", "cv", "resume", "curriculum vitae"
    ])


def upload_action_text(text):
    low = clean(text).lower()
    if not low:
        return False

    # Explicit profile-management labels are not attachment controls.
    blocked = [
        "můj životopis", "muj zivotopis",
        "upravit životopis", "upravit zivotopis",
        "vytvořit životopis", "vytvorit zivotopis",
        "správa životopisu", "sprava zivotopisu",
    ]
    if any(x in low for x in blocked):
        return False

    cv_words = ["životopis", "zivotopis", "cv", "resume", "soubor", "file"]
    action_words = [
        "nahrát", "nahrat", "přiložit", "prilozit", "přidat", "pridat",
        "vybrat", "zvolit", "upload", "attach", "choose", "add",
    ]
    return any(c in low for c in cv_words) and any(a in low for a in action_words)


async def safe_element_text(el):
    parts = []
    try:
        parts.append(await el.inner_text())
    except Exception:
        pass

    for attr in [
        "aria-label", "title", "value", "name", "id",
        "data-testid", "data-test", "class", "for"
    ]:
        try:
            v = await el.get_attribute(attr)
            if v:
                parts.append(v)
        except Exception:
            pass

    try:
        labels = await el.evaluate("""
            (e) => e.labels
                ? [...e.labels].map(x => x.innerText || x.textContent || '').join(' ')
                : ''
        """)
        if labels:
            parts.append(labels)
    except Exception:
        pass

    return clean(" ".join(x for x in parts if x))


def href_is_safe_upload(href):
    href = clean(href or "")
    low = href.lower()

    if not href or low in {"#", "javascript:void(0)", "javascript:void(0);"}:
        return True
    if low.startswith("javascript:"):
        return True

    blocked = [
        "/osobni/zivotopis",
        "/profil/zivotopis",
        "/cvonline/",
        "/zivotopis/",
        "/prihlasit-se/",
    ]
    if any(x in low for x in blocked):
        return False

    # Any real navigation is not trusted as an upload control.
    if low.startswith(("http://", "https://", "/")):
        return False

    return True


async def cv_attachment_detected(page):
    """Return True only for concrete evidence that a CV is attached/selected."""
    # File input with an actual selected file.
    for frame in await page_contexts(page):
        try:
            files = frame.locator('input[type="file"]')
            for i in range(await files.count()):
                el = files.nth(i)
                try:
                    count = await el.evaluate("(e) => e.files ? e.files.length : 0")
                    if count and int(count) > 0:
                        return True
                except Exception:
                    pass
        except Exception:
            pass

    if await cv_filename_visible(page):
        return True

    # Checked form option that clearly references a CV.
    for frame in await page_contexts(page):
        try:
            checked = frame.locator(
                'input[type="radio"]:checked, input[type="checkbox"]:checked'
            )
            for i in range(min(await checked.count(), 100)):
                el = checked.nth(i)
                text = await safe_element_text(el)
                if cv_positive_text(text):
                    return True
        except Exception:
            pass

    return False


async def save_cv_diagnostics(page):
    """
    Save a compact, CV-focused view of the live form.
    This is intentionally broader than application_debug.json.
    """
    data = {
        "url": page.url,
        "title": await page.title(),
        "cv_path": str(Path(CV_PATH).resolve()),
        "frames": [],
    }

    for frame in await page_contexts(page):
        row = {"url": frame.url, "candidates": []}
        selectors = [
            "input", "button", "a", "label", "select", "option",
            '[role="button"]', '[onclick]', '[tabindex]',
            '[data-testid]', '[data-test]'
        ]

        seen = set()
        for selector in selectors:
            try:
                loc = frame.locator(selector)
                for i in range(min(await loc.count(), 300)):
                    el = loc.nth(i)
                    try:
                        text = await safe_element_text(el)
                        low = text.lower()
                        if not (
                            cv_positive_text(text)
                            or upload_action_text(text)
                            or "file" in low
                            or "upload" in low
                            or "attach" in low
                            or "soubor" in low
                        ):
                            continue

                        try:
                            outer = await el.evaluate("(e) => e.outerHTML")
                        except Exception:
                            outer = ""

                        sig = clean(outer)[:800] or f"{selector}:{i}:{text}"
                        if sig in seen:
                            continue
                        seen.add(sig)

                        item = {
                            "selector_group": selector,
                            "text": clean(text)[:300],
                            "outer_html": clean(outer)[:1200],
                        }
                        for attr in [
                            "type", "name", "id", "href", "accept", "value",
                            "aria-label", "title", "data-testid", "data-test",
                        ]:
                            try:
                                item[attr] = (await el.get_attribute(attr) or "")[:400]
                            except Exception:
                                item[attr] = ""

                        try:
                            item["visible"] = await el.is_visible()
                        except Exception:
                            item["visible"] = False

                        try:
                            item["checked"] = await el.is_checked()
                        except Exception:
                            item["checked"] = None

                        row["candidates"].append(item)
                    except Exception:
                        pass
            except Exception:
                pass

        data["frames"].append(row)

    Path("cv_debug.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    try:
        await page.screenshot(path="cv_debug.png", full_page=True)
    except Exception:
        pass

    return data


async def select_saved_cv_control(page):
    """Use a saved CV only if it is an option inside the actual application form."""
    original_url = page.url

    # radio / checkbox
    for frame in await page_contexts(page):
        try:
            controls = frame.locator('input[type="radio"], input[type="checkbox"]')
            scored = []
            for i in range(min(await controls.count(), 180)):
                el = controls.nth(i)
                try:
                    if await el.is_disabled():
                        continue
                    text = await safe_element_text(el)
                    if not cv_positive_text(text):
                        continue

                    low = text.lower()
                    score = 10
                    for word in [
                        "uložen", "saved", "použít", "pouzit",
                        "vybrat", ".pdf", "soubor"
                    ]:
                        if word in low:
                            score += 3
                    scored.append((score, el, text))
                except Exception:
                    pass

            scored.sort(key=lambda x: x[0], reverse=True)
            for _, el, text in scored:
                try:
                    if not await el.is_checked():
                        await el.check(force=True)
                        await page.wait_for_timeout(250)

                    if is_resume_profile_url(page.url):
                        try:
                            await page.go_back(
                                wait_until="domcontentloaded", timeout=15000
                            )
                            await page.wait_for_timeout(400)
                        except Exception:
                            pass
                        continue

                    if await el.is_checked() and (
                        page.url == original_url or "externi-jof" in page.url
                    ):
                        return True, f"saved_cv_option:{clean(text)[:80]}"
                except Exception:
                    pass
        except Exception:
            pass

    # select
    for frame in await page_contexts(page):
        try:
            selects = frame.locator("select")
            for i in range(min(await selects.count(), 60)):
                sel = selects.nth(i)
                try:
                    options = sel.locator("option")
                    choices = []
                    for j in range(min(await options.count(), 120)):
                        opt = options.nth(j)
                        text = clean(await opt.inner_text())
                        value = await opt.get_attribute("value")
                        if not value or not cv_positive_text(text):
                            continue
                        if any(x in text.lower() for x in [
                            "bez životopisu", "bez zivotopisu", "without cv", "no cv"
                        ]):
                            continue
                        score = 10
                        if ".pdf" in text.lower() or "uložen" in text.lower():
                            score += 5
                        choices.append((score, value, text))

                    if choices:
                        choices.sort(reverse=True)
                        _, value, text = choices[0]
                        await sel.select_option(value=value)
                        await page.wait_for_timeout(250)
                        if await cv_attachment_detected(page) or (
                            not is_resume_profile_url(page.url)
                            and ("externi-jof" in page.url or page.url == original_url)
                        ):
                            return True, f"saved_cv_select:{clean(text)[:80]}"
                except Exception:
                    pass
        except Exception:
            pass

    return False, "no_saved_cv_option"


async def use_candidate_cv_control(page, el, description):
    original_url = page.url

    try:
        tag = (await el.evaluate("(e) => e.tagName")).lower()
    except Exception:
        tag = ""

    href = ""
    try:
        href = await el.get_attribute("href") or ""
    except Exception:
        pass

    if tag == "a" and not href_is_safe_upload(href):
        return False, f"unsafe_anchor:{description}"

    # Native chooser path.
    try:
        async with page.expect_file_chooser(timeout=1600) as info:
            await el.click(timeout=2800)
        chooser = await info.value
        await chooser.set_files(CV_PATH)
        await page.wait_for_timeout(350)

        if not is_resume_profile_url(page.url) and await cv_attachment_detected(page):
            return True, f"native_file_chooser:{description}"
    except Exception:
        pass

    # Normal click/check may reveal the actual file input or a second step.
    try:
        typ = (await el.get_attribute("type") or "").lower()
        if typ in {"radio", "checkbox"}:
            await el.check(force=True)
        else:
            await el.click(timeout=2800)
        await page.wait_for_timeout(300)
    except Exception:
        return False, f"click_failed:{description}"

    # Block navigation away from application.
    if is_resume_profile_url(page.url):
        try:
            await page.go_back(wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(450)
        except Exception:
            pass
        return False, f"profile_navigation_blocked:{description}"

    if page.url != original_url and "externi-jof" not in page.url:
        try:
            await page.go_back(wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(450)
        except Exception:
            pass
        return False, f"navigation_blocked:{description}"

    # A click may have exposed a file input.
    if await direct_file_upload(page):
        return True, f"revealed_file_input:{description}"

    if await cv_attachment_detected(page):
        return True, f"cv_state_changed:{description}"

    return False, f"no_effect:{description}"


async def discover_cv_controls(page):
    """
    Broad but guarded discovery of upload-like controls.
    Includes safe anchors and custom clickable elements.
    """
    selectors = [
        "button",
        "label",
        "a",
        '[role="button"]',
        'input[type="radio"]',
        'input[type="checkbox"]',
        '[onclick]',
        '[tabindex="0"]',
        '[data-testid]',
        '[data-test]',
    ]

    candidates = []
    seen = set()

    for frame in await page_contexts(page):
        for selector in selectors:
            try:
                loc = frame.locator(selector)
                for i in range(min(await loc.count(), 250)):
                    el = loc.nth(i)
                    try:
                        typ = (await el.get_attribute("type") or "").lower()
                        if typ not in {"radio", "checkbox"} and not await el.is_visible():
                            continue

                        text = await safe_element_text(el)
                        if not upload_action_text(text):
                            continue

                        try:
                            outer = await el.evaluate("(e) => e.outerHTML")
                        except Exception:
                            outer = f"{selector}:{i}:{text}"

                        sig = clean(str(outer))[:700]
                        if sig in seen:
                            continue
                        seen.add(sig)

                        low = text.lower()
                        score = 10
                        if any(x in low for x in [
                            "nahrát", "nahrat", "upload", "choose file",
                            "vybrat soubor"
                        ]):
                            score += 8
                        if any(x in low for x in [
                            "přiložit", "prilozit", "attach"
                        ]):
                            score += 5

                        try:
                            tag = (await el.evaluate("(e) => e.tagName")).lower()
                        except Exception:
                            tag = ""

                        if tag == "button":
                            score += 5
                        elif tag == "label":
                            score += 4
                        elif tag == "a":
                            href = await el.get_attribute("href") or ""
                            score += 2 if href_is_safe_upload(href) else -30

                        candidates.append((score, el, text))
                    except Exception:
                        pass
            except Exception:
                pass

    candidates.sort(key=lambda x: x[0], reverse=True)

    for score, el, text in candidates[:50]:
        if score < 0:
            continue
        ok, source = await use_candidate_cv_control(
            page, el, clean(text)[:100]
        )
        if ok:
            return True, source

        # after each interaction, check for an exposed file input
        if await direct_file_upload(page):
            return True, "direct_file_input_after_candidate"

    return False, "no_effective_cv_control"


async def manual_cv_fallback(page):
    """
    One bounded manual fallback.
    User only attaches/selects CV; final submit remains untouched.
    """
    if not MANUAL_CV_FALLBACK:
        return False, "manual_fallback_disabled"

    await save_cv_diagnostics(page)

    print("\n📎 CV BLOCK NOT IDENTIFIED AUTOMATICALLY")
    print("   In the opened Jobs.cz form, attach/select the CV manually.")
    print("   Do NOT click the final submit button.")
    print("   v32 will detect the CV and continue automatically.")
    print("   Diagnostic files: cv_debug.json and cv_debug.png")

    original_url = page.url

    for _ in range(max(1, MANUAL_CV_WAIT_SECONDS)):
        await page.wait_for_timeout(1000)

        if is_resume_profile_url(page.url):
            continue

        if page.url != original_url and "externi-jof" not in page.url:
            continue

        # If manual action exposed a real file input, fill it automatically.
        if await direct_file_upload(page):
            return True, "manual_reveal_then_auto_upload"

        if await cv_attachment_detected(page):
            return True, "manual_cv_detected"

    return False, "manual_cv_wait_expired"


async def upload_cv_adaptive(page):
    """
    v32:
      1) direct file input
      2) saved-CV option
      3) guarded discovery of custom upload controls
      4) diagnostics + one manual attach/select fallback
    """
    if not Path(CV_PATH).exists():
        return False, "cv_file_missing"

    if await direct_file_upload(page):
        return True, "direct_file_input"

    ok, source = await select_saved_cv_control(page)
    if ok:
        return True, source

    ok, source = await discover_cv_controls(page)
    if ok:
        return True, source

    if await cv_attachment_detected(page):
        return True, "cv_attachment_detected"

    ok, source = await manual_cv_fallback(page)
    if ok:
        return True, source

    return False, "cv_attachment_not_detected"



def candidate_display_name():
    name = clean(
        f"{CANDIDATE.get('first_name', '')} {CANDIDATE.get('last_name', '')}"
    )
    return name or "Kandidát"


def generate_czech_cover_letter(job):
    """
    Deterministic Czech cover letter based only on confirmed candidate skills
    and the vacancy/company metadata. No invented commercial experience.
    """
    job = job or {}
    title = clean(
        job.get("actual_title")
        or job.get("title")
        or "nabízenou pozici"
    )
    company = clean(job.get("company", "")).rstrip(" .")

    if company and company not in {
        "(company not detected)",
        "(not detected)",
    }:
        opening = (
            f'rád bych se ucházel o pozici „{title}“ '
            f've společnosti {company}.'
        )
    else:
        opening = f'rád bych se ucházel o pozici „{title}“.'

    t = normalize_key_text(title)
    if any(x in t for x in ["intern", "junior", "trainee", "staz", "zacinaj"]):
        interest = (
            "Pozice mě zaujala možností dále se rozvíjet v datové analytice "
            "a zároveň využít své dosavadní znalosti v praxi."
        )
    elif any(x in t for x in ["power bi", "business intelligence", "bi analyt"]):
        interest = (
            "Zaujalo mě zejména propojení práce s daty, reportingu a "
            "business intelligence."
        )
    elif "business" in t:
        interest = (
            "Zaujalo mě propojení analytické práce s praktickými potřebami "
            "byznysu a rozhodováním na základě dat."
        )
    else:
        interest = (
            "Pozice mě zaujala zaměřením na práci s daty a analytické úlohy."
        )

    letter = (
        "Dobrý den,\n\n"
        f"{opening} "
        "Jsem absolvent informatiky v Praze a mám pevné základy v SQL, "
        "statistické analýze, Excelu a vizualizaci dat. "
        "V rámci bakalářského projektu jsem pracoval se zpracováním dat, "
        "výzkumnou metodologií a interpretací statistických výsledků. "
        "Zároveň mám základní znalost Pythonu a Power BI. "
        f"{interest} "
        "Rád bych své analytické dovednosti dále rozvíjel a přispěl k práci "
        "vašeho týmu.\n\n"
        "Děkuji za zvážení mé žádosti.\n"
        "S pozdravem\n"
        f"{candidate_display_name()}"
    )
    return letter


def concise_czech_cover_letter(job):
    title = clean(
        (job or {}).get("actual_title")
        or (job or {}).get("title")
        or "nabízenou pozici"
    )
    return (
        "Dobrý den,\n\n"
        f'rád bych se ucházel o pozici „{title}“. '
        "Jsem absolvent informatiky v Praze se znalostí SQL, statistické "
        "analýzy, Excelu a datové vizualizace; mám také základní znalost "
        "Pythonu a Power BI. Rád bych své analytické dovednosti dále rozvíjel "
        "a využil je v praxi.\n\n"
        "Děkuji za zvážení mé žádosti.\n"
        "S pozdravem\n"
        f"{candidate_display_name()}"
    )


def cover_letter_semantic_score(meta):
    """
    Strict semantic score. Generic free-text questions should not be filled
    unless they clearly refer to a cover/motivation/employer message.
    """
    norm = normalize_key_text(meta or "")
    score = 0

    strong = [
        "pruvodni dopis",
        "motivacni dopis",
        "cover letter",
        "motivation letter",
        "motivacni text",
    ]
    employer_message = [
        "zprava pro zamestnavatele",
        "vzkaz pro zamestnavatele",
        "zprava pro personalistu",
        "vzkaz pro personalistu",
        "message to employer",
        "message to recruiter",
    ]

    if any(x in norm for x in strong):
        score += 100

    if any(x in norm for x in employer_message):
        score += 85

    if "cover" in norm and ("letter" in norm or "message" in norm):
        score += 60

    if "motivation" in norm or "motivac" in norm:
        score += 55

    # Helpful generic wording only when clearly application-oriented.
    if (
        ("proc" in norm and ("pozice" in norm or "prace" in norm))
        or "why are you interested" in norm
    ):
        score += 35

    negative = [
        "gdpr",
        "souhlas",
        "consent",
        "poznamka k dokumentu",
        "reference",
        "plat",
        "salary",
        "datum nastupu",
        "start date",
    ]
    if any(x in norm for x in negative):
        score -= 100

    return score


async def textarea_metadata(el):
    try:
        labels = await el.evaluate("""
            (e) => e.labels
              ? [...e.labels].map(
                  x => x.innerText || x.textContent || ''
                ).join(' ')
              : ''
        """)
    except Exception:
        labels = ""

    try:
        nearby = await el.evaluate("""
            (e) => {
              const p = e.closest(
                '.form-group, .field, .form-field, .control, label, section'
              );
              return p ? (p.innerText || p.textContent || '') : '';
            }
        """)
    except Exception:
        nearby = ""

    parts = []
    for attr in [
        "name",
        "id",
        "placeholder",
        "aria-label",
        "data-testid",
        "data-automation-id",
    ]:
        try:
            value = await el.get_attribute(attr)
            if value:
                parts.append(value)
        except Exception:
            pass

    if labels:
        parts.append(labels)
    if nearby:
        parts.append(clean(nearby)[:600])

    return clean(" ".join(parts))


async def find_cover_letter_field(page):
    candidates = []

    for frame in await page_contexts(page):
        # Standard textareas.
        try:
            loc = frame.locator("textarea")
            for i in range(min(await loc.count(), 120)):
                el = loc.nth(i)
                try:
                    if not await el.is_visible() or await el.is_disabled():
                        continue
                    meta = await textarea_metadata(el)
                    score = cover_letter_semantic_score(meta)
                    if score > 0:
                        candidates.append(
                            (score, "textarea", frame, el, meta)
                        )
                except Exception:
                    pass
        except Exception:
            pass

        # Rich-text application fields.
        try:
            loc = frame.locator(
                '[contenteditable="true"], '
                '[role="textbox"][contenteditable="true"]'
            )
            for i in range(min(await loc.count(), 80)):
                el = loc.nth(i)
                try:
                    if not await el.is_visible():
                        continue

                    parts = []
                    for attr in [
                        "id",
                        "class",
                        "aria-label",
                        "data-testid",
                        "data-placeholder",
                    ]:
                        value = await el.get_attribute(attr)
                        if value:
                            parts.append(value)

                    try:
                        nearby = await el.evaluate("""
                            (e) => {
                              const p = e.closest(
                                '.form-group, .field, .form-field, section'
                              );
                              return p
                                ? (p.innerText || p.textContent || '')
                                : '';
                            }
                        """)
                        if nearby:
                            parts.append(clean(nearby)[:600])
                    except Exception:
                        pass

                    meta = clean(" ".join(parts))
                    score = cover_letter_semantic_score(meta)
                    if score > 0:
                        candidates.append(
                            (score, "contenteditable", frame, el, meta)
                        )
                except Exception:
                    pass
        except Exception:
            pass

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0] if candidates else None


def fit_cover_letter_to_limit(job, max_chars):
    full = generate_czech_cover_letter(job)
    concise = concise_czech_cover_letter(job)

    configured = max(180, int(COVER_LETTER_MAX_CHARS))
    limit = configured

    if max_chars and max_chars > 0:
        limit = min(limit, max_chars)

    if len(full) <= limit:
        return full

    if len(concise) <= limit:
        return concise

    # Keep greeting/signature even for unusually small employer limits.
    signature = f"\n\nS pozdravem\n{candidate_display_name()}"
    body_limit = max(80, limit - len(signature))
    trimmed = concise[:body_limit].rstrip(" ,;:-")
    if not trimmed.endswith((".", "!", "?")):
        trimmed += "."
    return (trimmed + signature)[:limit]


async def fill_czech_cover_letter(page, job):
    result = {
        "filled": False,
        "source": "",
        "language": "cs",
        "chars": 0,
        "field_meta": "",
        "existing": False,
    }

    if not AUTO_CZECH_COVER_LETTER:
        result["source"] = "disabled"
        return result

    if COVER_LETTER_LANGUAGE not in {"cs", "cz", "czech"}:
        result["source"] = "unsupported_language"
        return result

    candidate = await find_cover_letter_field(page)
    if candidate is None:
        result["source"] = "field_not_found"
        return result

    score, kind, _, el, meta = candidate
    result["field_meta"] = clean(meta)[:300]

    # Preserve text if the user/employer system already populated the field.
    try:
        if kind == "textarea":
            existing = clean(await el.input_value())
        else:
            existing = clean(await el.inner_text())
    except Exception:
        existing = ""

    if existing:
        result["filled"] = True
        result["existing"] = True
        result["source"] = f"existing_{kind}"
        result["chars"] = len(existing)
        return result

    max_chars = 0
    try:
        raw_max = await el.get_attribute("maxlength")
        if raw_max and raw_max.isdigit():
            max_chars = int(raw_max)
    except Exception:
        pass

    letter = fit_cover_letter_to_limit(job, max_chars)

    try:
        if kind == "textarea":
            await el.fill(letter)
            actual = await el.input_value()
        else:
            await el.click()
            await el.fill(letter)
            actual = await el.inner_text()

        actual = actual or ""
        result["filled"] = len(clean(actual)) >= min(80, len(clean(letter)))
        result["source"] = f"semantic_{kind}_score_{score}"
        result["chars"] = len(actual)
        return result
    except Exception as exc:
        result["source"] = f"fill_failed:{type(exc).__name__}"
        return result

async def inspect_form(page, job=None):
    result = {
        "first_name": False,
        "first_name_source": "",
        "last_name": False,
        "last_name_source": "",
        "email": False,
        "phone": False,
        "phone_present": False,
        "phone_source": "",
        "cv": False,
        "cv_source": "",
        "cover_letter": False,
        "cover_letter_language": "",
        "cover_letter_source": "",
        "cover_letter_chars": 0,
        "submit": False,
        "submit_text": "",
        "current_url": page.url,
    }

    async def fill_any(selectors, value):
        for frame in await page_contexts(page):
            for sel in selectors:
                try:
                    loc = frame.locator(sel).first
                    if await loc.count() and await loc.is_visible() and not await loc.is_disabled():
                        await loc.fill(value)
                        return frame, sel
                except Exception:
                    pass
        return None, None

    async def read_any(selectors):
        for frame in await page_contexts(page):
            for sel in selectors:
                try:
                    loc = frame.locator(sel).first
                    if await loc.count() and await loc.is_visible():
                        return await loc.input_value()
                except Exception:
                    pass
        return ""

    # Names / email: keep proven v28 selectors.
    await fill_any([
        'input[autocomplete="given-name"]',
        'input[name*="first" i]',
        'input[id*="first" i]',
        'input[name*="given" i]',
        'input[id*="given" i]',
        'input[name*="jmeno" i]',
        'input[id*="jmeno" i]',
        'input[name*="jméno" i]',
        'input[id*="jméno" i]',
        'input[name*="krest" i]',
        'input[id*="krest" i]',
    ], CANDIDATE["first_name"])

    await fill_any([
        'input[autocomplete="family-name"]',
        'input[name*="last" i]',
        'input[id*="last" i]',
        'input[name*="surname" i]',
        'input[id*="surname" i]',
        'input[name*="prijmen" i]',
        'input[id*="prijmen" i]',
        'input[name*="příjmen" i]',
        'input[id*="příjmen" i]',
    ], CANDIDATE["last_name"])

    await fill_any([
        'input[type="email"]',
        'input[name*="email" i]',
        'input[id*="email" i]',
    ], CANDIDATE["email"])

    # Phone: first use known selectors, then semantic fallback.
    phone_frame, phone_sel = await fill_any([
        'input[type="tel"]',
        'input[name*="phone" i]',
        'input[id*="phone" i]',
        'input[name*="telefon" i]',
        'input[id*="telefon" i]',
        'input[name*="mobile" i]',
        'input[id*="mobile" i]',
    ], CANDIDATE["phone"])

    expected_phone = re.sub(r"\D", "", CANDIDATE["phone"])
    local_phone = expected_phone[-9:]
    phone_val = await read_any([
        'input[type="tel"]',
        'input[name*="phone" i]',
        'input[id*="phone" i]',
        'input[name*="telefon" i]',
        'input[id*="telefon" i]',
        'input[name*="mobile" i]',
        'input[id*="mobile" i]',
    ])
    digits = re.sub(r"\D", "", phone_val)

    semantic_phone = await find_semantic_input(
        page,
        keywords=["phone", "telefon", "telephone", "mobile", "mobil", "tel"],
        negative=["email", "first", "last", "surname", "name"],
    )
    result["phone_present"] = bool(
        phone_frame is not None or phone_val or semantic_phone is not None
    )

    result["phone"] = bool(digits and digits.endswith(local_phone))
    if result["phone"]:
        result["phone_source"] = phone_sel or "known_selector"
    elif result["phone_present"]:
        result["phone"], result["phone_source"] = await fill_phone_adaptive(page)
    else:
        result["phone"] = True
        result["phone_source"] = "not_present_optional"

    # CV: adaptive external-form upload.
    result["cv"], result["cv_source"] = await upload_cv_adaptive(page)

    if is_resume_profile_url(page.url):
        result["cv"] = False
        result["cv_source"] = "blocked_profile_navigation"
        result["current_url"] = page.url
        return result

    # Optional Czech cover / motivation letter.
    cover_state = await fill_czech_cover_letter(page, job or {})
    result["cover_letter"] = cover_state.get("filled", False)
    result["cover_letter_language"] = cover_state.get("language", "")
    result["cover_letter_source"] = cover_state.get("source", "")
    result["cover_letter_chars"] = cover_state.get("chars", 0)

    first_val = await read_any([
        'input[autocomplete="given-name"]',
        'input[name*="first" i]',
        'input[id*="first" i]',
        'input[name*="given" i]',
        'input[id*="given" i]',
        'input[name*="jmeno" i]',
        'input[id*="jmeno" i]',
        'input[name*="jméno" i]',
        'input[id*="jméno" i]',
        'input[name*="krest" i]',
        'input[id*="krest" i]',
    ])
    last_val = await read_any([
        'input[autocomplete="family-name"]',
        'input[name*="last" i]',
        'input[id*="last" i]',
        'input[name*="surname" i]',
        'input[id*="surname" i]',
        'input[name*="prijmen" i]',
        'input[id*="prijmen" i]',
        'input[name*="příjmen" i]',
        'input[id*="příjmen" i]',
    ])
    email_val = await read_any([
        'input[type="email"]',
        'input[name*="email" i]',
        'input[id*="email" i]',
    ])

    result["first_name"] = (
        CANDIDATE["first_name"].lower() in first_val.lower()
    )
    if result["first_name"]:
        result["first_name_source"] = "known_selector"
    else:
        (
            result["first_name"],
            result["first_name_source"],
        ) = await fill_semantic_name(
            page,
            "first",
            CANDIDATE["first_name"],
        )

    result["last_name"] = (
        CANDIDATE["last_name"].lower() in last_val.lower()
    )
    if result["last_name"]:
        result["last_name_source"] = "known_selector"
    else:
        (
            result["last_name"],
            result["last_name_source"],
        ) = await fill_semantic_name(
            page,
            "last",
            CANDIDATE["last_name"],
        )

    result["email"] = CANDIDATE["email"].lower() in email_val.lower()

    # Submit detection.
    for frame in await page_contexts(page):
        for sel in [
            'button:has-text("ODESLAT")',
            'button:has-text("Odeslat")',
            'button:has-text("Poslat")',
            'button:has-text("Odpovědět")',
            'input[type="submit"]',
            'button[type="submit"]',
        ]:
            try:
                loc = frame.locator(sel).first
                if await loc.count() and await loc.is_visible():
                    result["submit"] = True
                    try:
                        result["submit_text"] = clean(await loc.inner_text())
                    except Exception:
                        result["submit_text"] = await loc.get_attribute("value") or "submit"
                    break
            except Exception:
                pass
        if result["submit"]:
            break

    result["current_url"] = page.url
    return result


def is_jobs_domain(url):
    return "jobs.cz" in (url or "").lower()


def is_pwc_careers_url(url):
    low = (url or "").lower()
    return (
        "jobs-cee.pwc.com" in low
        or "careers.pwc.com" in low
        or (
            "pwc.wd" in low
            and "myworkdayjobs.com" in low
        )
    )


def is_workday_url(url):
    low = (url or "").lower()
    return any(x in low for x in [
        "myworkdayjobs.com",
        "myworkday.com",
        "myworkdaysite.com",
        "workday.com",
        "workdayjobs.com",
        "wd1.myworkdayjobs.com",
        "wd3.myworkdayjobs.com",
        "wd5.myworkdayjobs.com",
    ])


async def is_jobs_handoff_page(page):
    if "/externi-jof/" not in (page.url or "").lower():
        return False
    for frame in await page_contexts(page):
        try:
            button = frame.get_by_role(
                "button",
                name=re.compile(r"pokračovat\s+v\s+odpovědi", re.I),
            ).first
            if await button.count() and await button.is_visible():
                return True
        except Exception:
            pass
    return False


async def inspect_jobs_handoff(page):
    result = {
        "stage": "jobs_handoff",
        "first_name": False,
        "last_name": False,
        "email": False,
        "phone": True,
        "phone_present": False,
        "phone_source": "not_present_on_handoff",
        "cv": True,
        "cv_source": "not_required_on_handoff",
        "cover_letter": False,
        "submit": False,
        "submit_text": "",
        "current_url": page.url,
    }

    async def fill_exact(selectors, value):
        for frame in await page_contexts(page):
            for sel in selectors:
                try:
                    loc = frame.locator(sel).first
                    if await loc.count() and await loc.is_visible() and not await loc.is_disabled():
                        await loc.fill(value)
                        return loc
                except Exception:
                    pass
        return None

    first = await fill_exact([
        'input[name="jobad_application[firstName]"]',
        '#jobad_application_firstName',
    ], CANDIDATE["first_name"])
    last = await fill_exact([
        'input[name="jobad_application[surname]"]',
        '#jobad_application_surname',
    ], CANDIDATE["last_name"])
    email = await fill_exact([
        'input[name="jobad_application[email]"]',
        '#jobad_application_email',
        'input[type="email"]',
    ], CANDIDATE["email"])

    try:
        result["first_name"] = first is not None and CANDIDATE["first_name"].lower() in (await first.input_value()).lower()
    except Exception:
        pass
    try:
        result["last_name"] = last is not None and CANDIDATE["last_name"].lower() in (await last.input_value()).lower()
    except Exception:
        pass
    try:
        result["email"] = email is not None and CANDIDATE["email"].lower() in (await email.input_value()).lower()
    except Exception:
        pass

    for frame in await page_contexts(page):
        try:
            button = frame.get_by_role(
                "button",
                name=re.compile(r"pokračovat\s+v\s+odpovědi", re.I),
            ).first
            if await button.count() and await button.is_visible():
                result["submit"] = True
                result["submit_text"] = clean(await button.inner_text())
                break
        except Exception:
            pass
    return result


async def click_jobs_handoff(page):
    context = page.context
    old_pages = list(context.pages)
    old_url = page.url

    target = None
    for frame in await page_contexts(page):
        try:
            button = frame.get_by_role(
                "button",
                name=re.compile(r"pokračovat\s+v\s+odpovědi", re.I),
            ).first
            if await button.count() and await button.is_visible():
                target = button
                break
        except Exception:
            pass

    if target is None:
        return None, "handoff_button_not_found"

    try:
        await target.click(timeout=10000)
    except Exception as exc:
        return None, f"handoff_click_failed:{exc}"

    for _ in range(50):
        await page.wait_for_timeout(400)
        new_pages = [p for p in context.pages if p not in old_pages]
        for p in new_pages:
            try:
                if p.url and p.url != "about:blank":
                    try:
                        await p.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    return p, "handoff_popup"
            except Exception:
                pass

        if page.url != old_url and "/externi-jof/" not in page.url.lower():
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            return page, "handoff_redirect"

    return page, "handoff_timeout"


async def save_stage_debug(page, json_name, png_name):
    data = {"url": page.url, "title": "", "frames": []}
    try:
        data["title"] = await page.title()
    except Exception:
        pass

    for frame in await page_contexts(page):
        row = {
            "url": frame.url,
            "forms": [],
            "controls": [],
            "inputs": [],
            "textareas": [],
            "selects": [],
        }

        try:
            forms = frame.locator("form")
            for i in range(min(await forms.count(), 30)):
                el = forms.nth(i)
                try:
                    row["forms"].append({
                        "action": (await el.get_attribute("action") or "")[:1000],
                        "method": (await el.get_attribute("method") or "")[:80],
                        "text": clean(await el.inner_text())[:1500],
                    })
                except Exception:
                    pass
        except Exception:
            pass

        try:
            controls = frame.locator('button, a, [role="button"], input[type="submit"]')
            for i in range(min(await controls.count(), 260)):
                el = controls.nth(i)
                try:
                    if not await el.is_visible():
                        continue
                    text = clean(await el.inner_text())
                    if not text:
                        text = clean(await el.get_attribute("value") or "")
                    row["controls"].append({
                        "tag": await el.evaluate("(e) => e.tagName"),
                        "text": text[:400],
                        "href": (await el.get_attribute("href") or "")[:1000],
                        "type": (await el.get_attribute("type") or "")[:100],
                        "name": (await el.get_attribute("name") or "")[:250],
                        "id": (await el.get_attribute("id") or "")[:250],
                        "aria": (await el.get_attribute("aria-label") or "")[:400],
                        "data_automation_id": (await el.get_attribute("data-automation-id") or "")[:300],
                    })
                except Exception:
                    pass
        except Exception:
            pass

        try:
            inputs = frame.locator("input")
            for i in range(min(await inputs.count(), 320)):
                el = inputs.nth(i)
                try:
                    labels = await el.evaluate("""
                        (e) => e.labels
                          ? [...e.labels].map(x => x.innerText || x.textContent || '').join(' ')
                          : ''
                    """)
                    row["inputs"].append({
                        "type": (await el.get_attribute("type") or "")[:100],
                        "name": (await el.get_attribute("name") or "")[:250],
                        "id": (await el.get_attribute("id") or "")[:250],
                        "placeholder": (await el.get_attribute("placeholder") or "")[:400],
                        "autocomplete": (await el.get_attribute("autocomplete") or "")[:150],
                        "accept": (await el.get_attribute("accept") or "")[:400],
                        "labels": clean(labels)[:500],
                        "aria": (await el.get_attribute("aria-label") or "")[:400],
                        "data_automation_id": (await el.get_attribute("data-automation-id") or "")[:300],
                        "visible": await el.is_visible(),
                    })
                except Exception:
                    pass
        except Exception:
            pass

        try:
            tas = frame.locator("textarea")
            for i in range(min(await tas.count(), 120)):
                el = tas.nth(i)
                try:
                    row["textareas"].append({
                        "name": (await el.get_attribute("name") or "")[:250],
                        "id": (await el.get_attribute("id") or "")[:250],
                        "placeholder": (await el.get_attribute("placeholder") or "")[:400],
                        "data_automation_id": (await el.get_attribute("data-automation-id") or "")[:300],
                    })
                except Exception:
                    pass
        except Exception:
            pass

        try:
            sels = frame.locator("select")
            for i in range(min(await sels.count(), 120)):
                el = sels.nth(i)
                try:
                    row["selects"].append({
                        "name": (await el.get_attribute("name") or "")[:250],
                        "id": (await el.get_attribute("id") or "")[:250],
                        "data_automation_id": (await el.get_attribute("data-automation-id") or "")[:300],
                    })
                except Exception:
                    pass
        except Exception:
            pass

        data["frames"].append(row)

    Path(json_name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        await page.screenshot(path=png_name, full_page=True)
    except Exception:
        pass
    return data


async def dismiss_pwc_cookie_banner(page):
    # Prefer Deny: enough to remove the overlay without granting optional tracking.
    for pattern in [
        re.compile(r"^Deny$", re.I),
        re.compile(r"Reject", re.I),
        re.compile(r"Decline", re.I),
    ]:
        for frame in await page_contexts(page):
            try:
                btn = frame.get_by_role("button", name=pattern).first
                if await btn.count() and await btn.is_visible():
                    await btn.click(timeout=4000)
                    await page.wait_for_timeout(300)
                    return True
            except Exception:
                pass
    return False


def pwc_job_code_from_url(url):
    m = re.search(r"/job/([^/]+)/", url or "", re.I)
    return m.group(1) if m else ""


async def click_current_pwc_apply(page):
    """
    Click only the current vacancy's exact Apply Now link.
    Recommended-job Apply buttons have longer accessible names and are ignored.
    """
    await dismiss_pwc_cookie_banner(page)
    context = page.context
    old_pages = list(context.pages)
    old_url = page.url
    job_code = pwc_job_code_from_url(page.url)

    candidates = []
    for frame in await page_contexts(page):
        try:
            links = frame.locator('a[href*="/apply?jobSeqNo="]')
            for i in range(min(await links.count(), 50)):
                el = links.nth(i)
                try:
                    if not await el.is_visible():
                        continue
                    text = clean(await el.inner_text())
                    href = await el.get_attribute("href") or ""
                    aria = await el.get_attribute("aria-label") or ""

                    score = 0
                    if text.lower() == "apply now":
                        score += 20
                    if aria.strip().lower() in {"", "apply now"}:
                        score += 5
                    if job_code and job_code.lower() in href.lower():
                        score += 20
                    # Related jobs generally expose their title in text/aria.
                    if text.lower().startswith("apply now ") and text.lower() != "apply now":
                        score -= 20
                    candidates.append((score, el, href, text, aria))
                except Exception:
                    pass
        except Exception:
            pass

    if not candidates:
        return page, "pwc_apply_not_found"

    candidates.sort(key=lambda x: x[0], reverse=True)
    score, target, href, text, aria = candidates[0]
    if score < 15:
        return page, "pwc_apply_ambiguous"

    try:
        await target.click(timeout=10000)
    except Exception:
        # Direct navigation to the exact href is safe here because we already
        # selected the current vacancy's Apply link.
        try:
            await page.goto(href, wait_until="domcontentloaded", timeout=30000)
            return page, "pwc_apply_direct_navigation"
        except Exception as exc:
            return page, f"pwc_apply_failed:{exc}"

    # Follow popup or redirect.
    for _ in range(60):
        await page.wait_for_timeout(400)

        new_pages = [p for p in context.pages if p not in old_pages]
        for p in new_pages:
            try:
                if p.url and p.url != "about:blank":
                    try:
                        await p.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    return p, "pwc_apply_popup"
            except Exception:
                pass

        if page.url != old_url:
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            return page, "pwc_apply_redirect"

    return page, "pwc_apply_clicked_no_redirect"


async def follow_apply_chain(page):
    """
    PwC's /apply endpoint can itself redirect to another ATS/Workday URL.
    Wait for the chain to settle.
    """
    last_url = page.url
    stable = 0

    for _ in range(50):
        await page.wait_for_timeout(400)
        current = page.url

        if current == last_url:
            stable += 1
        else:
            stable = 0
            last_url = current

        if is_workday_url(current):
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            return page, "workday_reached"

        # Non-PwC external ATS is also a valid destination.
        if current and not is_pwc_careers_url(current):
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            return page, "external_ats_reached"

        if stable >= 8:
            break

    return page, "apply_chain_settled"


async def workday_login_like(page):
    text = ""
    try:
        text = clean(await page.locator("body").inner_text()).lower()
    except Exception:
        pass

    signals = [
        "sign in",
        "create account",
        "already have an account",
        "candidate home",
        "email address",
        "password",
    ]
    return sum(1 for s in signals if s in text) >= 2


async def workday_application_like(page):
    text = ""
    try:
        text = clean(await page.locator("body").inner_text()).lower()
    except Exception:
        pass

    signals = [
        "autofill with resume",
        "apply manually",
        "my information",
        "resume",
        "experience",
        "application",
    ]
    return any(s in text for s in signals)


async def workday_manual_bootstrap(page):
    if not WORKDAY_MANUAL_BOOTSTRAP:
        return False

    print("\n🧑‍💻 WORKDAY ACTION REQUIRED")
    print("   If Workday asks you to sign in/create an account, complete that manually.")
    print("   Do not submit the final application.")
    print("   v34 will continue automatically when the application page appears.")

    for _ in range(max(1, WORKDAY_WAIT_SECONDS)):
        await page.wait_for_timeout(1000)

        if await workday_application_like(page) and not await workday_login_like(page):
            return True

        # URL can change after sign-in.
        if is_workday_url(page.url):
            try:
                if await page.locator('input[type="file"]').count():
                    return True
            except Exception:
                pass

    return False


async def try_workday_resume_start(page):
    """
    On Workday start pages, prefer Autofill with Resume when available.
    This is an intermediate action, not final submission.
    """
    for name in [
        re.compile(r"autofill with resume", re.I),
        re.compile(r"upload resume", re.I),
        re.compile(r"use my resume", re.I),
    ]:
        for role in ["button", "link"]:
            try:
                el = page.get_by_role(role, name=name).first
                if await el.count() and await el.is_visible():
                    # Some buttons immediately expose a chooser.
                    try:
                        async with page.expect_file_chooser(timeout=1800) as info:
                            await el.click(timeout=5000)
                        chooser = await info.value
                        await chooser.set_files(CV_PATH)
                        await page.wait_for_timeout(600)
                        return True, "workday_autofill_file_chooser"
                    except Exception:
                        try:
                            await el.click(timeout=5000)
                            await page.wait_for_timeout(600)
                        except Exception:
                            pass

                    if await direct_file_upload(page):
                        return True, "workday_autofill_file_input"
                    return False, "workday_autofill_clicked"
            except Exception:
                pass

    # If a file input is already present, upload directly.
    if await direct_file_upload(page):
        return True, "workday_direct_file_input"

    return False, "workday_resume_start_not_found"


def is_phenom_apply_url(url):
    low = (url or "").lower()
    return "/apply?" in low and (
        "jobs-cee.pwc.com" in low or "careers.phenom.com" in low or "stepname=" in low
    )


def phenom_step_from_url(url):
    m = re.search(r"[?&]step=(\d+)", url or "", re.I)
    return int(m.group(1)) if m else None


def phenom_stepname_from_url(url):
    m = re.search(r"[?&]stepname=([^&]+)", url or "", re.I)
    return m.group(1) if m else ""


async def wait_for_phenom_form(page):
    for _ in range(40):
        try:
            if await page.locator(
                'input[type="file"], input[type="email"], '
                'button:has-text("Upload Resume"), button:has-text("Next"), '
                '[data-automation-id]'
            ).count():
                return True
        except Exception:
            pass
        await page.wait_for_timeout(250)
    return False


async def phenom_upload_resume(page):
    if await direct_file_upload(page):
        return True, "phenom_direct_file_input"

    pats = [
        re.compile(r"upload resume", re.I),
        re.compile(r"upload cv", re.I),
        re.compile(r"attach resume", re.I),
        re.compile(r"attach cv", re.I),
        re.compile(r"choose file", re.I),
    ]
    for frame in await page_contexts(page):
        for role in ["button", "link"]:
            for pat in pats:
                try:
                    el = frame.get_by_role(role, name=pat).first
                    if not await el.count() or not await el.is_visible():
                        continue
                    try:
                        async with page.expect_file_chooser(timeout=2000) as info:
                            await el.click(timeout=5000)
                        chooser = await info.value
                        await chooser.set_files(CV_PATH)
                        await page.wait_for_timeout(600)
                        return True, f"phenom_file_chooser:{pat.pattern}"
                    except Exception:
                        try:
                            await el.click(timeout=3000)
                            await page.wait_for_timeout(350)
                        except Exception:
                            pass
                    if await direct_file_upload(page):
                        return True, f"phenom_revealed_file_input:{pat.pattern}"
                except Exception:
                    pass
    return False, "phenom_cv_not_found"


async def phenom_fill_basic_field(page, selectors, value):
    for frame in await page_contexts(page):
        for sel in selectors:
            try:
                loc = frame.locator(sel).first
                if await loc.count() and await loc.is_visible() and not await loc.is_disabled():
                    await loc.fill(value)
                    await loc.press("Tab")
                    actual = await loc.input_value()
                    if value.lower() in actual.lower():
                        return True, sel
            except Exception:
                pass
    return False, ""


async def fill_phenom_phone_country(page):
    # Native select.
    for frame in await page_contexts(page):
        try:
            sels = frame.locator("select")
            for i in range(min(await sels.count(), 50)):
                sel = sels.nth(i)
                opts = sel.locator("option")
                for j in range(min(await opts.count(), 350)):
                    opt = opts.nth(j)
                    text = clean(await opt.inner_text())
                    value = await opt.get_attribute("value") or ""
                    low = f"{text} {value}".lower()
                    if "+420" in low or "czech republic" in low or "czechia" in low:
                        try:
                            if value:
                                await sel.select_option(value=value)
                            else:
                                await sel.select_option(label=text)
                            await page.wait_for_timeout(200)
                            return True, f"native_select:{text[:80]}"
                        except Exception:
                            pass
        except Exception:
            pass

    # Custom combobox.
    for frame in await page_contexts(page):
        try:
            combos = frame.locator('[role="combobox"], input[aria-haspopup="listbox"]')
            for i in range(min(await combos.count(), 40)):
                combo = combos.nth(i)
                if not await combo.is_visible():
                    continue
                meta = " ".join([
                    await combo.get_attribute("aria-label") or "",
                    await combo.get_attribute("placeholder") or "",
                    await combo.get_attribute("name") or "",
                    await combo.get_attribute("id") or "",
                ]).lower()
                if not any(x in meta for x in ["phone", "country", "code", "mobile"]):
                    continue
                try:
                    await combo.click(timeout=3000)
                    await page.wait_for_timeout(250)
                except Exception:
                    continue
                for pat in [
                    re.compile(r"Czech Republic.*420", re.I),
                    re.compile(r"Czechia.*420", re.I),
                    re.compile(r"\+420", re.I),
                    re.compile(r"Czech Republic", re.I),
                    re.compile(r"Czechia", re.I),
                ]:
                    try:
                        opt = page.get_by_role("option", name=pat).first
                        if await opt.count() and await opt.is_visible():
                            await opt.click(timeout=3000)
                            return True, f"combobox:{pat.pattern}"
                    except Exception:
                        pass
        except Exception:
            pass
    return False, "country_code_not_found"


async def fill_phenom_phone_number(page):
    local = re.sub(r"\D", "", CANDIDATE["phone"])[-9:]
    selectors = [
        'input[type="tel"]',
        'input[name*="phone" i]', 'input[id*="phone" i]',
        'input[name*="mobile" i]', 'input[id*="mobile" i]',
        'input[data-automation-id*="phone" i]',
    ]
    for frame in await page_contexts(page):
        for sel in selectors:
            try:
                loc = frame.locator(sel)
                for i in range(min(await loc.count(), 30)):
                    el = loc.nth(i)
                    if not await el.is_visible() or await el.is_disabled():
                        continue
                    meta = " ".join([
                        await el.get_attribute("name") or "",
                        await el.get_attribute("id") or "",
                        await el.get_attribute("aria-label") or "",
                        await el.get_attribute("placeholder") or "",
                    ]).lower()
                    if any(x in meta for x in ["country", "code"]):
                        continue
                    for value in [local, CANDIDATE["phone"], f"{local[:3]} {local[3:6]} {local[6:]}"]:
                        try:
                            await el.fill(value)
                            await el.press("Tab")
                            actual = re.sub(r"\D", "", await el.input_value())
                            if actual.endswith(local):
                                return True, sel
                        except Exception:
                            pass
            except Exception:
                pass
    return False, "phone_number_not_found"


async def phenom_find_intermediate_next(page):
    pats = [
        re.compile(r"^next$", re.I),
        re.compile(r"^continue$", re.I),
        re.compile(r"save\s*(and|&)?\s*continue", re.I),
        re.compile(r"continue application", re.I),
    ]
    for frame in await page_contexts(page):
        for role in ["button", "link"]:
            for pat in pats:
                try:
                    el = frame.get_by_role(role, name=pat).first
                    if await el.count() and await el.is_visible():
                        return el, clean(await el.inner_text()) or pat.pattern
                except Exception:
                    pass
    return None, ""


async def phenom_find_final_submit(page):
    pats = [
        re.compile(r"^submit$", re.I),
        re.compile(r"submit application", re.I),
        re.compile(r"send application", re.I),
        re.compile(r"complete application", re.I),
    ]
    for frame in await page_contexts(page):
        for role in ["button", "link"]:
            for pat in pats:
                try:
                    el = frame.get_by_role(role, name=pat).first
                    if await el.count() and await el.is_visible():
                        return el, clean(await el.inner_text()) or pat.pattern
                except Exception:
                    pass
    return None, ""


async def phenom_required_unfilled(page):
    missing = []
    for frame in await page_contexts(page):
        try:
            fields = frame.locator('input[required], select[required], textarea[required], [aria-required="true"]')
            for i in range(min(await fields.count(), 180)):
                el = fields.nth(i)
                try:
                    if not await el.is_visible() or await el.is_disabled():
                        continue
                    tag = (await el.evaluate("(e) => e.tagName")).lower()
                    typ = (await el.get_attribute("type") or "").lower()
                    meta = clean(" ".join([
                        await el.get_attribute("name") or "",
                        await el.get_attribute("id") or "",
                        await el.get_attribute("aria-label") or "",
                        await el.get_attribute("placeholder") or "",
                        await el.get_attribute("data-automation-id") or "",
                    ]))
                    if typ in {"checkbox", "radio"}:
                        blank = not await el.is_checked()
                    elif tag == "select":
                        blank = not bool(await el.input_value())
                    else:
                        blank = not bool(clean(await el.input_value()))
                    if blank:
                        missing.append(meta[:250] or f"{tag}:{typ}")
                except Exception:
                    pass
        except Exception:
            pass
    out, seen = [], set()
    for x in missing:
        if x not in seen:
            seen.add(x); out.append(x)
    return out


async def fill_phenom_personal_information(page):
    await wait_for_phenom_form(page)
    result = {
        "stage": "phenom_personal_information",
        "first_name": False, "last_name": False, "email": False,
        "phone": False, "phone_present": False, "phone_source": "",
        "cv": False, "cv_source": "", "cover_letter": False,
        "submit": False, "submit_text": "", "current_url": page.url,
    }

    result["cv"], result["cv_source"] = await phenom_upload_resume(page)
    result["first_name"], _ = await phenom_fill_basic_field(page, [
        'input[autocomplete="given-name"]', 'input[name*="first" i]',
        'input[id*="first" i]', 'input[data-automation-id*="first" i]'
    ], CANDIDATE["first_name"])
    result["last_name"], _ = await phenom_fill_basic_field(page, [
        'input[autocomplete="family-name"]', 'input[name*="last" i]',
        'input[id*="last" i]', 'input[name*="surname" i]',
        'input[id*="surname" i]', 'input[data-automation-id*="last" i]'
    ], CANDIDATE["last_name"])
    result["email"], _ = await phenom_fill_basic_field(page, [
        'input[type="email"]', 'input[autocomplete="email"]',
        'input[name*="email" i]', 'input[id*="email" i]',
        'input[data-automation-id*="email" i]'
    ], CANDIDATE["email"])

    phone_visible = False
    for frame in await page_contexts(page):
        try:
            loc = frame.locator('input[type="tel"], input[name*="phone" i], input[id*="phone" i], input[name*="mobile" i], input[id*="mobile" i], [data-automation-id*="phone" i]')
            for i in range(min(await loc.count(), 30)):
                if await loc.nth(i).is_visible():
                    phone_visible = True; break
        except Exception:
            pass
        if phone_visible:
            break
    result["phone_present"] = phone_visible
    if phone_visible:
        _, country_src = await fill_phenom_phone_country(page)
        phone_ok, phone_src = await fill_phenom_phone_number(page)
        result["phone"] = phone_ok
        result["phone_source"] = f"{country_src};{phone_src}"
    else:
        result["phone"] = True
        result["phone_source"] = "not_present_optional"

    final_el, final_text = await phenom_find_final_submit(page)
    if final_el is not None:
        result["submit"] = True
        result["submit_text"] = final_text
    return result


def normalize_yes_no(value):
    low = clean(value).lower()
    if low in {"yes", "y", "true", "1", "ano"}:
        return "yes"
    if low in {"no", "n", "false", "0", "ne"}:
        return "no"
    return ""


async def phenom_select_options(page, select_id):
    for frame in await page_contexts(page):
        try:
            sel = frame.locator(f'[id="{select_id}"]').first
            if await sel.count():
                opts = sel.locator("option")
                result = []
                for i in range(await opts.count()):
                    opt = opts.nth(i)
                    result.append({
                        "text": clean(await opt.inner_text()),
                        "value": await opt.get_attribute("value") or "",
                        "selected": await opt.is_checked() if (await opt.get_attribute("selected")) is not None else False,
                    })
                return result
        except Exception:
            pass
    return []


async def phenom_select_current(page, select_id):
    for frame in await page_contexts(page):
        try:
            sel = frame.locator(f'[id="{select_id}"]').first
            if await sel.count():
                value = await sel.input_value()
                try:
                    text = clean(
                        await sel.locator("option:checked").first.inner_text()
                    )
                except Exception:
                    text = ""
                return clean(value), text
        except Exception:
            pass
    return "", ""


async def phenom_select_yes_no(page, select_id, desired):
    """
    Select Yes/No using visible option text rather than opaque values.
    Returns (ok, chosen_text).
    """
    desired = normalize_yes_no(desired)
    if desired not in {"yes", "no"}:
        return False, ""

    wanted = "yes" if desired == "yes" else "no"

    for frame in await page_contexts(page):
        try:
            sel = frame.locator(f'[id="{select_id}"]').first
            if not await sel.count() or not await sel.is_visible():
                continue

            opts = sel.locator("option")
            for i in range(await opts.count()):
                opt = opts.nth(i)
                text = clean(await opt.inner_text())
                if text.lower() == wanted:
                    value = await opt.get_attribute("value")
                    if value:
                        await sel.select_option(value=value)
                    else:
                        await sel.select_option(label=text)
                    await page.wait_for_timeout(200)

                    current_value, current_text = await phenom_select_current(
                        page, select_id
                    )
                    if current_text.lower() == wanted:
                        return True, current_text
        except Exception:
            pass

    return False, ""


async def phenom_select_has_real_choice(page, select_id):
    value, text = await phenom_select_current(page, select_id)
    low = text.lower()
    if not text:
        return False, ""
    if any(x in low for x in [
        "please select", "select", "choose", "--"
    ]):
        return False, text
    return True, text


async def fill_phenom_city(page):
    if not PWC_CITY:
        return False
    for frame in await page_contexts(page):
        for sel in [
            '#cntryFields\\.city',
            'input[id="cntryFields.city"]',
            'input[autocomplete="address-level2"]',
            'input[aria-label="City"]',
        ]:
            try:
                loc = frame.locator(sel).first
                if await loc.count() and await loc.is_visible() and not await loc.is_disabled():
                    current = clean(await loc.input_value())
                    if not current:
                        await loc.fill(PWC_CITY)
                        await loc.press("Tab")
                    return True
            except Exception:
                pass
    return False


async def pwc_select_by_text(page, select_id, desired_text):
    """
    Select an option by its visible label using an exact id attribute selector.
    Works with PwC IDs containing dots.
    """
    if not desired_text:
        return False, ""

    for frame in await page_contexts(page):
        try:
            sel = frame.locator(f'[id="{select_id}"]').first
            if not await sel.count() or not await sel.is_visible():
                continue

            options = sel.locator("option")
            for i in range(await options.count()):
                opt = options.nth(i)
                text = clean(await opt.inner_text())
                if text.lower() == clean(desired_text).lower():
                    value = await opt.get_attribute("value")
                    if value:
                        await sel.select_option(value=value)
                    else:
                        await sel.select_option(label=text)
                    await page.wait_for_timeout(180)

                    try:
                        selected = clean(
                            await sel.locator("option:checked").first.inner_text()
                        )
                    except Exception:
                        selected = ""

                    if selected.lower() == text.lower():
                        return True, selected
        except Exception:
            pass

    return False, ""


async def fill_pwc_profile_preferences(page):
    """
    Fill stable PwC profile fields from explicit environment preferences.
    """
    states = {}

    worked = normalize_yes_no(PWC_WORKED_BEFORE)
    worked_label = "Yes" if worked == "yes" else "No" if worked == "no" else ""
    if worked_label:
        ok, selected = await pwc_select_by_text(
            page, "haveYouWorkedForPwc", worked_label
        )
        states["worked_before"] = selected if ok else ""
    else:
        states["worked_before"] = ""

    ok, selected = await pwc_select_by_text(
        page, "country", PWC_COUNTRY
    )
    states["country"] = selected if ok else ""

    # Phone country code often uses "Czechia (+420)".
    phone_country = ""
    for label in [
        f"{PWC_COUNTRY} (+420)",
        "Czechia (+420)",
        "Czech Republic (+420)",
    ]:
        ok, selected = await pwc_select_by_text(
            page, "phoneWidget.countryPhoneCode", label
        )
        if ok:
            phone_country = selected
            break
    states["phone_country"] = phone_country

    if PWC_GENDER:
        ok, selected = await pwc_select_by_text(
            page, "gender", PWC_GENDER
        )
        states["gender"] = selected if ok else ""
    else:
        states["gender"] = ""

    return states


async def read_pwc_profile_preferences(page):
    result = {}
    mapping = {
        "worked_before": "haveYouWorkedForPwc",
        "country": "country",
        "phone_country": "phoneWidget.countryPhoneCode",
        "gender": "gender",
    }
    for key, select_id in mapping.items():
        _, text = await phenom_select_current(page, select_id)
        result[key] = text
    return result


async def apply_configured_pwc_consents(page):
    """
    Apply only explicitly configured Yes/No values.
    Blank config means: do not choose for the user.
    """
    states = {}

    mapping = [
        (
            "future_recruitment",
            "jsqData.CEE_Job_Application_v2.a",
            PWC_FUTURE_RECRUITMENT_CONSENT,
        ),
        (
            "events",
            "jsqData.CEE_Job_Application_v2.b",
            PWC_EVENTS_CONSENT,
        ),
    ]

    for key, select_id, configured in mapping:
        normalized = normalize_yes_no(configured)

        if normalized:
            ok, text = await phenom_select_yes_no(
                page, select_id, normalized
            )
            states[key] = {
                "configured": normalized,
                "selected": text if ok else "",
                "ready": ok,
            }
        else:
            ready, text = await phenom_select_has_real_choice(
                page, select_id
            )
            states[key] = {
                "configured": "",
                "selected": text if ready else "",
                "ready": ready,
            }

    return states


async def wait_for_manual_pwc_consents(page):
    print("\n📝 TWO PWC CONSENT CHOICES ARE REQUIRED")
    print("   Please choose Yes or No for BOTH dropdowns under 'Application questions'.")
    print("   1) Keep my data for possible future PwC recruitment")
    print("   2) Receive PwC job/event communications")
    print("   Do NOT click Submit.")
    print("   v38 will detect both choices and continue automatically.")

    for _ in range(max(1, PWC_MANUAL_CHOICES_WAIT_SECONDS)):
        await page.wait_for_timeout(1000)

        a_ready, a_text = await phenom_select_has_real_choice(
            page, "jsqData.CEE_Job_Application_v2.a"
        )
        b_ready, b_text = await phenom_select_has_real_choice(
            page, "jsqData.CEE_Job_Application_v2.b"
        )

        if a_ready or b_ready:
            print(
                "   Detected choices: "
                f"future={a_text if a_ready else 'UNSET'}, "
                f"events={b_text if b_ready else 'UNSET'}"
            )

        if a_ready and b_ready:
            return {
                "future_recruitment": {
                    "configured": "",
                    "selected": a_text,
                    "ready": True,
                },
                "events": {
                    "configured": "",
                    "selected": b_text,
                    "ready": True,
                },
            }

    return {
        "future_recruitment": {
            "configured": "",
            "selected": "",
            "ready": False,
        },
        "events": {
            "configured": "",
            "selected": "",
            "ready": False,
        },
    }


async def applicant_acknowledgment_state(page):
    """
    Inspect the hidden PwC acknowledgment checkbox.
    We do NOT auto-check it here because final Submit itself is the legal
    acknowledgment shown on the page. This is diagnostic only.
    """
    for frame in await page_contexts(page):
        try:
            el = frame.locator("#applicantAcknowledgment").first
            if await el.count():
                return {
                    "present": True,
                    "checked": await el.is_checked(),
                    "required": (
                        await el.get_attribute("required") is not None
                        or (await el.get_attribute("aria-required") or "").lower() == "true"
                    ),
                }
        except Exception:
            pass
    return {"present": False, "checked": False, "required": False}


async def handle_phenom_apply(page):
    await wait_for_phenom_form(page)

    await save_stage_debug(
        page,
        "phenom_step1_before_debug.json",
        "phenom_step1_before_debug.png",
    )

    step = phenom_step_from_url(page.url)
    stepname = phenom_stepname_from_url(page.url)
    print(f"🧩 Phenom step: {step} | {stepname or '(no stepname)'}")

    # Set stable profile preferences before resume parsing.
    profile_states = await fill_pwc_profile_preferences(page)

    form = await fill_phenom_personal_information(page)

    # Resume parsing can rewrite some fields, so set them once more afterwards.
    profile_states = await fill_pwc_profile_preferences(page)
    await fill_phenom_city(page)

    profile_states = await read_pwc_profile_preferences(page)
    form["worked_before"] = profile_states.get("worked_before", "")
    form["country"] = profile_states.get("country", "")
    form["phone_country"] = profile_states.get("phone_country", "")
    form["gender"] = profile_states.get("gender", "")

    consent_states = await apply_configured_pwc_consents(page)

    # If either consent has no configured value and is still unselected,
    # wait for the user to choose it manually in the visible browser.
    if not all(v.get("ready") for v in consent_states.values()):
        consent_states = await wait_for_manual_pwc_consents(page)

    form["consent_future"] = (
        consent_states.get("future_recruitment", {}).get("selected", "")
    )
    form["consent_events"] = (
        consent_states.get("events", {}).get("selected", "")
    )

    ack = await applicant_acknowledgment_state(page)
    form["ack_present"] = ack["present"]
    form["ack_checked"] = ack["checked"]
    form["ack_required"] = ack["required"]

    await save_stage_debug(
        page,
        "phenom_step1_after_debug.json",
        "phenom_step1_after_debug.png",
    )

    core = ["first_name", "last_name", "email", "cv"]
    if form.get("phone_present"):
        core.append("phone")

    missing = [k for k in core if not form.get(k)]
    if missing:
        return (
            "PHENOM_PERSONAL_PARTIALLY_FILLED",
            "PwC/Phenom form reached; missing/invalid: "
            + ", ".join(missing)
            + ". See phenom_step1_after_debug.json/png",
            page.url,
            form,
        )

    profile_missing = []
    expected_worked = "Yes" if normalize_yes_no(PWC_WORKED_BEFORE) == "yes" else "No"
    if expected_worked and form.get("worked_before", "").lower() != expected_worked.lower():
        profile_missing.append("worked_before")
    if PWC_COUNTRY and form.get("country", "").lower() != PWC_COUNTRY.lower():
        profile_missing.append("country")
    if form.get("phone_present") and "+420" not in form.get("phone_country", ""):
        profile_missing.append("phone_country")

    if profile_missing:
        return (
            "PWC_PROFILE_FIELDS_REVIEW",
            "Core CV/contact data are ready, but PwC profile select(s) did not "
            "validate: " + ", ".join(profile_missing),
            page.url,
            form,
        )

    consent_missing = []
    if not form.get("consent_future"):
        consent_missing.append("future_recruitment_consent")
    if not form.get("consent_events"):
        consent_missing.append("events_consent")

    if consent_missing:
        return (
            "PWC_CONSENT_CHOICES_REQUIRED",
            "Core application data and CV are ready, but required PwC consent "
            "choice(s) are still unselected: "
            + ", ".join(consent_missing),
            page.url,
            form,
        )

    final_el, final_text = await phenom_find_final_submit(page)

    if final_el is None:
        return (
            "PHENOM_READY_NO_SUBMIT",
            "All known required PwC fields are ready, but final Submit was not detected.",
            page.url,
            form,
        )

    form["submit"] = True
    form["submit_text"] = final_text

    # Never submit unless BOTH global final gates are explicitly enabled.
    if AUTO_SUBMIT and CONFIRMATION_GATE:
        await final_el.click(timeout=10000)
        await page.wait_for_timeout(1500)
        return (
            "SUBMITTED",
            f"PwC/Phenom application submitted after double gate ({final_text})",
            page.url,
            form,
        )

    return (
        "READY_FOR_MANUAL_SUBMIT",
        f"PwC/Phenom form is complete; final Submit detected ({final_text}). "
        "Submission blocked by safety gate.",
        page.url,
        form,
    )


async def handle_workday(page):
    await save_stage_debug(page, "workday_debug.json", "workday_debug.png")

    # Login/account creation is deliberately manual.
    if await workday_login_like(page) and not await workday_application_like(page):
        ok = await workday_manual_bootstrap(page)
        await save_stage_debug(page, "workday_debug.json", "workday_debug.png")
        if not ok:
            return (
                "WORKDAY_LOGIN_REQUIRED",
                "Workday sign-in/account step was not completed within the wait window. "
                "See workday_debug.json/png",
                page.url,
                {
                    "stage": "workday",
                    "first_name": False, "last_name": False, "email": False,
                    "phone": False, "phone_present": False,
                    "phone_source": "", "cv": False,
                    "cv_source": "not_reached", "cover_letter": False,
                    "submit": False, "submit_text": "",
                },
            )

    resume_ok, resume_source = await try_workday_resume_start(page)
    await save_stage_debug(page, "workday_debug.json", "workday_debug.png")

    # v34 intentionally stops here instead of guessing multi-step Workday
    # questions/consents. The next adapter can be built from the real debug.
    return (
        "WORKDAY_REACHED",
        f"Workday application stage reached; resume_action={resume_source}. "
        "Final submission remains blocked. See workday_debug.json/png",
        page.url,
        {
            "stage": "workday",
            "first_name": False,
            "last_name": False,
            "email": False,
            "phone": False,
            "phone_present": False,
            "phone_source": "",
            "cv": resume_ok,
            "cv_source": resume_source,
            "cover_letter": False,
            "submit": False,
            "submit_text": "",
        },
    )


async def handle_external_application(page):
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    await page.wait_for_timeout(1000)

    await save_stage_debug(
        page,
        "external_application_debug.json",
        "external_application_debug.png",
    )

    # Explicit PwC job-detail adapter.
    if is_pwc_careers_url(page.url) and "/job/" in page.url.lower():
        page, reason = await click_current_pwc_apply(page)
        print(f"🟧 PwC Apply Now: {reason}")
        page, chain_reason = await follow_apply_chain(page)
        print(f"➡️ Apply destination: {page.url}")
        print(f"   Route: {chain_reason}")

        if is_workday_url(page.url):
            return await handle_workday(page)

        # Confirmed PwC flow: this is a Phenom application UI on the same PwC domain.
        if is_phenom_apply_url(page.url):
            return await handle_phenom_apply(page)

        await save_stage_debug(
            page,
            "external_apply_debug.json",
            "external_apply_debug.png",
        )

        for _ in range(20):
            await page.wait_for_timeout(500)
            if is_workday_url(page.url):
                return await handle_workday(page)
            if is_phenom_apply_url(page.url):
                return await handle_phenom_apply(page)

        return (
            "PWC_APPLY_REACHED",
            "PwC Apply endpoint reached, but neither Phenom nor Workday adapter matched. "
            "See external_apply_debug.json/png",
            page.url,
            {
                "stage": "pwc_apply",
                "first_name": False, "last_name": False, "email": False,
                "phone": False, "phone_present": False, "phone_source": "",
                "cv": False, "cv_source": "not_reached",
                "cover_letter": False, "submit": False, "submit_text": "",
            },
        )

    if is_workday_url(page.url):
        return await handle_workday(page)

    return (
        "EXTERNAL_ATS_REACHED",
        "External employer site reached, but no dedicated adapter matched. "
        "See external_application_debug.json/png",
        page.url,
        {
            "stage": "external_ats",
            "first_name": False, "last_name": False, "email": False,
            "phone": False, "phone_present": False, "phone_source": "",
            "cv": False, "cv_source": "not_reached",
            "cover_letter": False, "submit": False, "submit_text": "",
        },
    )


async def manual_submit_success_signal(page, original_url):
    """
    Conservative success detection after the user manually presses the
    employer's final Submit button.
    """
    current_url = page.url or ""

    try:
        body = clean(await page.locator("body").inner_text()).lower()
    except Exception:
        body = ""

    positive_phrases = [
        "thank you for applying",
        "thank you for your application",
        "application submitted",
        "application has been submitted",
        "application received",
        "we received your application",
        "your application has been received",
        "successfully submitted",
        "děkujeme za odpověď",
        "dekujeme za odpoved",
        "odpověď byla odeslána",
        "odpoved byla odeslana",
        "reakce byla odeslána",
        "reakce byla odeslana",
        "děkujeme za reakci",
        "dekujeme za reakci",
    ]

    if any(p in body for p in positive_phrases):
        return True, "confirmation_text"

    # A redirect away from the Phenom application form is another strong signal,
    # provided it isn't just a login/error route.
    if current_url != original_url:
        low = current_url.lower()
        if (
            "/apply?" not in low
            and "error" not in low
            and "login" not in low
            and "signin" not in low
        ):
            return True, "post_submit_redirect"

    return False, ""


async def hold_for_manual_final_submit(page, result):
    """
    When the application is fully prepared, keep Chromium open so the user can
    make the consequential final click themselves. Detect success and then
    allow the browser to close normally.
    """
    status, reason, current_url, form = result

    if status != "READY_FOR_MANUAL_SUBMIT" or not MANUAL_SUBMIT_HOLD:
        return result

    print("\n✅ APPLICATION IS FULLY READY")
    print("   Review the visible application form one last time.")
    print("   If everything is correct, click the orange Submit button yourself.")
    print("   v51 will detect the confirmation automatically.")
    print(f"   Waiting up to {MANUAL_SUBMIT_WAIT_SECONDS} seconds...")

    original_url = page.url

    for _ in range(max(1, MANUAL_SUBMIT_WAIT_SECONDS)):
        await page.wait_for_timeout(1000)

        ok, signal = await manual_submit_success_signal(page, original_url)
        if ok:
            print(f"✅ Manual submission detected: {signal}")
            return (
                "SUBMITTED_MANUALLY",
                f"Final Submit was clicked manually and submission confirmation was detected ({signal})",
                page.url,
                form,
            )

    return (
        "READY_FOR_MANUAL_SUBMIT",
        reason + f" Manual-submit wait expired after {MANUAL_SUBMIT_WAIT_SECONDS}s.",
        page.url,
        form,
    )


async def prepare_application(job):
    async with async_playwright() as p:
        profile_dir = resolve_browser_profile_dir()
        browser = await p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
            viewport={"width": 1440, "height": 1000},
        )
        page = await browser.new_page()

        try:
            known_external = None
            if job.get("source") == "jobs.cz":
                known_external = KNOWN_EXTERNAL_ROUTES.get(str(job.get("job_id", "")))
            if known_external:
                print(f"♻️ Resuming known external route without repeating Jobs.cz handoff:")
                print(f"   {known_external}")
                await page.goto(known_external, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1000)
                result = await handle_external_application(page)
                return await hold_for_manual_final_submit(page, result)

            await page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1200)

            if not job.get("company"):
                company, source = await extract_company_from_page(page)
                if company:
                    job["company"] = company
                    job["company_source"] = source

            # If login session is already valid, Jobs.cz may redirect /rpd -> /fp.
            # If the form is already present, do not require a second CTA click.
            if await looks_like_application_form(page):
                print("🧾 Application form already visible; continuing without CTA click.")
            else:
                active, click_reason = await click_application_control(page)
                if active is None:
                    debug = await collect_application_debug(page)

                    if str(click_reason).startswith("invalid_destination:"):
                        return (
                            "INVALID_APPLICATION_DESTINATION",
                            "Candidate CTA led to a page without application "
                            f"signals; form filling was blocked. {click_reason}",
                            page.url,
                            {
                                "debug_controls": sum(
                                    len(f.get("controls", []))
                                    for f in debug.get("frames", [])
                                )
                            },
                        )

                    return (
                        "NEEDS_MANUAL_REVIEW",
                        "Application control not found on source portal; "
                        "debug saved to application_debug.json/png",
                        page.url,
                        {
                            "debug_controls": sum(
                                len(f.get("controls", []))
                                for f in debug.get("frames", [])
                            )
                        },
                    )
                page = active
                await page.wait_for_timeout(1000)

            # Login bootstrap can happen after clicking the response CTA.
            if is_login_url(page.url):
                logged_page = await bootstrap_login(page, job["url"])
                if logged_page is None:
                    return (
                        "LOGIN_REQUIRED",
                        "Login was not completed; persistent profile remains available",
                        page.url,
                        {},
                    )
                page = logged_page

                # Jobs.cz currently may land on an /fp/<employer>/<job>/ route after login.
                # Re-evaluate company and application state on that exact page.
                company, source = await extract_company_from_page(page)
                if company:
                    job["company"] = company
                    job["company_source"] = source

                if not await looks_like_application_form(page):
                    active, click_reason = await click_application_control(page)
                    if active is None:
                        # One deterministic retry via original job URL. This covers
                        # auth flows where the return URL is lost during sign-in.
                        try:
                            await page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
                            await page.wait_for_timeout(1000)
                        except Exception:
                            pass

                        company, source = await extract_company_from_page(page)
                        if company:
                            job["company"] = company
                            job["company_source"] = source

                        if not await looks_like_application_form(page):
                            active, click_reason = await click_application_control(page)

                    if active is None:
                        debug = await collect_application_debug(page)

                        if str(click_reason).startswith("invalid_destination:"):
                            return (
                                "INVALID_APPLICATION_DESTINATION",
                                "After login, candidate CTA led to a non-"
                                f"application destination. {click_reason}",
                                page.url,
                                {
                                    "debug_controls": sum(
                                        len(f.get("controls", []))
                                        for f in debug.get("frames", [])
                                    )
                                },
                            )

                        return (
                            "NEEDS_MANUAL_REVIEW",
                            "Logged in, but source-portal application CTA/form "
                            "still not detected; debug saved",
                            page.url,
                            {
                                "debug_controls": sum(
                                    len(f.get("controls", []))
                                    for f in debug.get("frames", [])
                                )
                            },
                        )
                    page = active
                    await page.wait_for_timeout(1000)

            if is_login_url(page.url):
                return "LOGIN_REQUIRED", "Login redirect persisted", page.url, {}

            low = page.url.lower()
            if "/zivotopis" in low and not await looks_like_application_form(page):
                return "PROFILE_REQUIRED", "Jobs.cz profile/CV flow opened", page.url, {}

            # Jobs.cz /externi-jof/ is an intermediate handoff, not the employer CV form.
            if await is_jobs_handoff_page(page):
                handoff = await inspect_jobs_handoff(page)

                handoff_missing = [
                    k for k in ["first_name", "last_name", "email"]
                    if not handoff.get(k)
                ]
                if handoff_missing:
                    await collect_application_debug(page)
                    return (
                        "JOBS_HANDOFF_PARTIALLY_FILLED",
                        "Jobs.cz handoff missing/invalid: " + ", ".join(handoff_missing),
                        page.url,
                        handoff,
                    )

                if not handoff.get("submit"):
                    await collect_application_debug(page)
                    return (
                        "JOBS_HANDOFF_NO_CONTINUE",
                        "Jobs.cz handoff is filled, but 'Pokračovat v odpovědi' was not detected",
                        page.url,
                        handoff,
                    )

                if not ALLOW_JOBS_HANDOFF:
                    return (
                        "PRE_APPLY_CONFIRMATION_REQUIRED",
                        "Jobs.cz 'Pokračovat v odpovědi' may create a preliminary employer application. "
                        "Set ALLOW_JOBS_HANDOFF=true only when you intentionally want to proceed.",
                        page.url,
                        handoff,
                    )

                print("➡️ Jobs.cz handoff explicitly allowed — continuing to employer ATS...")
                external_page, handoff_reason = await click_jobs_handoff(page)
                if external_page is None:
                    return (
                        "JOBS_HANDOFF_FAILED",
                        handoff_reason,
                        page.url,
                        handoff,
                    )

                page = external_page
                print(f"🌐 Employer/ATS destination: {page.url}")
                result = await handle_external_application(page)
                return await hold_for_manual_final_submit(page, result)

            form = await inspect_form(page, job)

            if is_resume_profile_url(page.url):
                await collect_application_debug(page)
                return (
                    "CV_UPLOAD_NAVIGATION_BLOCKED",
                    "Résumé/profile navigation was detected and was not treated as CV upload",
                    page.url,
                    form,
                )

            core_fields = ["first_name", "last_name", "email", "cv"]
            if form.get("phone_present"):
                core_fields.append("phone")

            missing = [k for k in core_fields if not form.get(k)]
            if missing:
                await collect_application_debug(page)

                if missing == ["cv"]:
                    return (
                        "CV_ATTACHMENT_REQUIRED",
                        "Form is otherwise ready, but CV attachment was not detected automatically or during the bounded manual fallback",
                        page.url,
                        form,
                    )

                return (
                    "FORM_PARTIALLY_FILLED",
                    "Missing/invalid: " + ", ".join(missing),
                    page.url,
                    form,
                )

            if not form["submit"]:
                await collect_application_debug(page)
                return (
                    "FORM_READY_NO_SUBMIT_CONTROL",
                    "Core form valid; submit control not detected",
                    page.url,
                    form,
                )

            if AUTO_SUBMIT and CONFIRMATION_GATE:
                # Find the same submit control across all frames and click only
                # after both explicit safety gates are enabled.
                for frame in await page_contexts(page):
                    for sel in [
                        'button:has-text("ODESLAT")',
                        'button:has-text("Odeslat")',
                        'button:has-text("Poslat")',
                        'input[type="submit"]',
                        'button[type="submit"]',
                    ]:
                        try:
                            loc = frame.locator(sel).first
                            if await loc.count() and await loc.is_visible():
                                await loc.click(timeout=10000)
                                await page.wait_for_timeout(1500)
                                return "SUBMITTED", "Submitted after double gate", page.url, form
                        except Exception:
                            pass
                return "FORM_READY_NO_SUBMIT_CONTROL", "Submit vanished before click", page.url, form

            result = (
                "READY_FOR_MANUAL_SUBMIT",
                f"Submit detected ({form['submit_text'] or 'submit'}); submission blocked by safety gate",
                page.url,
                form,
            )
            return await hold_for_manual_final_submit(page, result)

        finally:
            await browser.close()

TERMINAL_SUCCESS_STATUSES = {
    "SUBMITTED",
    "SUBMITTED_MANUALLY",
    "APPLICATION_CONFIRMED",
}

USER_INTERVENTION_STATUSES = {
    "READY_FOR_MANUAL_SUBMIT",
    "PWC_CONSENT_CHOICES_REQUIRED",
    "WORKDAY_LOGIN_REQUIRED",
    "LOGIN_REQUIRED",
    "PRE_APPLY_CONFIRMATION_REQUIRED",
}


def should_continue_after_application(status):
    if status in TERMINAL_SUCCESS_STATUSES:
        return True
    if status in USER_INTERVENTION_STATUSES:
        return False
    return CONTINUE_AFTER_APPLICATION_ERROR


def print_application_result(index, total, target, status, reason, current_url, form):
    print("\n" + "=" * 72)
    print(f"APPLICATION RESULT {index}/{total}")
    print("=" * 72)
    print(f"Source: {target.get('source') or source_from_url(target.get('url', ''))}")
    print(f"Position: {target.get('actual_title') or target['title']}")
    print(f"Company: {target.get('company') or '(not detected)'}")
    print(
        "Location: "
        f"{target.get('resolved_location') or target.get('location') or '(unknown)'}"
    )
    print(f"Location gate: {target.get('location_gate', 'not_checked')}")
    print(f"Company source: {target.get('company_source') or 'not_detected'}")
    print(f"Job ID: {target['job_id']}")
    print(f"URL: {target['url']}")
    print(f"Decision: {target['decision']}")
    print(f"Match score: {target['score']}/100")
    print(
        f"Evidence: {target['evidence_quality']} "
        f"(source={target.get('evidence_source', 'http')}, "
        f"length={target.get('evidence_length', len(target.get('description', '')))})"
    )
    print(f"Application status: {status}")
    print(f"Reason: {reason}")

    if form:
        if form.get("stage"):
            print(f"Stage: {form.get('stage')}")

        if "worked_before" in form or "country" in form:
            print(
                "PwC profile: "
                f"worked_before={form.get('worked_before') or 'UNSET'}, "
                f"country={form.get('country') or 'UNSET'}, "
                f"city={PWC_CITY or '(blank)'}, "
                f"phone_country={form.get('phone_country') or 'UNSET'}, "
                f"gender={form.get('gender') or 'UNSET'}"
            )

        if "consent_future" in form or "consent_events" in form:
            print(
                "PwC choices: "
                f"future_recruitment={form.get('consent_future') or 'UNSET'}, "
                f"events={form.get('consent_events') or 'UNSET'}, "
                f"ack_present={'YES' if form.get('ack_present') else 'NO'}, "
                f"ack_checked={'YES' if form.get('ack_checked') else 'NO'}"
            )

        print(
            "Form: "
            f"first_name={'YES' if form.get('first_name') else 'NO'}"
            f"[{clean(form.get('first_name_source', ''))[:80] or '-'}], "
            f"last_name={'YES' if form.get('last_name') else 'NO'}"
            f"[{clean(form.get('last_name_source', ''))[:80] or '-'}], "
            f"email={'YES' if form.get('email') else 'NO'}, "
            f"phone={'YES' if form.get('phone') else 'NO'}"
            f"[{form.get('phone_source') or '-'};present="
            f"{'YES' if form.get('phone_present') else 'NO'}], "
            f"cv={'YES' if form.get('cv') else 'NO'}"
            f"[{form.get('cv_source') or '-'}], "
            f"cover_letter={'YES' if form.get('cover_letter') else 'NO'}"
            f"[lang={form.get('cover_letter_language') or '-'};"
            f"source={form.get('cover_letter_source') or '-'};"
            f"chars={form.get('cover_letter_chars', 0)}], "
            f"submit={'YES' if form.get('submit') else 'NO'}"
        )

    print(f"Current URL: {current_url}")


async def main():
    print("🚀 Starting Job Agent v52 — broader data-role discovery")
    print(f"📄 CV: {Path(CV_PATH).resolve()}")
    print(f"📨 AUTO_SUBMIT: {AUTO_SUBMIT}")
    print(f"🔐 CONFIRMATION_GATE: {CONFIRMATION_GATE}")
    print(f"🧭 ALLOW_JOBS_HANDOFF: {ALLOW_JOBS_HANDOFF}")
    print(f"🧑‍💻 WORKDAY_MANUAL_BOOTSTRAP: {WORKDAY_MANUAL_BOOTSTRAP}")
    print("📝 PWC consent prefs: "
          f"future={PWC_FUTURE_RECRUITMENT_CONSENT or 'ASK'}, "
          f"events={PWC_EVENTS_CONSENT or 'ASK'}")
    print("👤 PWC profile prefs: "
          f"worked_before={PWC_WORKED_BEFORE or 'ASK'}, "
          f"country={PWC_COUNTRY or 'ASK'}, "
          f"city={PWC_CITY or '(blank)'}, "
          f"gender={PWC_GENDER or 'ASK'}")
    print(f"🔑 LOGIN_BOOTSTRAP: {LOGIN_BOOTSTRAP}")
    print(f"📎 MANUAL_CV_FALLBACK: {MANUAL_CV_FALLBACK}")
    print(f"🛑 MANUAL_SUBMIT_HOLD: {MANUAL_SUBMIT_HOLD} ({MANUAL_SUBMIT_WAIT_SECONDS}s)")
    print(f"💾 STATE_DIR: {STATE_DIR}")
    print(
        f"🎯 APPLY >= {MIN_APPLY_SCORE} | "
        f"VERIFIED TARGET >= {VERIFIED_TARGET_APPLY_SCORE} | "
        f"ENTRY APPLY >= {ENTRY_APPLY_SCORE} | "
        f"EXPANDED APPLY >= {EXPANDED_APPLY_SCORE} | "
        f"REVIEW >= {MIN_REVIEW_SCORE}"
    )
    print(
        f"📬 Applications/run: max={MAX_APPLICATIONS_PER_RUN} | "
        f"continue_after_error={CONTINUE_AFTER_APPLICATION_ERROR}"
    )
    print(
        f"🧠 Browser evidence recovery: {BROWSER_EVIDENCE_RECOVERY} | "
        f"levels={sorted(BROWSER_EVIDENCE_LEVELS)} | "
        f"max={MAX_BROWSER_EVIDENCE_JOBS}"
    )
    print(
        f"🛡️ Strict application CTA validation: "
        f"{STRICT_APPLICATION_ROUTE_VALIDATION}"
    )
    print(
        f"✉️ Czech cover letter: {AUTO_CZECH_COVER_LETTER} | "
        f"language={COVER_LETTER_LANGUAGE} | "
        f"max_chars={COVER_LETTER_MAX_CHARS}"
    )
    print(
        f"🧭 Microsite CTA retry: retries={MICROSITE_CTA_RETRIES} | "
        f"wait_ms={MICROSITE_CTA_WAIT_MS} | "
        f"same_host_reply_fallback={ALLOW_SAME_HOST_REPLY_FALLBACK}"
    )
    print(f"🌐 Sources: Jobs.cz={SOURCE_JOBS_CZ} | Prace.cz={SOURCE_PRACE_CZ}")
    print(
        f"📍 Location gate: mode={LOCATION_MODE} | "
        f"remote_outside_prague={ALLOW_FULL_REMOTE_OUTSIDE_PRAGUE}"
    )

    if not Path(CV_PATH).exists():
        raise FileNotFoundError(CV_PATH)

    processed = load_processed()
    print(f"🗂️ Previously processed: {len(processed)} job(s)")

    session = requests.Session()
    jobs = discover_all(session)
    print(f"🔗 Combined discovery before enrichment/dedup: {len(jobs)} candidate(s)")

    print("\n🔍 DISCOVERY PRIORITY PREVIEW")
    for i, job in enumerate(jobs[:14], 1):
        print(
            f"{i}. [{job.get('source')}] "
            f"{job.get('actual_title') or job.get('title')} | "
            f"{job.get('company') or '(company pending)'} | "
            f"priority={discovery_priority(job)}"
        )

    fresh = [
        j for j in jobs
        if canonical_history_key(j) not in processed
    ][:MAX_JOBS_TO_REVIEW * 3]

    enriched = []
    for job in fresh:
        job = enrich_job(job, session)
        enriched.append(job)

    # Second pass for promising target vacancies that were weak over plain HTTP.
    # This pass is read-only: no application controls are clicked.
    enriched = await browser_recover_weak_evidence(enriched)

    # Cross-site semantic dedup: same normalized employer + title + location.
    # Prefer Jobs.cz when the same vacancy appears on both portals because its
    # adapter is more mature; otherwise keep the higher-evidence record.
    groups = {}
    for job in enriched:
        key = dedupe_key(job)
        groups.setdefault(key, []).append(job)

    deduped = []
    duplicate_groups = 0
    for key, group in groups.items():
        if len(group) > 1:
            duplicate_groups += 1

        group.sort(
            key=lambda j: (
                j.get("source") != "jobs.cz",
                {"strong": 0, "medium": 1, "weak": 2}.get(j.get("evidence_quality"), 3),
            )
        )
        keep = group[0]
        keep["duplicate_sources"] = sorted({
            g.get("source", "") for g in group if g.get("source")
        })
        deduped.append(keep)

    print(
        f"🔗 Cross-site deduplication: {len(enriched)} → {len(deduped)} "
        f"({duplicate_groups} duplicate group(s))"
    )

    ranked = []
    job_overrides = load_job_overrides()
    for job in deduped[:MAX_JOBS_TO_REVIEW]:
        if (
            job.get("source") == "jobs.cz"
            and not job.get("company")
            and str(job.get("job_id", "")) in KNOWN_COMPANIES
        ):
            job["company"] = KNOWN_COMPANIES[str(job.get("job_id", ""))]
        result = score_job(job)

        loc_allowed, loc_reason, resolved_location = location_gate(job)
        job["location_gate"] = loc_reason
        job["resolved_location"] = resolved_location

        if loc_allowed is False:
            result["decision"] = "SKIP"
            result["score"] = min(result["score"], 20)
            result.setdefault("reasons", []).append(
                f"location_gate:{loc_reason}"
            )
        elif loc_allowed is None and result["decision"] == "APPLY":
            result["decision"] = "REVIEW"
            result["score"] = min(result["score"], MIN_APPLY_SCORE - 1)
            result.setdefault("reasons", []).append(
                "location_gate:unknown_location"
            )

        job.update(result)

        override = job_overrides.get(canonical_history_key(job), {})
        override_decision = str(override.get("decision", "")).upper().strip()
        if override_decision == "SKIP":
            job["decision"] = "SKIP"
            job.setdefault("reasons", []).append("desktop_override:SKIP")
        elif override_decision == "REVIEW":
            job["decision"] = "REVIEW"
            job.setdefault("reasons", []).append("desktop_override:REVIEW")
        elif override_decision == "INTERESTING":
            job.setdefault("reasons", []).append("desktop_override:INTERESTING")

        ranked.append(job)

    ranked.sort(key=lambda j: (-j["score"], j["decision"] != "APPLY"))

    Path("jobs.json").write_text(
        json.dumps(ranked, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n🏆 DECISION RANKING")
    for i, job in enumerate(ranked, 1):
        print(
            f"{i}. [{job.get('source')}] [{job['job_id']}] "
            f"{job.get('actual_title') or job['title']} | "
            f"{job.get('company') or '(company not detected)'} | "
            f"{job.get('resolved_location') or job.get('location') or '(location unknown)'} | "
            f"{job.get('role_class')} | {job.get('decision')} | "
            f"{job.get('score')}/100 | "
            f"evidence={job.get('evidence_quality')}/{job.get('evidence_source', 'http')} | "
            f"verified={'YES' if job.get('verified_target_promotion') else 'NO'} | "
            f"expanded_signals={','.join(job.get('expanded_signals', [])) if job.get('expanded_signals') else '-'}"
        )

    apply_candidates = [
        j for j in ranked
        if j["decision"] == "APPLY"
    ]

    # Save non-APPLY observations. load_processed() only treats confirmed
    # submissions as terminal, so REVIEW/SKIP jobs can be reconsidered later.
    for job in ranked:
        if job["decision"] == "APPLY":
            continue
        status = "SKIPPED" if job["decision"] == "SKIP" else "REVIEW_PENDING"
        save_status(
            job,
            status,
            job["score"],
            "; ".join(job.get("reasons", [])[:12]),
        )

    if not apply_candidates:
        print("\n❌ No target role currently qualifies for APPLY.")
        return

    queue = apply_candidates[:MAX_APPLICATIONS_PER_RUN]

    print(
        f"\n📬 APPLICATION QUEUE: {len(queue)} of "
        f"{len(apply_candidates)} APPLY candidate(s)"
    )
    for i, job in enumerate(queue, 1):
        print(
            f"{i}. [{job.get('source')}] "
            f"{job.get('actual_title') or job['title']} | "
            f"{job.get('company') or '(company not detected)'} | "
            f"{job.get('resolved_location') or job.get('location') or '(location unknown)'} | "
            f"{job['score']}/100 | "
            f"evidence={job.get('evidence_quality')}/{job.get('evidence_source', 'http')}"
        )

    run_results = []
    submitted_count = 0

    for index, target in enumerate(queue, 1):
        print("\n" + "#" * 72)
        print(f"APPLICATION {index}/{len(queue)}")
        print("#" * 72)
        print(
            f"🎯 [{target.get('source')}] [{target['job_id']}] "
            f"{target.get('actual_title') or target['title']} | "
            f"{target.get('company') or '(company not detected)'} | "
            f"{target.get('resolved_location') or target.get('location') or '(location unknown)'} | "
            f"{target['score']}/100 | evidence={target['evidence_quality']}"
        )

        try:
            status, reason, current_url, form = await prepare_application(target)
        except Exception as exc:
            status = "APPLICATION_ERROR"
            reason = f"{type(exc).__name__}: {exc}"
            current_url = target.get("url", "")
            form = {}

        save_status(target, status, target["score"], reason)

        if status in TERMINAL_SUCCESS_STATUSES:
            submitted_count += 1

        result_record = {
            "target": target,
            "status": status,
            "reason": reason,
            "current_url": current_url,
            "form": form,
        }
        run_results.append(result_record)

        print_application_result(
            index,
            len(queue),
            target,
            status,
            reason,
            current_url,
            form,
        )

        if index < len(queue):
            if should_continue_after_application(status):
                print(
                    f"\n➡️ Continuing to next APPLY candidate "
                    f"({index + 1}/{len(queue)})..."
                )
            else:
                print(
                    "\n🛑 Queue paused because this application still needs "
                    "your intervention."
                )
                break

    print("\n" + "=" * 72)
    print("RUN SUMMARY")
    print("=" * 72)
    print(f"Queued APPLY candidates: {len(queue)}")
    print(f"Attempted this run: {len(run_results)}")
    print(f"Confirmed submissions: {submitted_count}")

    for i, result in enumerate(run_results, 1):
        target = result["target"]
        print(
            f"{i}. {target.get('actual_title') or target['title']} | "
            f"{target.get('company') or '(company not detected)'} | "
            f"{result['status']}"
        )

    remaining = max(0, len(apply_candidates) - len(run_results))
    if remaining:
        print(f"Remaining APPLY candidates for a later run: {remaining}")

if __name__ == "__main__":
    asyncio.run(main())
