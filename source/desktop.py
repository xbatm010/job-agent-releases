import csv
import shutil
import tempfile
from datetime import datetime, timedelta
from html import escape
from desktop_theme import LIGHT_STYLE, DECISION_LABELS, display_decision
from desktop_widgets import VacancyDelegate, VacancyDetail, icon_pixmap, ui_icon, SOURCE_NAMES
import io
import json
import multiprocessing as mp
import os
import queue
import signal
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal, QThread, QObject, Slot, QUrl, QSize
from PySide6.QtGui import QColor, QPalette, QTextCursor, QFont, QFontDatabase, QDesktopServices, QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QComboBox,
    QProgressBar,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QHeaderView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "Job Agent"
DEFAULT_UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/xbatm010/job-agent-releases/main/manifest.json"

PLAYWRIGHT_BROWSERS_DIR = Path.home() / "Library" / "Caches" / "ms-playwright"
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(PLAYWRIGHT_BROWSERS_DIR)


def playwright_browser_present() -> bool:
    """
    Playwright installs revisioned browser directories such as:
      chromium-1243/
      chromium_headless_shell-1243/
    We only require at least one Chromium-family directory to exist.
    """
    try:
        if not PLAYWRIGHT_BROWSERS_DIR.exists():
            return False
        for child in PLAYWRIGHT_BROWSERS_DIR.iterdir():
            name = child.name.lower()
            if child.is_dir() and (
                name.startswith("chromium-")
                or name.startswith("chromium_headless_shell-")
            ):
                return True
    except Exception:
        return False
    return False


def playwright_install_command() -> str:
    return (
        f'PLAYWRIGHT_BROWSERS_PATH="{PLAYWRIGHT_BROWSERS_DIR}" '
        "python -m playwright install chromium"
    )


def load_version_info():
    try:
        p = resource_path("version.json")
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"app_name": "Job Agent Desktop", "version": "2.9.1", "channel": "beta"}

VERSION_INFO = None
APP_VERSION = "2.9.1"
TERMINAL_STATUSES = {
    "SUBMITTED",
    "SUBMITTED_MANUALLY",
    "APPLICATION_CONFIRMED",
}


def app_support_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.getenv("APPDATA", str(Path.home())))
    else:
        base = Path.home() / ".local" / "share"
    p = base / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


APP_DIR = app_support_dir()
SETTINGS_FILE = APP_DIR / "settings.json"
RUNTIME_DIR = APP_DIR / "runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_PROFILE_DIR = APP_DIR / "browser_profile"
HISTORY_FILE = Path.home() / ".job_agent" / "applications.csv"
VACANCIES_FILE = Path.home() / ".job_agent" / "vacancies.jsonl"
OVERRIDES_FILE = Path.home() / ".job_agent" / "job_overrides.json"


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def brand_pixmap(size: int = 64) -> QPixmap:
    """Render the bundled SVG brand icon safely at runtime."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    path = resource_path("assets/job_agent_icon.svg")
    if not path.exists():
        return pixmap

    try:
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            return pixmap
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
    except Exception:
        pass
    return pixmap


VERSION_INFO = load_version_info()
APP_VERSION = str(VERSION_INFO.get("version", "2.0.0"))
APP_CHANNEL = str(VERSION_INFO.get("channel", "stable")).strip().lower()
if APP_CHANNEL not in {"stable", "beta"}:
    APP_CHANNEL = "stable"

def detect_legacy_profile() -> str:
    candidates = [
        Path.home()
        / "Downloads"
        / "job_agent_v27"
        / "job_agent_v27"
        / "browser_profile",
        Path.home()
        / "Downloads"
        / "job_agent_v51"
        / "job_agent_v51"
        / "browser_profile",
        Path.home()
        / "Downloads"
        / "job_agent_v52"
        / "job_agent_v52"
        / "browser_profile",
    ]
    for p in candidates:
        if p.exists() and p.is_dir():
            return str(p)
    return str(DEFAULT_PROFILE_DIR)


DEFAULTS = {
    "search_only": True,
    "source_jobs": True,
    "source_prace": True,
    "source_startupjobs": True,
    "max_applications": 3,
    "min_apply": 66,
    "verified_apply": 64,
    "entry_apply": 62,
    "expanded_apply": 70,
    "review": 55,
    "manual_queue_min": 65,
    "browser_evidence": True,
    "czech_cover_letter": True,
    "prague_only": True,
    "cv_path": "",
    "first_name": "",
    "last_name": "",
    "email": "",
    "phone": "",
    "browser_profile": detect_legacy_profile(),
    "update_channel": APP_CHANNEL,
    "update_channel_explicit": False,
    "update_manifest_url": DEFAULT_UPDATE_MANIFEST_URL,
    "auto_check_updates": True,
}


def load_settings() -> dict:
    data = dict(DEFAULTS)
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                # v2.7.3 scoring migration: update only untouched v2.7.2
                # defaults. Any custom threshold set by the user is preserved.
                legacy_thresholds = {
                    "min_apply": 73,
                    "verified_apply": 70,
                    "entry_apply": 68,
                    "expanded_apply": 74,
                    "review": 60,
                }
                settings_changed = False

                # Indeed was retired in Desktop 2.8. Remove the legacy setting
                # from existing local profiles instead of carrying dead config
                # forward indefinitely.
                if "source_indeed" in saved:
                    saved = dict(saved)
                    saved.pop("source_indeed", None)
                    settings_changed = True

                if all(
                    saved.get(key, old_value) == old_value
                    for key, old_value in legacy_thresholds.items()
                ):
                    saved = dict(saved)
                    saved.update({
                        "min_apply": 66,
                        "verified_apply": 64,
                        "entry_apply": 62,
                        "expanded_apply": 70,
                        "review": 55,
                    })
                    settings_changed = True

                # Older beta builds incorrectly defaulted their updater to the
                # stable channel. Migrate only that old implicit default. Once
                # the user changes the channel in the UI we persist
                # update_channel_explicit=True and never override the choice.
                saved_channel = str(
                    saved.get("update_channel", "")
                ).strip().lower()
                if (
                    APP_CHANNEL == "beta"
                    and saved_channel in {"", "stable"}
                    and not bool(saved.get("update_channel_explicit", False))
                ):
                    saved = dict(saved)
                    saved["update_channel"] = "beta"
                    saved["update_channel_explicit"] = False
                    settings_changed = True

                if settings_changed:
                    try:
                        SETTINGS_FILE.write_text(
                            json.dumps(saved, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    except Exception:
                        pass

                data.update(saved)
        except Exception:
            pass
    return data


def save_settings(data: dict) -> None:
    SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def canonical_local_job_id(job_id: str, url: str = "") -> str:
    raw = str(job_id or "").strip()
    if raw.startswith("job:") and raw[4:].isdigit():
        return raw
    if raw.isdigit():
        return f"job:{raw}"

    for prefix in ("jobs.cz:", "prace.cz:"):
        if raw.lower().startswith(prefix):
            suffix = raw[len(prefix):]
            if suffix.isdigit():
                return f"job:{suffix}"

    low_url = str(url or "")
    for marker in ("/rpd/", "/pd/", "/job/", "/jobs/", "/pozice/", "/position/"):
        pos = low_url.lower().find(marker)
        if pos >= 0:
            rest = low_url[pos + len(marker):]
            digits = ""
            for ch in rest:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            if digits:
                return f"job:{digits}"

    return raw


def terminal_job_ids() -> set[str]:
    out = set()
    if not HISTORY_FILE.exists():
        return out
    try:
        with HISTORY_FILE.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if str(row.get("status", "")).upper() not in TERMINAL_STATUSES:
                    continue
                key = canonical_local_job_id(
                    row.get("job_id", ""),
                    row.get("url", ""),
                )
                if key:
                    out.add(key)
    except Exception:
        pass
    return out


def vacancy_already_submitted(record: dict) -> bool:
    key = canonical_local_job_id(
        record.get("job_id", ""),
        record.get("url", ""),
    )
    return bool(key and key in terminal_job_ids())


def processed_count() -> int:
    if not HISTORY_FILE.exists():
        return 0

    unique = set()
    try:
        with HISTORY_FILE.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("status") not in TERMINAL_STATUSES:
                    continue
                jid = canonical_local_job_id(
                    row.get("job_id", ""),
                    row.get("url", ""),
                )
                if jid:
                    unique.add(jid)
    except Exception:
        return 0
    return len(unique)


def parse_vacancy_saved_at(value):
    """Return local naive timestamp, or None for old/invalid undated records."""
    if not value:
        return None
    try:
        date = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if date.tzinfo is not None:
            date = date.astimezone().replace(tzinfo=None)
        return date
    except (TypeError, ValueError, OverflowError):
        return None


def protected_vacancy(record, overrides=None, submitted_ids=None):
    """Never silently purge submitted, favorited or queued applications."""
    jid = canonical_local_job_id(record.get("job_id", ""), record.get("url", ""))
    override = (overrides or {}).get(jid, {})
    decision = str(override.get("decision", "")).upper()
    if jid in (submitted_ids or set()):
        return True
    if str(record.get("status", "")).upper() in TERMINAL_STATUSES:
        return True
    if decision in {"INTERESTING", "MANUAL_APPLY"} or bool(record.get("manual_queue")):
        return True
    return False


def old_vacancy_ids(records, days, now=None, overrides=None, submitted_ids=None):
    """Use the latest saved snapshot, not a guessed posting date."""
    cutoff = (now or datetime.now()) - timedelta(days=int(days))
    return {
        canonical_local_job_id(row.get("job_id", ""), row.get("url", ""))
        for row in records
        if parse_vacancy_saved_at(row.get("saved_at")) is not None
        and parse_vacancy_saved_at(row.get("saved_at")) < cutoff
        and not protected_vacancy(row, overrides, submitted_ids)
        and canonical_local_job_id(row.get("job_id", ""), row.get("url", ""))
    }


def purge_vacancy_records(job_ids):
    """Back up and remove snapshots, preserve applications.csv, block rediscovery.

    Returns (vacancies_hidden, snapshot_rows_removed, backup_path). Invalid JSON
    lines are preserved unchanged. If a snapshot is absent, an INACTIVE tombstone
    still prevents a legacy history fallback from showing the vacancy.
    """
    ids = {canonical_local_job_id(jid) for jid in job_ids}
    ids.discard("")
    if not ids:
        return 0, 0, None

    overrides = load_job_overrides()
    submitted = terminal_job_ids()
    records = {
        canonical_local_job_id(row.get("job_id", ""), row.get("url", "")): row
        for row in load_vacancy_records()
    }
    for jid in ids:
        if jid in submitted or (jid in records and protected_vacancy(records[jid], overrides, submitted)):
            raise ValueError(f"Запись {jid} защищена: отклик, избранное или очередь.")

    source_lines = []
    if VACANCIES_FILE.exists():
        source_lines = VACANCIES_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    retained = []
    removed_rows = 0
    for line in source_lines:
        try:
            row = json.loads(line)
            jid = canonical_local_job_id(row.get("job_id", ""), row.get("url", ""))
        except (ValueError, AttributeError, TypeError):
            retained.append(line)
            continue
        if jid in ids:
            removed_rows += 1
        else:
            retained.append(line)

    # No history file is rewritten or removed. The backup is retained locally.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backups = VACANCIES_FILE.parent / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    backup_path = None
    if VACANCIES_FILE.exists():
        backup_path = backups / f"vacancies-{stamp}.jsonl"
        shutil.copy2(VACANCIES_FILE, backup_path)

    data = load_job_overrides()
    for jid in ids:
        data[jid] = {"decision": "INACTIVE", "updated_at": datetime.now().isoformat(timespec="seconds"),
                     "reason": "manually_deleted"}
    OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    def atomic_write(path, content):
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=f".{path.name}-", delete=False) as tmp:
                name = Path(tmp.name)
                tmp.write(content)
            os.replace(name, path)
        finally:
            if name is not None and name.exists():
                name.unlink()

    atomic_write(OVERRIDES_FILE, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    if source_lines:
        atomic_write(VACANCIES_FILE, "".join(retained))
    return len(ids), removed_rows, backup_path


def load_vacancy_records() -> list[dict]:
    latest = {}

    if VACANCIES_FILE.exists():
        try:
            with VACANCIES_FILE.open("r", encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        row = json.loads(raw)
                    except Exception:
                        continue
                    source = str(row.get("source", "")).strip().lower()
                    url = str(row.get("url", "")).strip().lower()
                    if source == "indeed.cz" or "indeed.com" in url:
                        continue
                    jid = canonical_local_job_id(
                        row.get("job_id", ""),
                        row.get("url", ""),
                    )
                    if jid:
                        row["job_id"] = jid
                        latest[jid] = row
        except Exception:
            pass

    # A purged vacancy may still have historical application rows.
    # Keep them in applications.csv without recreating the removed Dashboard item.
    inactive = {
        key for key, value in load_job_overrides().items()
        if str(value.get("decision", "")).upper() == "INACTIVE"
    }

    # Backward-compatible fallback for jobs recorded before Desktop 2.2.
    if HISTORY_FILE.exists():
        try:
            with HISTORY_FILE.open("r", encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    source = str(row.get("source", "")).strip().lower()
                    url = str(row.get("url", "")).strip().lower()
                    if source == "indeed.cz" or "indeed.com" in url:
                        continue
                    jid = canonical_local_job_id(
                        row.get("job_id", ""),
                        row.get("url", ""),
                    )
                    if not jid:
                        continue
                    if jid not in latest and jid not in inactive:
                        copied = dict(row)
                        copied["job_id"] = jid
                        latest[jid] = copied
        except Exception:
            pass

    def sort_key(row):
        try:
            score = int(float(row.get("score", 0) or 0))
        except Exception:
            score = 0
        return (-score, str(row.get("title", "")).lower())

    return sorted(latest.values(), key=sort_key)


def load_job_overrides() -> dict:
    if not OVERRIDES_FILE.exists():
        return {}
    try:
        data = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        normalized = {}
        for raw_key, value in data.items():
            key = canonical_local_job_id(raw_key)
            if key:
                normalized[key] = value
        return normalized
    except Exception:
        return {}


def write_job_override(job_id: str, decision: str) -> None:
    job_id = canonical_local_job_id(job_id)
    if not job_id:
        return
    OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = load_job_overrides()
    data[job_id] = {
        "decision": decision,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    OVERRIDES_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def delete_job_override(job_id: str) -> bool:
    job_id = canonical_local_job_id(job_id)
    if not job_id:
        return False
    data = load_job_overrides()
    if job_id not in data:
        return False
    del data[job_id]
    OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDES_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


class QueueWriter(io.TextIOBase):
    def __init__(self, q):
        self.q = q
        self.buffer = ""

    def write(self, text):
        if not text:
            return 0
        self.buffer += str(text)
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.q.put(("log", line))
        return len(text)

    def flush(self):
        if self.buffer:
            self.q.put(("log", self.buffer))
            self.buffer = ""


def child_env(settings: dict) -> dict:
    allowed_location = (
        "Praha,Prague,Stodůlky,Stodulky,"
        "Praha-východ,Praha-západ,Říčany,Ricany"
    )
    blocked_location = (
        "Brno,Ostrava,Olomouc,Plzeň,Plzen,"
        "České Budějovice,Ceske Budejovice,"
        "Hradec Králové,Hradec Kralove,Pardubice,"
        "Zlín,Zlin,Liberec"
    )

    return {
        "SEARCH_ONLY": str(bool(settings.get("search_only", True))).lower(),
        "SOURCE_JOBS_CZ": str(settings["source_jobs"]).lower(),
        "SOURCE_PRACE_CZ": str(settings["source_prace"]).lower(),
        "SOURCE_STARTUPJOBS_CZ": str(settings["source_startupjobs"]).lower(),
        "MAX_APPLICATIONS_PER_RUN": str(settings["max_applications"]),
        "MIN_APPLY_SCORE": str(settings["min_apply"]),
        "VERIFIED_TARGET_APPLY_SCORE": str(settings["verified_apply"]),
        "ENTRY_APPLY_SCORE": str(settings["entry_apply"]),
        "EXPANDED_APPLY_SCORE": str(settings["expanded_apply"]),
        "MIN_REVIEW_SCORE": str(settings["review"]),
        "MANUAL_REVIEW_APPLY_MIN_SCORE": str(settings["manual_queue_min"]),
        "BROWSER_EVIDENCE_RECOVERY": str(
            settings["browser_evidence"]
        ).lower(),
        "AUTO_CZECH_COVER_LETTER": str(
            settings["czech_cover_letter"]
        ).lower(),
        "COVER_LETTER_LANGUAGE": "cs",
        "LOCATION_MODE": "prague" if settings["prague_only"] else "any",
        "ALLOWED_LOCATION_TERMS": allowed_location,
        "BLOCKED_LOCATION_TERMS": blocked_location,
        "ALLOW_FULL_REMOTE_OUTSIDE_PRAGUE": "true",
        "CV_PATH": str(Path(settings["cv_path"]).expanduser()),
        "CANDIDATE_FIRST_NAME": settings.get("first_name", ""),
        "CANDIDATE_LAST_NAME": settings.get("last_name", ""),
        "CANDIDATE_EMAIL": settings.get("email", ""),
        "CANDIDATE_PHONE": settings.get("phone", ""),
        "BROWSER_PROFILE_DIR": str(
            Path(settings["browser_profile"]).expanduser()
        ),
        "STATE_DIR": str(Path.home() / ".job_agent"),
        "PLAYWRIGHT_BROWSERS_PATH": str(PLAYWRIGHT_BROWSERS_DIR),

        # Consequential action safety is intentionally locked in Desktop v1.
        "AUTO_SUBMIT": "false",
        "CONFIRMATION_GATE": "false",
        "ALLOW_JOBS_HANDOFF": "false",
        "MANUAL_SUBMIT_HOLD": "true",
        "CONTINUE_AFTER_APPLICATION_ERROR": "true",

        # Discovery/runtime defaults used by the Desktop child process.
        "MAX_DISCOVERY_PER_SOURCE": "80",
        "MAX_BROWSER_EVIDENCE_JOBS": "12",
        "MAX_JOBS_TO_REVIEW": "36",
        "STRICT_APPLICATION_ROUTE_VALIDATION": "true",
        "ALLOW_SAME_HOST_REPLY_FALLBACK": "true",
    }


def agent_worker(settings: dict, q) -> None:
    writer = QueueWriter(q)
    sys.stdout = writer
    sys.stderr = writer

    try:
        if hasattr(os, "setsid"):
            try:
                os.setsid()
            except Exception:
                pass

        os.chdir(RUNTIME_DIR)

        for key, value in child_env(settings).items():
            os.environ[key] = value

        cv = Path(settings["cv_path"]).expanduser()
        if not settings.get("search_only", True) and not cv.is_file():
            raise FileNotFoundError(f"CV not found: {cv}")

        profile = Path(settings["browser_profile"]).expanduser()
        profile.mkdir(parents=True, exist_ok=True)

        q.put(("state", "running"))

        import asyncio
        import main as agent_main

        asyncio.run(agent_main.main())
        writer.flush()
        q.put(("finished", 0))
    except KeyboardInterrupt:
        writer.flush()
        q.put(("finished", 130))
    except Exception as exc:
        writer.flush()
        q.put(("log", f"❌ Desktop runner error: {type(exc).__name__}: {exc}"))
        q.put(("finished", 1))



def prepare_job_worker(settings: dict, job: dict, q) -> None:
    writer = QueueWriter(q)
    sys.stdout = writer
    sys.stderr = writer

    try:
        if hasattr(os, "setsid"):
            try:
                os.setsid()
            except Exception:
                pass

        os.chdir(RUNTIME_DIR)
        for key, value in child_env(settings).items():
            os.environ[key] = value

        cv = Path(settings["cv_path"]).expanduser()
        if not cv.is_file():
            raise FileNotFoundError(f"CV not found: {cv}")

        profile = Path(settings["browser_profile"]).expanduser()
        profile.mkdir(parents=True, exist_ok=True)

        q.put(("state", "running"))

        import asyncio
        import main as agent_main

        asyncio.run(agent_main.prepare_single_job(job))
        writer.flush()
        q.put(("finished", 0))
    except KeyboardInterrupt:
        writer.flush()
        q.put(("finished", 130))
    except Exception as exc:
        writer.flush()
        q.put(("log", f"❌ Prepare now error: {type(exc).__name__}: {exc}"))
        q.put(("finished", 1))


class UpdateCheckWorker(QObject):
    finished = Signal(object, object)

    def __init__(self, manifest_url, channel, current_version):
        super().__init__()
        self.manifest_url = manifest_url
        self.channel = channel
        self.current_version = current_version

    @Slot()
    def run(self):
        try:
            from updater import read_manifest, is_newer
            info = read_manifest(self.manifest_url, self.channel)
            if info is None:
                self.finished.emit(None, "No release found for selected channel.")
                return
            payload = {
                "version": info.version,
                "channel": info.channel,
                "url": info.url,
                "sha256": info.sha256,
                "notes": info.notes,
                "min_version": info.min_version,
                "is_newer": is_newer(info.version, self.current_version),
            }
            self.finished.emit(payload, None)
        except Exception as exc:
            self.finished.emit(None, f"{type(exc).__name__}: {exc}")


class UpdateDownloadWorker(QObject):
    finished = Signal(object, object)
    progress = Signal(int)

    def __init__(self, info_dict):
        super().__init__()
        self.info_dict = info_dict

    @Slot()
    def run(self):
        try:
            from updater import UpdateInfo, download_update
            info = UpdateInfo(
                version=self.info_dict["version"],
                channel=self.info_dict["channel"],
                url=self.info_dict["url"],
                sha256=self.info_dict.get("sha256", ""),
                notes=self.info_dict.get("notes", ""),
                min_version=self.info_dict.get("min_version", ""),
            )
            path = download_update(
                info,
                progress_cb=lambda p: self.progress.emit(int(p)),
            )
            self.finished.emit(str(path), None)
        except Exception as exc:
            self.finished.emit(None, f"{type(exc).__name__}: {exc}")


class JobAgentWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Job Agent Desktop v{APP_VERSION}")
        self.setWindowIcon(QIcon(brand_pixmap(128)))
        self.settings = load_settings()

        self.log_queue = None
        self.agent_process = None
        self.run_started_at = None
        self.update_thread = None
        self.update_worker = None
        self.available_update = None
        self.dashboard_all_records = []
        self.dashboard_records = []

        self._build_ui()
        self._load_widgets()
        self.channel_combo.currentTextChanged.connect(
            self._persist_update_channel
        )
        self._fit_window_to_screen()

        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self._poll_queue)
        self.timer.start()

        self.stats_timer = QTimer(self)
        self.stats_timer.setInterval(2500)
        self.stats_timer.timeout.connect(self._refresh_stats)
        self.stats_timer.start()

        self._refresh_stats()

        # Give the window time to finish opening, then perform a read-only
        # update check. Installation still requires explicit user action.
        if self.settings.get("auto_check_updates", True):
            QTimer.singleShot(
                1800,
                lambda: self.check_for_updates(silent=True),
            )

    def _fit_window_to_screen(self):
        """
        Keep the initial window comfortably inside the usable desktop area.
        Widget layouts remain resizable; this only chooses a sensible startup
        size and minimum size for smaller Mac displays / scaled resolutions.
        """
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(960, 720)
            self.setMinimumSize(760, 560)
            return

        available = screen.availableGeometry()
        target_w = min(1380, max(860, int(available.width() * 0.92)))
        target_h = min(900, max(640, int(available.height() * 0.90)))
        self.setMinimumSize(
            min(760, max(680, int(available.width() * 0.72))),
            min(560, max(500, int(available.height() * 0.62))),
        )
        self.resize(target_w, target_h)

    def _build_ui(self):
        palette = QPalette()
        for role, color in [(QPalette.Window, "#ffffff"), (QPalette.WindowText, "#101626"), (QPalette.Base, "#ffffff"), (QPalette.Text, "#101626"), (QPalette.Button, "#ffffff"), (QPalette.ButtonText, "#101626"), (QPalette.Highlight, "#e4efff"), (QPalette.HighlightedText, "#101626")]:
            palette.setColor(role, QColor(color))
        self.setPalette(palette)
        families = QFontDatabase.families()
        family = next((f for preferred in ("Helvetica Neue", "Arial", "Nimbus Sans [urw]", "Nimbus Sans [UKWN]", "DejaVu Sans") for f in families if f == preferred), QApplication.font().family())
        self.setStyleSheet(LIGHT_STYLE.replace('"Helvetica Neue", "Arial", sans-serif', f'"{family}"'))
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(10, 32, 10, 20)
        side.setSpacing(8)
        brand = QHBoxLayout()
        brand.setContentsMargins(10, 0, 0, 0)
        brand.setSpacing(12)
        self.brand_icon = QLabel()
        self.brand_icon.setPixmap(icon_pixmap("briefcase", "#ffffff", 36, "#065dff"))
        brand.addWidget(self.brand_icon)
        brand_name = QLabel("Job Agent")
        brand_name.setStyleSheet("font-size:19px;font-weight:600;")
        brand.addWidget(brand_name)
        brand.addStretch()
        side.addLayout(brand)
        side.addSpacing(20)
        self.nav_buttons = []
        for index, label, icon_name in [(0, "Обзор", "home"), (1, "Отклики", "document"), (2, "Журнал", "list")]:
            button = QPushButton("  " + label)
            button.setObjectName("Nav")
            button.setIcon(ui_icon(icon_name))
            button.setIconSize(QSize(22, 22))
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.workspace_tabs.setCurrentIndex(i))
            self.nav_buttons.append(button)
            side.addWidget(button)
            if index == 0:
                vacancies = QPushButton("  Вакансии")
                vacancies.setObjectName("Nav")
                vacancies.setIcon(ui_icon("search"))
                vacancies.setIconSize(QSize(22, 22))
                vacancies.clicked.connect(self._show_all_vacancies)
                side.addWidget(vacancies)
        saved = QPushButton("  Избранное")
        saved.setObjectName("Nav")
        saved.setIcon(ui_icon("bookmark"))
        saved.setIconSize(QSize(22, 22))
        saved.clicked.connect(self._show_favorites)
        side.addWidget(saved)
        side.addStretch()
        for label, tab, icon_name in [("Профиль", 0, "person"), ("Настройки", 1, "settings"), ("Обновления", 4, "update")]:
            button = QPushButton("  " + label)
            button.setObjectName("Nav")
            button.setIcon(ui_icon(icon_name))
            button.setIconSize(QSize(22, 22))
            button.clicked.connect(lambda checked=False, i=tab: self._open_settings(i))
            side.addWidget(button)
        version = QLabel(f"Версия {APP_VERSION} · {APP_CHANNEL}")
        version.setObjectName("Muted")
        version.setContentsMargins(14, 12, 0, 0)
        version.setStyleSheet("font-size:12px;")
        side.addWidget(version)
        outer.addWidget(sidebar)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(26, 36, 20, 16)
        layout.setSpacing(16)
        outer.addWidget(content, 1)
        heading = QHBoxLayout()
        heading.setSpacing(20)
        heading_text = QVBoxLayout()
        heading_text.setSpacing(4)
        self.page_title = QLabel("Вакансии для тебя")
        self.page_title.setObjectName("Title")
        heading_text.addWidget(self.page_title)
        self.page_subtitle = QLabel("Прага и рядом · Data / BI / Reporting")
        self.page_subtitle.setObjectName("Subtitle")
        self.page_subtitle.setWordWrap(True)
        heading_text.addWidget(self.page_subtitle)
        heading.addLayout(heading_text, 1)
        self.metric_panels = []
        self.metric_dividers = []
        self.total_value, self.processed_value, self.review_value = QLabel("0"), QLabel("0"), QLabel("0")
        for i, (value, label) in enumerate([(self.total_value, "в истории"), (self.processed_value, "отправлено"), (self.review_value, "на проверку")]):
            if i:
                divider = QFrame()
                divider.setObjectName("MetricDivider")
                divider.setFixedSize(1, 50)
                heading.addWidget(divider)
                self.metric_dividers.append(divider)
            panel = QWidget()
            box = QVBoxLayout(panel)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(2)
            value.setObjectName("Metric")
            box.addWidget(value)
            caption = QLabel(label)
            caption.setObjectName("MetricCaption")
            box.addWidget(caption)
            heading.addWidget(panel)
            self.metric_panels.append(panel)
        run_controls = QVBoxLayout()
        run_controls.setSpacing(6)
        run_buttons = QHBoxLayout()
        self.start_btn = QPushButton("Начать поиск")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setIcon(ui_icon("search", "#ffffff", 21))
        self.start_btn.setIconSize(QSize(21, 21))
        self.start_btn.setMinimumHeight(46)
        self.start_btn.clicked.connect(self.start_agent)
        self.stop_btn = QPushButton("Стоп")
        self.stop_btn.setEnabled(False)
        self.stop_btn.hide()
        self.stop_btn.clicked.connect(self.stop_agent)
        run_buttons.addWidget(self.start_btn)
        run_buttons.addWidget(self.stop_btn)
        run_controls.addLayout(run_buttons)
        self.search_only_check = QCheckBox("Только поиск")
        self.search_only_check.setStyleSheet("font-size:11px; color:#69758d;")
        self.search_only_check.setToolTip("Собрать и оценить вакансии. Подготовку выбранного отклика можно запустить отдельно.")
        self.search_only_check.toggled.connect(self._update_run_mode)
        run_controls.addWidget(self.search_only_check, 0, Qt.AlignRight)
        heading.addLayout(run_controls)
        layout.addLayout(heading)

        self.source_strip = QFrame()
        self.source_strip.setObjectName("SourceStrip")
        self.source_strip.setMinimumHeight(44)
        source_row = QHBoxLayout(self.source_strip)
        source_row.setContentsMargins(6, 2, 6, 2)
        source_row.setSpacing(0)
        self.source_badges = {}
        for i, source in enumerate(("jobs.cz", "prace.cz", "startupjobs.cz")):
            if i:
                divider = QFrame()
                divider.setObjectName("MetricDivider")
                divider.setFixedSize(1, 20)
                source_row.addWidget(divider)
            badge = QLabel()
            badge.setObjectName("Source")
            self.source_badges[source] = badge
            source_row.addWidget(badge)
        source_row.addStretch()
        layout.addWidget(self.source_strip)

        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.tabBar().hide()
        self.workspace_tabs.currentChanged.connect(self._page_changed)
        layout.addWidget(self.workspace_tabs, 1)
        dashboard_page = QWidget()
        dashboard_layout = QVBoxLayout(dashboard_page)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.setSpacing(16)
        dash_filters = QGridLayout()
        self.filters_layout = dash_filters
        dash_filters.setContentsMargins(0, 0, 0, 0)
        dash_filters.setSpacing(10)
        self.dashboard_search = QLineEdit()
        self.dashboard_search.setObjectName("Search")
        self.dashboard_search.setPlaceholderText("Поиск по названиям вакансий, компаниям, навыкам…")
        self.dashboard_search.addAction(ui_icon("search", "#69758d", 20), QLineEdit.LeadingPosition)
        self.dashboard_search.setClearButtonEnabled(True)
        self.dashboard_decision_filter = QComboBox(self)
        for label, value in [("Все вакансии", "All"), ("Подходят", "APPLY"), ("Проверить", "REVIEW"), ("В очереди", "QUEUED"), ("Избранное", "INTERESTING"), ("Пропущены", "SKIP"), ("Неактивные", "INACTIVE"), ("Отправлены", "SUBMITTED"), ("Можно в очередь", "Manual queue eligible")]:
            self.dashboard_decision_filter.addItem(label, value)
        self.dashboard_decision_filter.hide()
        self.dashboard_source_filter = QComboBox(self)
        self.dashboard_source_filter.addItem("Все источники", "All sources")
        for source in ("jobs.cz", "prace.cz", "startupjobs.cz"):
            self.dashboard_source_filter.addItem(source, source)
        self.dashboard_source_filter.hide()
        self.filter_tabs = QWidget()
        filter_row = QHBoxLayout(self.filter_tabs)
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(6)
        self.filter_buttons = {}
        for value, label in [("All", "Все"), ("APPLY", "Подходят"), ("REVIEW", "Проверить"), ("SUBMITTED", "Отправлены")]:
            button = QPushButton(label + " (0)")
            button.setObjectName("FilterTab")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, v=value: self._select_decision_filter(v))
            self.filter_buttons[value] = button
            filter_row.addWidget(button)
        self.filter_menu_btn = QPushButton()
        self.filter_menu_btn.setObjectName("IconButton")
        self.filter_menu_btn.setIcon(ui_icon("filter", "#69758d", 21))
        self.filter_menu_btn.setToolTip("Источник и дополнительные фильтры")
        filter_menu = QMenu(self.filter_menu_btn)
        self.source_filter_actions = {}
        source_menu = filter_menu.addMenu("Источник")
        for i in range(self.dashboard_source_filter.count()):
            value = self.dashboard_source_filter.itemData(i)
            action = source_menu.addAction(self.dashboard_source_filter.itemText(i))
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, v=value: self.dashboard_source_filter.setCurrentIndex(self.dashboard_source_filter.findData(v)))
            self.source_filter_actions[value] = action
        filter_menu.addSeparator()
        self.extra_filter_actions = {}
        for value, label in [("QUEUED", "В очереди"), ("INTERESTING", "Избранное"), ("SKIP", "Пропущены"), ("INACTIVE", "Неактивные"), ("Manual queue eligible", "Можно в очередь")]:
            action = filter_menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, v=value: self._select_decision_filter(v))
            self.extra_filter_actions[value] = action
        filter_menu.addSeparator()
        filter_menu.addAction("Сбросить фильтры", self._show_all_vacancies)
        filter_menu.addSeparator()
        filter_menu.addAction("Очистить старые вакансии…", self._cleanup_old_vacancies)
        self.filter_menu_btn.setMenu(filter_menu)
        filter_row.addWidget(self.filter_menu_btn)
        self.dashboard_count = QLabel("0 вакансий")
        self.dashboard_count.setObjectName("Muted")
        self.dashboard_count.hide()
        dash_filters.addWidget(self.dashboard_search, 0, 0)
        dash_filters.addWidget(self.filter_tabs, 0, 1)
        dash_filters.setColumnStretch(0, 1)
        dashboard_layout.addLayout(dash_filters)
        self.dashboard_search.textChanged.connect(self._refresh_dashboard)
        self.dashboard_decision_filter.currentIndexChanged.connect(self._refresh_dashboard)
        self.dashboard_source_filter.currentIndexChanged.connect(self._refresh_dashboard)

        self.dashboard_splitter = QSplitter(Qt.Horizontal)
        self.dashboard_splitter.setHandleWidth(14)
        self.dashboard_splitter.splitterMoved.connect(lambda *_: self._fit_detail_actions())
        self.dashboard_splitter.setChildrenCollapsible(False)
        self.list_panel = QWidget()
        list_layout = QVBoxLayout(self.list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(14)
        self.dashboard_table = self._new_table(["Вакансия", "Источник", "Оценка", "Статус"])
        self.dashboard_table.setItemDelegate(VacancyDelegate(self.dashboard_table))
        self.dashboard_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.dashboard_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.dashboard_table.setColumnWidth(1, 148)
        self.dashboard_table.setColumnWidth(2, 98)
        self.dashboard_table.setColumnWidth(3, 124)
        self.dashboard_table.verticalHeader().setDefaultSectionSize(94)
        self.dashboard_table.itemSelectionChanged.connect(self._dashboard_selection_changed)
        self.dashboard_table.doubleClicked.connect(lambda _: self._open_selected_job())
        list_layout.addWidget(self.dashboard_table, 1)
        self.run_journal = QFrame()
        self.run_journal.setObjectName("RunJournal")
        self.run_journal.setFixedHeight(144)
        journal_layout = QVBoxLayout(self.run_journal)
        journal_layout.setContentsMargins(0, 0, 0, 12)
        self.journal_header = QPushButton("Журнал запуска")
        self.journal_header.setObjectName("JournalHeader")
        self.journal_header.setIcon(ui_icon("down", "#101626", 16))
        self.journal_header.clicked.connect(lambda: self.workspace_tabs.setCurrentIndex(2))
        journal_layout.addWidget(self.journal_header)
        journal_row = QHBoxLayout()
        journal_row.setContentsMargins(18, 0, 14, 0)
        self.status_label = QLabel("●")
        self.status_label.setStyleSheet("color:#33a129; font-size:20px;")
        self.status_label.setToolTip("Готов к поиску")
        self.run_time_value = QLabel("—")
        self.run_time_value.setObjectName("Muted")
        self.browser_status_value = QLabel("")
        self.latest_log = QLabel("Начни поиск — результаты появятся в списке")
        self.latest_log.setObjectName("Muted")
        self.latest_log.setWordWrap(True)
        self.latest_log.setMaximumHeight(46)
        self.latest_log.setStyleSheet("font-size:12px;")
        self.latest_log.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        journal_row.addWidget(self.status_label)
        journal_row.addSpacing(10)
        journal_row.addWidget(self.run_time_value)
        journal_row.addSpacing(16)
        journal_row.addWidget(self.latest_log, 1)
        journal_more = QPushButton()
        journal_more.setObjectName("IconButton")
        journal_more.setIcon(ui_icon("more", "#69758d", 18))
        journal_more.setToolTip("Открыть полный журнал")
        journal_more.clicked.connect(lambda: self.workspace_tabs.setCurrentIndex(2))
        journal_row.addWidget(journal_more)
        journal_layout.addLayout(journal_row, 1)
        list_layout.addWidget(self.run_journal)
        self.dashboard_splitter.addWidget(self.list_panel)
        detail_panel = QFrame()
        detail_panel.setObjectName("DetailCard")
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(20, 18, 18, 12)
        detail_layout.setSpacing(10)
        self.dashboard_detail = VacancyDetail()
        self.dashboard_detail.setPlainText("Выбери вакансию, чтобы увидеть описание и причины оценки.")
        detail_layout.addWidget(self.dashboard_detail, 1)
        dash_buttons = QGridLayout()
        dash_buttons.setSpacing(10)
        self.detail_buttons_layout = dash_buttons
        self.prepare_now_btn = QPushButton("Подготовить отклик")
        self.prepare_now_btn.setObjectName("Primary")
        self.prepare_now_btn.setIcon(ui_icon("document", "#ffffff", 19))
        self.open_job_btn = QPushButton("Открыть вакансию")
        self.open_job_btn.setObjectName("Outline")
        self.open_job_btn.setIcon(ui_icon("external", "#065dff", 17))
        self.prepare_now_btn.clicked.connect(self._prepare_selected_now)
        self.open_job_btn.clicked.connect(self._open_selected_job)
        self.prepare_now_btn.setMinimumHeight(44)
        self.open_job_btn.setMinimumHeight(44)
        dash_buttons.addWidget(self.prepare_now_btn, 0, 0)
        dash_buttons.addWidget(self.open_job_btn, 0, 1)
        dash_buttons.setColumnStretch(0, 1)
        more = QPushButton()
        more.setObjectName("IconButton")
        more.setIcon(ui_icon("more", "#69758d", 18))
        more.setToolTip("Очередь, избранное и сопроводительное письмо")
        menu = QMenu(more)
        self.detail_actions = []
        for label, callback in [
            ("В очередь на следующий запуск", self._queue_selected_application),
            ("Сохранить в избранное", lambda: self._set_selected_override("INTERESTING")),
            ("Отметить для проверки", lambda: self._set_selected_override("REVIEW")),
            ("Пропустить", lambda: self._set_selected_override("SKIP")),
            ("Убрать неактивную вакансию", self._archive_selected_vacancy),
            ("Восстановить вакансию", self._restore_selected_vacancy),
            ("Сбросить отметку", self._clear_selected_override),
            ("Посмотреть письмо", self._show_selected_cover_letter),
            ("Копировать письмо", self._copy_selected_cover_letter),
            ("Удалить запись из базы…", self._delete_selected_vacancy),
        ]:
            action = menu.addAction(label)
            action.triggered.connect(callback)
            self.detail_actions.append(action)
        more.setMenu(menu)
        self.more_job_btn = more
        detail_layout.addLayout(dash_buttons)
        note_row = QHBoxLayout()
        note_icon = QLabel()
        note_icon.setPixmap(icon_pixmap("info", "#69758d", 16))
        note_row.addWidget(note_icon)
        note = QLabel("Финальную отправку подтверждаешь ты")
        self.submit_note = note
        note.setObjectName("Muted")
        note.setStyleSheet("font-size:11px;")
        note.setWordWrap(True)
        note_row.addWidget(note, 1)
        note_row.addWidget(more)
        detail_layout.addLayout(note_row)
        self.dashboard_splitter.addWidget(detail_panel)
        self.dashboard_splitter.setSizes([700, 440])
        dashboard_layout.addWidget(self.dashboard_splitter, 1)
        self.workspace_tabs.addTab(dashboard_page, "Обзор")

        applications_page = QWidget()
        applications_layout = QVBoxLayout(applications_page)
        applications_layout.setContentsMargins(0, 0, 0, 0)
        self.applications_count = QLabel("0")
        applications_layout.addWidget(self.applications_count)
        self.applications_table = self._new_table(["Оценка", "Вакансия", "Компания", "Решение", "Результат"])
        self.applications_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.applications_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.applications_table.verticalHeader().setDefaultSectionSize(62)
        applications_layout.addWidget(self.applications_table, 1)
        self.workspace_tabs.addTab(applications_page, "Отклики")

        log_page = QWidget()
        log_layout = QVBoxLayout(log_page)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("Журнал текущего запуска"))
        log_header.addStretch()
        copy_log = QPushButton("Копировать журнал")
        copy_log.clicked.connect(lambda: QApplication.clipboard().setText(self.log.toPlainText()))
        log_header.addWidget(copy_log)
        clear_log = QPushButton("Очистить")
        clear_log.clicked.connect(lambda: self.log.clear())
        log_header.addWidget(clear_log)
        log_layout.addLayout(log_header)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(12000)
        self.log.setFont(QFont("Menlo", 11))
        log_layout.addWidget(self.log, 1)
        self.workspace_tabs.addTab(log_page, "Журнал")
        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle("Job Agent · Настройки")
        self.settings_dialog.resize(720, 640)
        settings_layout = QVBoxLayout(self.settings_dialog)
        tabs = QTabWidget()
        self.settings_tabs = tabs
        settings_layout.addWidget(tabs, 1)
        profile_tab = QWidget()
        profile_layout = QFormLayout(profile_tab)
        profile_layout.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapLongRows
        )
        profile_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        self.first_name_edit = QLineEdit()
        self.last_name_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        profile_layout.addRow("Имя", self.first_name_edit)
        profile_layout.addRow("Фамилия", self.last_name_edit)
        profile_layout.addRow("Email", self.email_edit)
        profile_layout.addRow("Телефон", self.phone_edit)

        profile_note = QLabel(
            "Контакты и путь к резюме хранятся на этом Mac. "
            "Они нужны для подготовки отклика. Для поиска вакансий заполнять профиль необязательно."
        )
        profile_note.setWordWrap(True)
        profile_note.setStyleSheet("color: #666;")
        profile_layout.addRow(profile_note)
        tabs.addTab(profile_tab, "Профиль")

        search_tab = QWidget()
        search_layout = QFormLayout(search_tab)
        search_layout.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapLongRows
        )
        search_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )

        self.jobs_check = QCheckBox("Jobs.cz")
        self.prace_check = QCheckBox("Prace.cz")
        self.startupjobs_check = QCheckBox("StartupJobs.cz")

        src_row = QWidget()
        src_l = QGridLayout(src_row)
        src_l.setContentsMargins(0, 0, 0, 0)
        src_l.addWidget(self.jobs_check, 0, 0)
        src_l.addWidget(self.prace_check, 0, 1)
        src_l.addWidget(self.startupjobs_check, 1, 0, 1, 2)
        src_l.setColumnStretch(0, 1)
        src_l.setColumnStretch(1, 1)
        search_layout.addRow("Источники", src_row)

        discovery_note = QLabel(
            "StartupJobs.cz is discovery-only in this version: "
            "vacancies are scored and shown in Dashboard, but applications stay manual."
        )
        discovery_note.setWordWrap(True)
        discovery_note.setStyleSheet("color: #666;")
        search_layout.addRow(discovery_note)

        self.prague_check = QCheckBox("Praha + surroundings")
        self.prague_check.setToolTip(
            "Limit search to Praha and the allowed surrounding area."
        )
        search_layout.addRow("Расположение", self.prague_check)

        self.browser_check = QCheckBox("Chromium for weak jobs")
        self.browser_check.setToolTip(
            "Render vacancies with weak HTTP evidence in Chromium."
        )
        search_layout.addRow("Загрузка описаний", self.browser_check)

        self.cover_check = QCheckBox("Czech Průvodní dopis")
        self.cover_check.setToolTip(
            "Generate and fill a Czech cover letter when a supported field exists."
        )
        search_layout.addRow("Письмо", self.cover_check)

        self.max_apps_spin = QSpinBox()
        self.max_apps_spin.setRange(1, 5)
        search_layout.addRow("Откликов за запуск", self.max_apps_spin)

        tabs.addTab(search_tab, "Поиск")

        scoring_tab = QWidget()
        scoring_layout = QFormLayout(scoring_tab)
        scoring_layout.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapLongRows
        )
        scoring_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )

        self.apply_spin = self._score_spin()
        self.verified_spin = self._score_spin()
        self.entry_spin = self._score_spin()
        self.expanded_spin = self._score_spin()
        self.review_spin = self._score_spin()
        self.manual_queue_spin = self._score_spin()

        scoring_layout.addRow("Target APPLY ≥", self.apply_spin)
        scoring_layout.addRow("Verified target ≥", self.verified_spin)
        scoring_layout.addRow("Junior / Intern ≥", self.entry_spin)
        scoring_layout.addRow("Expanded role ≥", self.expanded_spin)
        scoring_layout.addRow("REVIEW ≥", self.review_spin)
        self.manual_queue_spin.hide()  # Retain stored legacy setting, not a user-facing score gate
        tabs.addTab(scoring_tab, "Оценка")

        paths_tab = QWidget()
        paths_layout = QVBoxLayout(paths_tab)

        paths_layout.addWidget(QLabel("CV"))
        cv_row = QHBoxLayout()
        self.cv_edit = QLineEdit()
        self.cv_btn = QPushButton("Browse…")
        self.cv_btn.clicked.connect(self._browse_cv)
        cv_row.addWidget(self.cv_edit, 1)
        cv_row.addWidget(self.cv_btn)
        paths_layout.addLayout(cv_row)

        paths_layout.addSpacing(10)
        paths_layout.addWidget(QLabel("Persistent browser profile"))
        profile_row = QHBoxLayout()
        self.profile_edit = QLineEdit()
        self.profile_btn = QPushButton("Browse…")
        self.profile_btn.clicked.connect(self._browse_profile)
        profile_row.addWidget(self.profile_edit, 1)
        profile_row.addWidget(self.profile_btn)
        paths_layout.addLayout(profile_row)

        paths_layout.addStretch()
        tabs.addTab(paths_tab, "Файлы")

        updates_tab = QWidget()
        updates_layout = QVBoxLayout(updates_tab)

        update_brand_row = QHBoxLayout()
        update_brand_icon = QLabel()
        update_brand_icon.setFixedSize(44, 44)
        update_brand_icon.setPixmap(brand_pixmap(44))
        update_brand_icon.setScaledContents(True)
        update_brand_text = QLabel("Job Agent")
        update_brand_font = QFont()
        update_brand_font.setPointSize(16)
        update_brand_font.setBold(True)
        update_brand_text.setFont(update_brand_font)
        update_brand_row.addWidget(update_brand_icon)
        update_brand_row.addWidget(update_brand_text)
        update_brand_row.addStretch()
        updates_layout.addLayout(update_brand_row)

        version_box = QGroupBox("Application")
        version_form = QFormLayout(version_box)
        self.version_value = QLabel(APP_VERSION)
        self.channel_combo = QComboBox()
        self.channel_combo.addItems(["stable", "beta"])
        self.manifest_edit = QLineEdit()
        self.manifest_edit.setText(DEFAULT_UPDATE_MANIFEST_URL)
        self.manifest_edit.setPlaceholderText("https://.../manifest.json")
        self.auto_update_check = QCheckBox("Check automatically when Job Agent starts")
        version_form.addRow("Current version", self.version_value)
        version_form.addRow("Update channel", self.channel_combo)
        version_form.addRow("Manifest URL", self.manifest_edit)
        version_form.addRow("Automatic check", self.auto_update_check)
        updates_layout.addWidget(version_box)

        self.update_status = QLabel(
            "Update source: GitHub Releases • xbatm010/job-agent-releases"
        )
        self.update_status.setWordWrap(True)
        updates_layout.addWidget(self.update_status)

        self.update_notes = QTextEdit()
        self.update_notes.setReadOnly(True)
        self.update_notes.setPlaceholderText("Release notes will appear here.")
        self.update_notes.setMaximumHeight(150)
        updates_layout.addWidget(self.update_notes)

        self.update_progress = QProgressBar()
        self.update_progress.setRange(0, 100)
        self.update_progress.hide()
        updates_layout.addWidget(self.update_progress)

        buttons = QHBoxLayout()
        self.check_update_btn = QPushButton("Check for updates")
        self.install_update_btn = QPushButton("Install update")
        self.install_update_btn.setEnabled(False)
        self.check_update_btn.clicked.connect(self.check_for_updates)
        self.install_update_btn.clicked.connect(self.install_update)
        buttons.addWidget(self.check_update_btn)
        buttons.addWidget(self.install_update_btn)
        updates_layout.addLayout(buttons)
        updates_layout.addStretch()

        tabs.addTab(updates_tab, "Обновления")

        for i in range(tabs.count()):
            page = tabs.widget(i)
            label = tabs.tabText(i)
            tabs.removeTab(i)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(page)
            tabs.insertTab(i, scroll, label)
        save = QPushButton("Сохранить настройки")
        save.setObjectName("Primary")
        save.clicked.connect(self._save_preferences)
        settings_layout.addWidget(save)
        self.prague_check.toggled.connect(self._update_run_mode)
        self._page_changed(0)

    def _new_table(self, headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().hide()
        table.setShowGrid(False)
        table.setWordWrap(True)
        table.setAlternatingRowColors(True)
        table.setMinimumSize(0, 130)
        table.horizontalHeader().setMinimumSectionSize(55)
        table.horizontalHeader().setStretchLastSection(False)
        return table

    def _page_changed(self, index):
        self.page_title.setText(["Вакансии для тебя", "История откликов", "Журнал работы"][index])
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
            button.setIcon(ui_icon(["home", "document", "list"][i], "#065dff" if i == index else "#101626"))

    def _show_favorites(self):
        self.workspace_tabs.setCurrentIndex(0)
        self.dashboard_decision_filter.setCurrentIndex(self.dashboard_decision_filter.findData("INTERESTING"))

    def _open_settings(self, index):
        self.settings_tabs.setCurrentIndex(index)
        self.settings_dialog.show()
        self.settings_dialog.raise_()

    def _save_preferences(self):
        self.settings = self._collect_settings()
        save_settings(self.settings)
        self.settings_dialog.accept()
        self._update_run_mode()
        self._refresh_dashboard()

    def _update_run_mode(self):
        self.start_btn.setText("Начать поиск" if self.search_only_check.isChecked() else "Найти и подготовить")
        area = "Прага и рядом" if self.prague_check.isChecked() else "Любое расположение"
        self.page_subtitle.setText(area + " · Data / BI / Reporting")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "dashboard_splitter"):
            return
        compact = self.width() < 1120
        self.sidebar.setFixedWidth(180 if compact else 200)
        self.page_title.setStyleSheet("font-size:26px;" if compact else "")
        self.page_subtitle.setStyleSheet("font-size:14px;" if compact else "")
        for panel in self.metric_panels + self.metric_dividers:
            panel.setVisible(self.width() >= 1280)
        self.run_journal.setVisible(not compact and self.height() >= 740)
        self.submit_note.setVisible(True)
        direction = Qt.Vertical if compact else Qt.Horizontal
        filters_stacked = self.width() < 1350
        if getattr(self, "_filters_stacked", None) != filters_stacked:
            self._filters_stacked = filters_stacked
            self.filters_layout.removeWidget(self.filter_tabs)
            self.filters_layout.addWidget(self.filter_tabs, 1 if filters_stacked else 0, 0 if filters_stacked else 1)
        if self.dashboard_splitter.orientation() != direction:
            self.dashboard_splitter.setOrientation(direction)
            self.dashboard_splitter.setSizes([180, 310] if compact else [700, 440])
        # The card buttons wrap only when its actual width needs it.
        self._fit_detail_actions()
        QTimer.singleShot(0, self._fit_detail_actions)

    def _fit_detail_actions(self):
        stacked = self.dashboard_splitter.orientation() == Qt.Horizontal and self.dashboard_splitter.widget(1).width() < 420
        if stacked == getattr(self, "_actions_stacked", None):
            return
        self._actions_stacked = stacked
        self.detail_buttons_layout.removeWidget(self.open_job_btn)
        self.detail_buttons_layout.addWidget(self.open_job_btn, 1 if stacked else 0, 0 if stacked else 1)

    def _select_decision_filter(self, value):
        if self.dashboard_decision_filter.currentData() == value:
            self._refresh_dashboard()
        else:
            self.dashboard_decision_filter.setCurrentIndex(self.dashboard_decision_filter.findData(value))

    def _show_all_vacancies(self):
        self.workspace_tabs.setCurrentIndex(0)
        self.dashboard_search.clear()
        self.dashboard_source_filter.setCurrentIndex(0)
        self._select_decision_filter("All")

    def _application_source_supported(self, record):
        return str(record.get("source", "")).strip().lower() in {
            "jobs.cz",
            "prace.cz",
        }

    def _selected_dashboard_record(self):
        row = self.dashboard_table.currentRow()
        if row < 0 or row >= len(self.dashboard_records):
            return None
        return self.dashboard_records[row]

    def _dashboard_selection_changed(self):
        record = self._selected_dashboard_record()
        if not record:
            self.dashboard_detail.setPlainText("Пока нет вакансий. Начни поиск или измени фильтры.")
            self._detail_signature = None
            self.open_job_btn.setEnabled(False)
            self.prepare_now_btn.setEnabled(False)
            self.more_job_btn.setEnabled(False)
            return
        overrides = load_job_overrides()
        decision = display_decision(record, overrides)
        signature = (json.dumps(record, sort_keys=True, ensure_ascii=False), decision)
        if signature != getattr(self, "_detail_signature", None):
            self.dashboard_detail.set_record(record, decision)
            self._detail_signature = signature
        running = bool(self.agent_process and self.agent_process.is_alive())
        terminal = decision == "SUBMITTED"
        supported = self._application_source_supported(record)
        self.open_job_btn.setEnabled(bool(record.get("url")))
        self.more_job_btn.setEnabled(True)
        try:
            score = int(float(record.get("score", 0) or 0))
        except (TypeError, ValueError):
            score = 0
        eligible = record.get("decision") == "APPLY" or (
            record.get("decision") == "REVIEW"
        )
        enabled = not running and not terminal and supported and eligible and decision != "SKIP"
        self.prepare_now_btn.setEnabled(enabled)
        self.prepare_now_btn.setToolTip(
            "Отклик уже отправлен" if terminal else
            "Открой вакансию и откликнись на сайте" if not supported else
            "Перед заполнением агент повторно проверит вакансию"
        )
        for index, action in enumerate(self.detail_actions):
            if 7 <= index <= 8:
                action.setEnabled(bool(record.get("cover_letter")))
            elif index == 9:
                action.setEnabled(not running and not terminal)
            else:
                action.setEnabled(not running and not terminal)
        inactive = str(overrides.get(str(record.get("job_id", "")), {}).get("decision", "")).upper() == "INACTIVE"
        self.detail_actions[4].setEnabled(not running and not inactive)
        self.detail_actions[5].setEnabled(not running and inactive)
        for index in (1, 2, 3, 6):
            self.detail_actions[index].setEnabled(not running and not terminal and not inactive)
        self.prepare_now_btn.setEnabled(self.prepare_now_btn.isEnabled() and not inactive)
        self.detail_actions[0].setEnabled(
            not running and not terminal and not inactive and supported
            and record.get("decision") == "REVIEW"
        )

    def _dashboard_record_matches_filters(self, record, overrides, include_decision=True):
        query = self.dashboard_search.text().strip().lower()
        if query:
            haystack = " ".join([
                str(record.get("title", "")),
                str(record.get("company", "")),
                str(record.get("location", "")),
                str(record.get("description", "")),
                " ".join(record.get("expanded_signals", [])),
            ]).lower()
            if query not in haystack:
                return False

        source_filter = self.dashboard_source_filter.currentData() or "All sources"
        if (
            source_filter != "All sources"
            and str(record.get("source", "")).strip() != source_filter
        ):
            return False

        jid = str(record.get("job_id", ""))
        override = str(
            overrides.get(jid, {}).get("decision", "")
        ).upper().strip()
        decision = override or str(record.get("decision", "")).upper().strip()
        display_decision = "QUEUED" if override == "MANUAL_APPLY" else decision
        if record.get("status") in TERMINAL_STATUSES:
            display_decision = "SUBMITTED"
        status = str(record.get("status", "")).upper().strip()

        selected = self.dashboard_decision_filter.currentData() or "All"
        if override == "INACTIVE":
            return selected == "INACTIVE"
        if selected == "INACTIVE":
            return False
        if not include_decision:
            return True
        if selected == "All":
            return True
        if selected == "SUBMITTED":
            return status in TERMINAL_STATUSES
        if selected == "Manual queue eligible":
            return display_decision in {"REVIEW", "QUEUED"}
        return display_decision == selected

    def _refresh_dashboard(self):
        selected = self._selected_dashboard_record()
        selected_id = str(selected.get("job_id", "")) if selected else ""
        self.dashboard_all_records = load_vacancy_records()
        overrides = load_job_overrides()
        submitted_ids = terminal_job_ids()
        for record in self.dashboard_all_records:
            canonical = canonical_local_job_id(record.get("job_id", ""), record.get("url", ""))
            if canonical in submitted_ids:
                record["status"] = "SUBMITTED_MANUALLY"
                record["decision"] = "APPLY"
        self.dashboard_records = [r for r in self.dashboard_all_records if self._dashboard_record_matches_filters(r, overrides)]
        self.dashboard_table.blockSignals(True)
        self.dashboard_table.setRowCount(len(self.dashboard_records))
        restore_row = 0
        colors = {"APPLY": "#23713e", "SUBMITTED": "#065acb", "REVIEW": "#956619", "SKIP": "#7d8798"}
        for row_index, record in enumerate(self.dashboard_records):
            jid = str(record.get("job_id", ""))
            decision = display_decision(record, overrides)
            values = [
                str(record.get("title", "")) + "\n" + (record.get("company") or "Компания не определена"),
                str(record.get("source") or "—"),
                str(record.get("score", "—")) + "/100",
                DECISION_LABELS.get(decision, decision),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, jid)
                item.setData(Qt.UserRole + 1, record)
                item.setData(Qt.UserRole + 2, decision)
                item.setToolTip(value)
                if col in {2, 3}:
                    item.setForeground(QColor(colors.get(decision, "#425777")))
                self.dashboard_table.setItem(row_index, col, item)
            if jid == selected_id:
                restore_row = row_index
        if self.dashboard_records:
            self.dashboard_table.selectRow(restore_row)
        self.dashboard_table.blockSignals(False)
        self.dashboard_count.setText(f"{len(self.dashboard_records)} вакансий")
        selected_filter = self.dashboard_decision_filter.currentData()
        scoped = [r for r in self.dashboard_all_records if self._dashboard_record_matches_filters(r, overrides, include_decision=False)]
        for key, button in self.filter_buttons.items():
            count = len(scoped) if key == "All" else sum(display_decision(r, overrides) == key for r in scoped)
            label = {"All": "Все", "APPLY": "Подходят", "REVIEW": "Проверить", "SUBMITTED": "Отправлены"}[key]
            button.setText(f"{label} ({count})")
            button.setChecked(selected_filter == key)
        for key, action in self.extra_filter_actions.items():
            action.setChecked(selected_filter == key)
        for key, action in self.source_filter_actions.items():
            action.setChecked(self.dashboard_source_filter.currentData() == key)
        source_filter = self.dashboard_source_filter.currentData()
        filtered = source_filter != "All sources" or selected_filter in self.extra_filter_actions
        self.filter_menu_btn.setIcon(ui_icon("filter", "#065dff" if filtered else "#69758d", 21))
        self.filter_menu_btn.setToolTip("Источник: " + self.dashboard_source_filter.currentText() + " · " + self.dashboard_decision_filter.currentText())
        self.total_value.setText(str(len(self.dashboard_all_records)))
        self.review_value.setText(str(sum(display_decision(r, overrides) == "REVIEW" for r in self.dashboard_all_records)))
        application_records = [r for r in self.dashboard_all_records if r.get("status", "") not in {"", "REVIEW_PENDING", "SKIPPED", "READY_TO_PREPARE"}]
        self.applications_table.setRowCount(len(application_records))
        for row, record in enumerate(application_records):
            decision = display_decision(record, overrides)
            values = [str(record.get("score", "")), str(record.get("title", "")), str(record.get("company", "")), DECISION_LABELS.get(decision, decision), str(record.get("status", ""))]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.applications_table.setItem(row, col, item)
        self.applications_count.setText(f"Попыток отклика в истории: {len(application_records)}")
        self._dashboard_selection_changed()

    def _open_selected_job(self):
        record = self._selected_dashboard_record()
        if not record:
            return
        url = str(record.get("url", "")).strip()
        if not url:
            QMessageBox.information(
                self,
                "Vacancy",
                "No vacancy URL is available for this record.",
            )
            return
        QDesktopServices.openUrl(QUrl(url))

    def _queue_selected_application(self):
        record = self._selected_dashboard_record()
        if not record:
            return

        if not self._application_source_supported(record):
            QMessageBox.information(
                self,
                "Discovery-only source",
                "StartupJobs.cz is currently discovery-only. "
                "Use Open job and submit manually on the employer/job-board site.",
            )
            return

        try:
            score = int(float(record.get("score", 0) or 0))
        except Exception:
            score = 0

        floor = self.manual_queue_spin.value()
        base_decision = str(record.get("decision", "")).upper().strip()

        if base_decision != "REVIEW":
            QMessageBox.information(
                self,
                "Queue application",
                "Only vacancies currently classified as REVIEW can be queued manually.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Queue application",
            "Queue this REVIEW vacancy for application preparation on the next run?\n\n"
            "The agent will re-check strong evidence, location and experience blockers. "
            "Final employer Submit will still require your manual action.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        write_job_override(
            str(record.get("job_id", "")),
            "MANUAL_APPLY",
        )
        self._refresh_dashboard()
        self._append_log(
            f"Manual queue: {record.get('title', '')} → next-run preparation"
        )

    def _prepare_selected_now(self):
        if self.agent_process and self.agent_process.is_alive():
            QMessageBox.information(
                self,
                "Prepare now",
                "Stop the current Job Agent run first.",
            )
            return

        record = self._selected_dashboard_record()
        if not record:
            return

        if not self._application_source_supported(record):
            QMessageBox.information(
                self,
                "Discovery-only source",
                "Prepare now is not enabled for StartupJobs.cz yet. "
                "Use Open job to review and apply manually.",
            )
            return

        status = str(record.get("status", "")).upper().strip()
        if status in TERMINAL_STATUSES or vacancy_already_submitted(record):
            QMessageBox.information(
                self,
                "Prepare now",
                "This vacancy already has a confirmed submission in local history. "
                "Prepare now is blocked to prevent a duplicate application.",
            )
            return

        try:
            score = int(float(record.get("score", 0) or 0))
        except Exception:
            score = 0

        overrides = load_job_overrides()
        override = str(
            overrides.get(str(record.get("job_id", "")), {}).get(
                "decision", ""
            )
        ).upper().strip()
        decision = str(record.get("decision", "")).upper().strip()

        allowed = decision == "APPLY" or override == "MANUAL_APPLY"
        if decision == "REVIEW":
            allowed = True

        if not allowed:
            QMessageBox.information(
                self,
                "Prepare now",
                "Prepare now is available for APPLY or REVIEW jobs. "
                "The agent will re-check the vacancy before opening the form.",
            )
            return

        settings = self._collect_settings()
        error = self._validate_settings(settings, require_application=True)
        if error:
            QMessageBox.warning(self, "Job Agent", error)
            return

        if not playwright_browser_present():
            QMessageBox.warning(
                self,
                "Playwright Chromium missing",
                "Playwright Chromium is not installed in the external browser cache.\n\n"
                f"Run this once in Terminal:\n\n{playwright_install_command()}",
            )
            return

        reply = QMessageBox.question(
            self,
            "Prepare now",
            "Prepare only this vacancy now?\n\n"
            "The agent will re-check score, strong evidence, location and "
            "experience blockers, then fill supported fields and stop before "
            "the employer's final Submit button.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        save_settings(settings)
        self.settings = settings
        self.log_queue = mp.get_context("spawn").Queue()
        self.agent_process = mp.get_context("spawn").Process(
            target=prepare_job_worker,
            args=(settings, dict(record), self.log_queue),
            daemon=False,
        )
        self.agent_process.start()
        self.run_started_at = time.time()
        self._set_running(True)
        self.workspace_tabs.setCurrentIndex(2)
        self._append_log("")
        self._append_log("═" * 72)
        self._append_log(
            f"Prepare now: {record.get('title', 'selected vacancy')}"
        )
        self._append_log("═" * 72)

    def _clear_selected_override(self):
        record = self._selected_dashboard_record()
        if not record:
            return
        jid = str(record.get("job_id", "")).strip()
        if delete_job_override(jid):
            self._append_log(
                f"Dashboard override cleared: {record.get('title', '')}"
            )
            self._refresh_dashboard()
        else:
            QMessageBox.information(
                self,
                "Clear override",
                "This vacancy has no Dashboard override.",
            )

    def _delete_selected_vacancy(self):
        record = self._selected_dashboard_record()
        if not record:
            return
        if self.agent_process and self.agent_process.is_alive():
            QMessageBox.warning(self, "Удаление", "Дождись завершения поиска.")
            return
        jid = canonical_local_job_id(record.get("job_id", ""), record.get("url", ""))
        if protected_vacancy(record, load_job_overrides(), terminal_job_ids()):
            QMessageBox.information(
                self, "Удаление", "Отправленные, избранные и стоящие в очереди вакансии защищены от удаления."
            )
            return
        answer = QMessageBox.question(
            self, "Удалить запись из базы?",
            f"Удалить «{record.get('title', '')}» из локальной базы?\n\n"
            "История откликов сохранится. Создаётся резервная копия вакансий. "
            "Вакансия не вернётся при следующем поиске. "
            "Для восстановления удалённой записи понадобится резервная копия.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            hidden, rows, backup = purge_vacancy_records({jid})
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Удаление не выполнено", str(exc))
            return
        self._append_log(f"Удалена вакансия: {jid}; строк={rows}; backup={backup or '—'}")
        self._refresh_dashboard()
        QMessageBox.information(self, "Удалено", f"Удалено из базы: {hidden}. Резервная копия: {backup or 'нет'}")

    def _cleanup_old_vacancies(self):
        if self.agent_process and self.agent_process.is_alive():
            QMessageBox.warning(self, "Очистка", "Дождись завершения поиска.")
            return
        choices = ["Старше 30 дней", "Старше 60 дней", "Старше 90 дней", "Старше 180 дней"]
        selected, ok = QInputDialog.getItem(
            self, "Очистка старых вакансий", "Удалить локальные записи:", choices, 2, False,
        )
        if not ok:
            return
        days = [30, 60, 90, 180][choices.index(selected)]
        records = load_vacancy_records()
        overrides = load_job_overrides()
        submitted = terminal_job_ids()
        ids = old_vacancy_ids(records, days, overrides=overrides, submitted_ids=submitted)
        if not ids:
            QMessageBox.information(
                self, "Очистка", "Подходящих старых вакансий нет. Записи без даты сохраняются."
            )
            return
        protected_count = sum(protected_vacancy(r, overrides, submitted) for r in records)
        answer = QMessageBox.question(
            self, "Подтвердить очистку",
            f"Найдено {len(ids)} вакансий старше {days} дней.\n"
            f"Защищено от удаления: {protected_count}.\n\n"
            "Будут удалены только сохранённые записи вакансий. "
            "История откликов не изменится. Создаётся резервная копия. "
            "Удалённые вакансии не вернутся после поиска, а их восстановление "
            "потребует резервной копии. Продолжить?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            hidden, rows, backup = purge_vacancy_records(ids)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Ошибка очистки", str(exc))
            return
        self._refresh_dashboard()
        self._append_log(f"Очистка > {days} дней: вакансий={hidden}, строк={rows}, backup={backup or '—'}")
        QMessageBox.information(
            self, "Очистка завершена",
            f"Удалено вакансий: {hidden}\nСтрок снимков: {rows}\n"
            f"Резервная копия: {backup or 'нет'}",
        )

    def _archive_selected_vacancy(self):
        record = self._selected_dashboard_record()
        if not record:
            return
        reply = QMessageBox.question(
            self, "Неактивная вакансия",
            "Скрыть вакансию из поиска и активного списка? История откликов сохранится.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        write_job_override(str(record.get("job_id", "")), "INACTIVE")
        self._refresh_dashboard()

    def _restore_selected_vacancy(self):
        record = self._selected_dashboard_record()
        if not record:
            return
        jid = str(record.get("job_id", ""))
        if str(load_job_overrides().get(jid, {}).get("decision", "")).upper() != "INACTIVE":
            return
        delete_job_override(jid)
        self._refresh_dashboard()

    def _set_selected_override(self, decision):
        record = self._selected_dashboard_record()
        if not record:
            return
        write_job_override(
            str(record.get("job_id", "")),
            str(decision).upper(),
        )
        self._refresh_dashboard()
        self._append_log(
            f"Dashboard override: {record.get('title', '')} → {decision}"
        )

    def _show_selected_cover_letter(self):
        record = self._selected_dashboard_record()
        if not record:
            return
        letter = str(record.get("cover_letter", "")).strip()
        if not letter:
            QMessageBox.information(
                self,
                "Cover letter",
                "No saved cover letter is available for this vacancy yet.",
            )
            return
        self.dashboard_detail.setPlainText(letter)

    def _copy_selected_cover_letter(self):
        record = self._selected_dashboard_record()
        if not record:
            return
        letter = str(record.get("cover_letter", "")).strip()
        if not letter:
            QMessageBox.information(
                self,
                "Cover letter",
                "No saved cover letter is available for this vacancy yet.",
            )
            return
        QApplication.clipboard().setText(letter)
        self._append_log(
            f"Cover letter copied: {record.get('title', '')}"
        )

    def _score_spin(self):
        w = QSpinBox()
        w.setRange(0, 100)
        return w

    def _load_widgets(self):
        s = self.settings
        self.first_name_edit.setText(str(s.get("first_name", "")))
        self.last_name_edit.setText(str(s.get("last_name", "")))
        self.email_edit.setText(str(s.get("email", "")))
        self.phone_edit.setText(str(s.get("phone", "")))

        self.search_only_check.setChecked(bool(s.get("search_only", True)))
        self.jobs_check.setChecked(bool(s["source_jobs"]))
        self.prace_check.setChecked(bool(s["source_prace"]))
        self.startupjobs_check.setChecked(bool(s.get("source_startupjobs", True)))
        self.prague_check.setChecked(bool(s["prague_only"]))
        self.browser_check.setChecked(bool(s["browser_evidence"]))
        self.cover_check.setChecked(bool(s["czech_cover_letter"]))

        self.max_apps_spin.setValue(int(s["max_applications"]))
        self.apply_spin.setValue(int(s["min_apply"]))
        self.verified_spin.setValue(int(s["verified_apply"]))
        self.entry_spin.setValue(int(s["entry_apply"]))
        self.expanded_spin.setValue(int(s["expanded_apply"]))
        self.review_spin.setValue(int(s["review"]))
        self.manual_queue_spin.setValue(int(s["manual_queue_min"]))

        self.cv_edit.setText(str(s["cv_path"]))
        self.profile_edit.setText(str(s["browser_profile"]))
        self.channel_combo.setCurrentText(
            str(s.get("update_channel", APP_CHANNEL))
        )

        manifest_url = str(s.get("update_manifest_url", "")).strip()
        if not manifest_url:
            manifest_url = DEFAULT_UPDATE_MANIFEST_URL
        self.manifest_edit.setText(manifest_url)

        self.auto_update_check.setChecked(
            bool(s.get("auto_check_updates", True))
        )

    def _persist_update_channel(self, channel):
        channel = str(channel or "").strip().lower()
        if channel not in {"stable", "beta"}:
            return
        self.settings["update_channel"] = channel
        self.settings["update_channel_explicit"] = True
        try:
            save_settings(self.settings)
        except Exception:
            pass

    def _collect_settings(self):
        return {
            "first_name": self.first_name_edit.text().strip(),
            "last_name": self.last_name_edit.text().strip(),
            "email": self.email_edit.text().strip(),
            "phone": self.phone_edit.text().strip(),
            "search_only": self.search_only_check.isChecked(),
            "source_jobs": self.jobs_check.isChecked(),
            "source_prace": self.prace_check.isChecked(),
            "source_startupjobs": self.startupjobs_check.isChecked(),
            "prague_only": self.prague_check.isChecked(),
            "browser_evidence": self.browser_check.isChecked(),
            "czech_cover_letter": self.cover_check.isChecked(),
            "max_applications": self.max_apps_spin.value(),
            "min_apply": self.apply_spin.value(),
            "verified_apply": self.verified_spin.value(),
            "entry_apply": self.entry_spin.value(),
            "expanded_apply": self.expanded_spin.value(),
            "review": self.review_spin.value(),
            "manual_queue_min": self.manual_queue_spin.value(),
            "cv_path": self.cv_edit.text().strip(),
            "browser_profile": self.profile_edit.text().strip(),
            "update_channel": self.channel_combo.currentText().strip(),
            "update_channel_explicit": bool(
                self.settings.get("update_channel_explicit", False)
            ),
            "update_manifest_url": (
                self.manifest_edit.text().strip()
                or DEFAULT_UPDATE_MANIFEST_URL
            ),
            "auto_check_updates": self.auto_update_check.isChecked(),
        }

    def _validate_settings(self, s, require_application=None):
        if require_application is None:
            require_application = not s.get("search_only", True)
        required = {
            "First name": s.get("first_name", ""),
            "Last name": s.get("last_name", ""),
            "Email": s.get("email", ""),
            "Phone": s.get("phone", ""),
        }
        missing = [
            label for label, value in required.items()
            if not str(value).strip()
        ]
        if require_application and missing:
            return "Complete the Profile tab first: " + ", ".join(missing)

        if not any([
            s["source_jobs"],
            s["source_prace"],
            s["source_startupjobs"],
        ]):
            return "Enable at least one source."

        cv = Path(s["cv_path"]).expanduser()
        if require_application and not cv.is_file():
            return f"CV file does not exist:\n{cv}"

        if s["review"] > s["min_apply"]:
            return "REVIEW threshold should not exceed target APPLY threshold."

        return ""

    def _browse_cv(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose CV",
            str(Path.home()),
            "PDF files (*.pdf);;All files (*)",
        )
        if path:
            self.cv_edit.setText(path)

    def _browse_profile(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "Choose browser profile directory",
            self.profile_edit.text() or str(Path.home()),
        )
        if path:
            self.profile_edit.setText(path)

    def _append_log(self, text):
        if text is None:
            return
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(str(text) + "\n")
        self.log.setTextCursor(cursor)
        line = str(text).strip().splitlines()
        if line:
            self.latest_log.setText(line[-1])
            self.latest_log.setToolTip(line[-1])
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def start_agent(self):
        if self.agent_process and self.agent_process.is_alive():
            return

        settings = self._collect_settings()
        error = self._validate_settings(settings)
        if error:
            QMessageBox.warning(self, "Job Agent", error)
            return

        if not playwright_browser_present():
            QMessageBox.warning(
                self,
                "Playwright Chromium missing",
                "Playwright Chromium is not installed in the external browser cache.\n\n"
                f"Expected location:\n{PLAYWRIGHT_BROWSERS_DIR}\n\n"
                "Run this once in Terminal:\n\n"
                f"{playwright_install_command()}",
            )
            return

        save_settings(settings)
        self.settings = settings

        self.log_queue = mp.get_context("spawn").Queue()
        self.agent_process = mp.get_context("spawn").Process(
            target=agent_worker,
            args=(settings, self.log_queue),
            daemon=False,
        )
        self.agent_process.start()
        self.run_started_at = time.time()

        self._set_running(True)
        self._append_log("")
        self._append_log("═" * 72)
        self._append_log("Starting Job Agent…")
        self._append_log("═" * 72)

    def stop_agent(self):
        proc = self.agent_process
        if not proc or not proc.is_alive():
            self._set_running(False)
            return

        self.status_label.setText("● Остановка…")
        self.status_label.setStyleSheet(
            "font-weight: 700; font-size: 15px; color: #a06000;"
        )
        self._append_log("🛑 Stop requested by user.")

        try:
            if os.name != "nt":
                os.killpg(proc.pid, signal.SIGTERM)
            else:
                proc.terminate()
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

        proc.join(timeout=3)
        if proc.is_alive():
            try:
                proc.kill()
            except Exception:
                pass

        self._set_running(False)
        self._append_log("■ Agent stopped.")

    def _set_running(self, running):
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.stop_btn.setVisible(running)
        self.search_only_check.setEnabled(not running)
        if hasattr(self, "prepare_now_btn"):
            self.prepare_now_btn.setEnabled(not running)

        if running:
            self.status_label.setText("●")
            self.status_label.setToolTip("Поиск идёт")
            self.journal_header.setText("Журнал запуска · поиск идёт")
            self.status_label.setStyleSheet(
                "font-weight: 700; font-size: 15px; color: #1f6fbd;"
            )
        else:
            self.status_label.setText("●")
            self.status_label.setToolTip("Готов к поиску")
            self.journal_header.setText("Журнал запуска")
            self.status_label.setStyleSheet(
                "font-weight: 700; font-size: 15px; color: #227722;"
            )
            self.run_started_at = None
        self._dashboard_selection_changed()

    def _poll_queue(self):
        if self.log_queue:
            while True:
                try:
                    kind, payload = self.log_queue.get_nowait()
                except queue.Empty:
                    break
                except Exception:
                    break

                if kind == "log":
                    self._append_log(payload)
                elif kind == "finished":
                    code = int(payload)
                    if code == 0:
                        self._append_log("✅ Run finished.")
                    else:
                        self._append_log(
                            f"⚠️ Agent process exited with code {code}."
                        )
                    self._set_running(False)
                    self._refresh_stats()

        if (
            self.agent_process
            and not self.agent_process.is_alive()
            and self.start_btn.isEnabled() is False
        ):
            self._set_running(False)
            self._refresh_stats()


    def check_for_updates(self, silent=False):
        url = self.manifest_edit.text().strip()
        channel = self.channel_combo.currentText().strip() or "stable"

        if not url:
            if not silent:
                QMessageBox.information(
                    self,
                    "Updates",
                    "No update manifest URL is configured.",
                )
            return

        self.available_update = None
        self.install_update_btn.setEnabled(False)
        self.check_update_btn.setEnabled(False)
        self.update_status.setText("Checking for updates…")
        self.update_notes.clear()

        self.update_thread = QThread(self)
        self.update_worker = UpdateCheckWorker(url, channel, APP_VERSION)
        self.update_worker.moveToThread(self.update_thread)
        self.update_thread.started.connect(self.update_worker.run)
        self.update_worker.finished.connect(self._update_check_done)
        self.update_worker.finished.connect(self.update_thread.quit)
        self.update_thread.start()

    @Slot(object, object)
    def _update_check_done(self, payload, error):
        self.check_update_btn.setEnabled(True)

        if error:
            self.update_status.setText(f"Update check failed: {error}")
            return

        self.available_update = payload
        self.update_notes.setPlainText(payload.get("notes", ""))

        if payload.get("is_newer"):
            self.update_status.setText(
                f"Update available: {payload['version']} ({payload['channel']})"
            )
            self.install_update_btn.setEnabled(True)
        else:
            self.update_status.setText(
                f"Up to date • Job Agent {APP_VERSION} • "
                f"{payload['channel']} channel"
            )

    def install_update(self):
        if not self.available_update:
            return

        if self.agent_process and self.agent_process.is_alive():
            QMessageBox.warning(
                self,
                "Updates",
                "Stop the current Job Agent run before installing an update.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Install update",
            f"Install Job Agent {self.available_update['version']}?\n\n"
            "Settings and application history will be backed up first.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.install_update_btn.setEnabled(False)
        self.check_update_btn.setEnabled(False)
        self.update_progress.setValue(0)
        self.update_progress.show()
        self.update_status.setText("Downloading update…")

        self.update_thread = QThread(self)
        self.update_worker = UpdateDownloadWorker(self.available_update)
        self.update_worker.moveToThread(self.update_thread)
        self.update_thread.started.connect(self.update_worker.run)
        self.update_worker.progress.connect(self.update_progress.setValue)
        self.update_worker.finished.connect(self._update_download_done)
        self.update_worker.finished.connect(self.update_thread.quit)
        self.update_thread.start()

    @Slot(object, object)
    def _update_download_done(self, path, error):
        self.check_update_btn.setEnabled(True)

        if error:
            self.update_progress.hide()
            self.update_status.setText(f"Update download failed: {error}")
            self.install_update_btn.setEnabled(True)
            return

        self.update_status.setText("Update downloaded and verified.")

        try:
            from updater import stage_install
            stage_install(Path(path), relaunch=True)
        except Exception as exc:
            self.update_progress.hide()
            self.install_update_btn.setEnabled(True)
            QMessageBox.warning(
                self,
                "Update downloaded",
                f"The update was downloaded successfully, but automatic "
                f"installation is unavailable:\n\n{type(exc).__name__}: {exc}\n\n"
                f"Downloaded file:\n{path}",
            )
            return

        QMessageBox.information(
            self,
            "Installing update",
            "The update has been verified and staged.\n\n"
            "Job Agent will close, replace the app, and relaunch.",
        )
        QApplication.quit()

    def _refresh_source_status(self):
        try:
            data = json.loads((HISTORY_FILE.parent / "discovery_status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        running = bool(self.agent_process and self.agent_process.is_alive())
        for name, label in self.source_badges.items():
            info = data.get("sources", {}).get(name, {})
            status = info.get("status", "unknown")
            count = info.get("count", 0)
            caption = {"ok": f"{count} найдено", "partial": f"{count} · есть ошибки", "empty": "0 · нужна проверка", "error": "ошибка загрузки", "disabled": "выключен", "searching": "поиск…" if running else "не завершён", "unknown": "не проверен"}.get(status, "нужна проверка")
            color = "#33a129" if status == "ok" else "#efa216" if status in {"partial", "empty", "error"} else "#6b7990"
            label.setText(f'<span style="color:{color};font-size:19px;">●</span> &nbsp; <b>{SOURCE_NAMES[name]}</b> &nbsp; <span style="color:#69758d;">{escape(caption)}</span>')
            details = "\n".join(info.get("details", []))
            label.setToolTip("Последний поиск: " + data.get("saved_at", "—") + ("\n" + details if details else ""))

    def _refresh_stats(self):
        self.processed_value.setText(str(processed_count()))
        self._refresh_dashboard()
        self._refresh_source_status()
        if playwright_browser_present():
            self.browser_status_value.setText("Ready")
            self.browser_status_value.setStyleSheet("color: #227722; font-weight: 700;")
        else:
            self.browser_status_value.setText("Missing")
            self.browser_status_value.setStyleSheet("color: #aa2222; font-weight: 700;")

        if self.run_started_at:
            elapsed = int(time.time() - self.run_started_at)
            mm, ss = divmod(elapsed, 60)
            self.run_time_value.setText(f"{mm:02d}:{ss:02d}")
        else:
            self.run_time_value.setText("—")

    def closeEvent(self, event):
        if self.agent_process and self.agent_process.is_alive():
            reply = QMessageBox.question(
                self,
                "Job Agent",
                "The agent is still running. Stop it and close the app?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            self.stop_agent()

        try:
            save_settings(self._collect_settings())
        except Exception:
            pass

        event.accept()


def main():
    mp.freeze_support()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Job Agent")

    window = JobAgentWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

