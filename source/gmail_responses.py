"""Optional read-only Gmail review for user-confirmed Job Agent applications.

The ChatGPT Gmail connector is unrelated to this local desktop authorization.
Only OAuth scope gmail.readonly is requested; credentials live in OS keyring,
not in the repository, settings JSON, application history, or logs.
"""
import json
import re
from pathlib import Path

SCOPES = ("https://www.googleapis.com/auth/gmail.readonly",)
KEYRING_SERVICE = "Job Agent Gmail read-only"
KEYRING_USER = "personal-account-v1"
MAX_MESSAGES = 40
STOP_WORDS = {
    "a", "an", "and", "the", "for", "of", "in", "to", "at", "with",
    "as", "na", "a", "pro", "v", "ve", "se", "do", "s", "z", "i",
    "junior", "senior", "specialist", "specialista", "specialistka",
}


def validate_client_file(path):
    """Require a locally selected Google Desktop OAuth JSON, never a service key."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise ValueError("Выберите локальный Google OAuth JSON для Desktop app.")
    if p.stat().st_size > 100_000:
        raise ValueError("OAuth JSON слишком большой.")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Невозможно прочитать Google OAuth JSON.") from exc
    entry = data.get("installed") if isinstance(data, dict) else None
    if not isinstance(entry, dict) or not all(
        isinstance(entry.get(k), str) and entry[k]
        for k in ("client_id", "client_secret", "auth_uri", "token_uri")
    ):
        raise ValueError("Нужен OAuth client типа Desktop app, не service account.")
    if entry["auth_uri"] != "https://accounts.google.com/o/oauth2/auth" and entry["auth_uri"] != "https://accounts.google.com/o/oauth2/v2/auth":
        raise ValueError("Недопустимый адрес Google OAuth.")
    if entry["token_uri"] != "https://oauth2.googleapis.com/token":
        raise ValueError("Недопустимый адрес выдачи токена.")
    return str(p)


def _keyring():
    import keyring
    return keyring


def is_connected():
    """Keychain metadata check only; does not open Gmail or refresh tokens."""
    try:
        return bool(_keyring().get_password(KEYRING_SERVICE, KEYRING_USER))
    except Exception:
        return False


def authorize(path):
    """User-initiated Google browser consent; only the Keychain stores tokens."""
    validated = validate_client_file(path)
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(validated, list(SCOPES))
    credentials = flow.run_local_server(
        host="localhost", port=0, open_browser=True, timeout_seconds=180,
        authorization_prompt_message="Разрешите только чтение Gmail в браузере: {url}",
    )
    if not credentials or not credentials.valid:
        raise RuntimeError("Google не подтвердил доступ к Gmail.")
    _keyring().set_password(KEYRING_SERVICE, KEYRING_USER, credentials.to_json())
    return True


def disconnect():
    """Discard local tokens; report keyring errors instead of claiming removal."""
    import keyring.errors
    try:
        _keyring().delete_password(KEYRING_SERVICE, KEYRING_USER)
    except keyring.errors.PasswordDeleteError:
        return False  # Nothing stored.
    return True


def _credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    raw = _keyring().get_password(KEYRING_SERVICE, KEYRING_USER)
    if not raw:
        raise RuntimeError("Сначала подключите Gmail в настройках Job Agent.")
    try:
        credentials = Credentials.from_authorized_user_info(json.loads(raw), list(SCOPES))
        if not credentials.valid and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            _keyring().set_password(KEYRING_SERVICE, KEYRING_USER, credentials.to_json())
    except Exception as exc:
        raise RuntimeError("Доступ Gmail истёк. Подключите аккаунт заново.") from exc
    if not credentials.valid:
        raise RuntimeError("Доступ Gmail истёк. Подключите аккаунт заново.")
    return credentials


def _norm(value):
    """Casefold and drop punctuation while keeping Czech and other Unicode text."""
    return " ".join(re.findall(r"[^\W_]+", str(value or "").casefold(), re.UNICODE))


def _title_tokens(value):
    return [token for token in _norm(value).split() if token not in STOP_WORDS and len(token) >= 3]


def _has_phrase(haystack, phrase):
    return bool(phrase) and f" {phrase} " in f" {haystack} "


def _canonical_id(record):
    """Do not merge ids from unrelated job boards by digits alone."""
    raw = str(record.get("job_id", "")).strip()
    if raw.startswith(("jobs.cz:", "prace.cz:")) and raw.rsplit(":", 1)[-1].isdigit():
        return "job:" + raw.rsplit(":", 1)[-1]
    if raw.isdigit():
        return "job:" + raw
    return raw


# Conservative, advisory-only classifications: never assign recruiter stage here.
# Message subject and short Gmail snippet are incomplete and sometimes misleading.
REPLY_LABELS = {
    "RECEIPT": "Автоподтверждение получения",
    "INTERVIEW": "Возможное приглашение на интервью",
    "REJECTION": "Возможный отказ",
    "RESULT": "Результат отбора — проверь письмо",
    "OTHER": "Требуется ручная проверка",
}


def classify_reply(subject, snippet):
    """Show an uncertain suggestion, not an employer-confirmed outcome."""
    title = _norm(subject)
    message = _norm(" ".join((subject, snippet)))
    receipt = (
        "zařadili jsme vás do výběrového řízení",
        "zaradili jsme vas do vyberoveho rizeni",
        "děkujeme za projevený zájem",
        "dekujeme za projeveny zajem",
        "many thanks for your cv",
        "thank you for your application",
        "application received",
        "we have received your application",
        "potvrzení přijetí",
    )
    interview = (
        "pozvánka na pohovor", "pozvanka na pohovor",
        "pozvání na pohovor", "pozvani na pohovor",
        "rádi bychom vás pozvali", "radi bychom vas pozvali",
        "interview invitation", "invite you to an interview",
        "invitation to interview",
    )
    rejection = (
        "bohužel jste nebyl", "bohužel jste nebyla",
        "bohuzel jste nebyl", "bohuzel jste nebyla",
        "rozhodli jsme se dát přednost", "rozhodli jsme se dat prednost",
        "nepostupujete do dalšího kola", "nepostupujete do dalsiho kola",
        "we regret to inform", "unfortunately you were not selected",
        "we will not be moving forward", "we have decided not to proceed",
    )
    # Avoid declaring rejection from generic 'Výsledek výběrového řízení'.
    result = ("výsledek výběrového řízení", "vysledek vyberoveho rizeni",
              "recruitment result", "výsledek pohovoru")
    if any(_has_phrase(message, p) for p in rejection):
        return "REJECTION"
    if any(_has_phrase(message, p) for p in interview):
        return "INTERVIEW"
    if any(_has_phrase(message, p) for p in receipt):
        return "RECEIPT"
    if any(_has_phrase(title, p) for p in result):
        return "RESULT"
    return "OTHER"


def _candidate(message, records, submitted):
    headers = {
        str(h.get("name", "")).lower(): str(h.get("value", ""))
        for h in message.get("payload", {}).get("headers", [])
        if isinstance(h, dict)
    }
    subject = headers.get("subject", "")[:250]
    sender = headers.get("from", "")[:250]
    snippet = str(message.get("snippet", ""))[:500]
    combined = _norm(" ".join((subject, sender, snippet)))
    text = " ".join((subject, snippet))
    matches = []
    for record in records:
        jid = _canonical_id(record)
        if not jid or jid not in submitted:
            continue
        numeric_id = jid.split(":", 1)[-1] if jid.startswith("job:") else ""
        # A >=7-digit posting id is distinctive and must appear as a whole token.
        id_match = (
            len(numeric_id) >= 7 and numeric_id.isdigit()
            and bool(re.search(r"(?<!\d)" + re.escape(numeric_id) + r"(?!\d)", text))
        )
        company = _norm(record.get("company", ""))
        title = _norm(record.get("title", ""))
        useful_title = _title_tokens(title)
        title_match = (
            len(useful_title) >= 2
            and all(_has_phrase(combined, token) for token in useful_title[:5])
        )
        company_match = (
            len(company) >= 4 and company not in {
                "unknown", "company not detected", "компания не определена",
            } and _has_phrase(combined, company)
        )
        if id_match or (title_match and company_match):
            matches.append((jid, "ID вакансии" if id_match else "Компания и название"))
    # Ambiguous messages are never assigned to a job automatically.
    unique_matches = {jid: reason for jid, reason in matches}
    if len(unique_matches) != 1:
        return None
    jid, reason = next(iter(unique_matches.items()))
    record = next((r for r in records if _canonical_id(r) == jid), {})
    category = classify_reply(subject, snippet)
    return {
        "job_id": jid,
        "job_title": str(record.get("title") or jid)[:250],
        "job_company": str(record.get("company") or "Компания не определена")[:250],
        "category": category,
        "category_label": REPLY_LABELS[category],
        "message_id": str(message.get("id", "")),
        "thread_id": str(message.get("threadId", "")),
        "subject": subject,
        "sender": sender,
        "snippet": snippet,
        "reason": reason,
    }


def suggest_matches(messages, records, submitted_ids):
    """Suggest likely matches without changing stages, dates or applications.csv."""
    submitted = {str(j) for j in submitted_ids}
    rows, seen = [], set()
    for message in messages:
        if not isinstance(message, dict):
            continue
        row = _candidate(message, records, submitted)
        if row and row["message_id"] and (row["job_id"], row["thread_id"]) not in seen:
            seen.add((row["job_id"], row["thread_id"]))
            rows.append(row)
    return rows


def scan(records, submitted_ids, limit=MAX_MESSAGES):
    """Explicit read-only check; downloads only message headers and snippets."""
    from googleapiclient.discovery import build
    credentials = _credentials()
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    limit = max(1, min(MAX_MESSAGES, int(limit)))
    page = service.users().messages().list(
        userId="me", q="newer_than:90d -in:sent",
        maxResults=limit, includeSpamTrash=False,
    ).execute()
    messages = []
    for message_ref in (page.get("messages") or [])[:limit]:
        mid = str(message_ref.get("id", ""))
        if not mid:
            continue
        message = service.users().messages().get(
            userId="me", id=mid, format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        messages.append(message)
    return suggest_matches(messages, records, submitted_ids)
