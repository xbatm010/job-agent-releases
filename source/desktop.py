import csv
import io
import json
import multiprocessing as mp
import os
import queue
import signal
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal, QThread, QObject, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QProgressBar,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
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
        return {"app_name": "Job Agent Desktop", "version": "2.1.1", "channel": "stable"}

VERSION_INFO = None
APP_VERSION = "2.1.1"
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


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


VERSION_INFO = load_version_info()
APP_VERSION = str(VERSION_INFO.get("version", "2.0.0"))

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
    "source_jobs": True,
    "source_prace": True,
    "max_applications": 3,
    "min_apply": 73,
    "verified_apply": 70,
    "entry_apply": 68,
    "expanded_apply": 74,
    "review": 60,
    "browser_evidence": True,
    "czech_cover_letter": True,
    "prague_only": True,
    "cv_path": "",
    "first_name": "",
    "last_name": "",
    "email": "",
    "phone": "",
    "browser_profile": detect_legacy_profile(),
    "update_channel": "stable",
    "update_manifest_url": DEFAULT_UPDATE_MANIFEST_URL,
    "auto_check_updates": True,
}


def load_settings() -> dict:
    data = dict(DEFAULTS)
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                data.update(saved)
        except Exception:
            pass
    return data


def save_settings(data: dict) -> None:
    SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def processed_count() -> int:
    if not HISTORY_FILE.exists():
        return 0

    unique = set()
    try:
        with HISTORY_FILE.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("status") not in TERMINAL_STATUSES:
                    continue
                jid = (row.get("job_id") or "").strip()
                if jid:
                    unique.add(jid)
    except Exception:
        return 0
    return len(unique)


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
        "SOURCE_JOBS_CZ": str(settings["source_jobs"]).lower(),
        "SOURCE_PRACE_CZ": str(settings["source_prace"]).lower(),
        "MAX_APPLICATIONS_PER_RUN": str(settings["max_applications"]),
        "MIN_APPLY_SCORE": str(settings["min_apply"]),
        "VERIFIED_TARGET_APPLY_SCORE": str(settings["verified_apply"]),
        "ENTRY_APPLY_SCORE": str(settings["entry_apply"]),
        "EXPANDED_APPLY_SCORE": str(settings["expanded_apply"]),
        "MIN_REVIEW_SCORE": str(settings["review"]),
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

        # v52 discovery defaults.
        "MAX_DISCOVERY_PER_SOURCE": "80",
        "MAX_BROWSER_EVIDENCE_JOBS": "10",
        "MAX_JOBS_TO_REVIEW": "24",
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
        if not cv.exists():
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
        self.resize(1050, 760)
        self.settings = load_settings()

        self.log_queue = None
        self.agent_process = None
        self.run_started_at = None
        self.update_thread = None
        self.update_worker = None
        self.available_update = None

        self._build_ui()
        self._load_widgets()

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

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)

        header = QHBoxLayout()
        title_box = QVBoxLayout()

        title = QLabel("Job Agent")
        f = QFont()
        f.setPointSize(22)
        f.setBold(True)
        title.setFont(f)

        subtitle = QLabel(
            f"v{APP_VERSION} • Jobs.cz + Prace.cz • Prague filter • Czech cover letters"
        )
        subtitle.setStyleSheet("color: #666;")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        self.status_label = QLabel("● Ready")
        self.status_label.setStyleSheet(
            "font-weight: 700; font-size: 15px; color: #227722;"
        )
        header.addWidget(self.status_label)
        outer.addLayout(header)

        safety = QLabel(
            "🔒 Final employer Submit is locked to manual confirmation."
        )
        safety.setStyleSheet(
            "padding: 9px; border: 1px solid #d8d8d8; "
            "border-radius: 7px; background: #f7f7f7;"
        )
        outer.addWidget(safety)

        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)

        stats = QGroupBox("Overview")
        stats_grid = QGridLayout(stats)
        self.processed_value = QLabel("0")
        self.run_time_value = QLabel("—")
        self.browser_status_value = QLabel("Checking…")
        stats_grid.addWidget(QLabel("Confirmed applications"), 0, 0)
        stats_grid.addWidget(self.processed_value, 0, 1)
        stats_grid.addWidget(QLabel("Current run"), 1, 0)
        stats_grid.addWidget(self.run_time_value, 1, 1)
        stats_grid.addWidget(QLabel("Playwright Chromium"), 2, 0)
        stats_grid.addWidget(self.browser_status_value, 2, 1)
        left_layout.addWidget(stats)

        tabs = QTabWidget()
        left_layout.addWidget(tabs, 1)

        profile_tab = QWidget()
        profile_layout = QFormLayout(profile_tab)
        self.first_name_edit = QLineEdit()
        self.last_name_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        profile_layout.addRow("First name", self.first_name_edit)
        profile_layout.addRow("Last name", self.last_name_edit)
        profile_layout.addRow("Email", self.email_edit)
        profile_layout.addRow("Phone", self.phone_edit)

        profile_note = QLabel(
            "Personal profile data and the CV path stay on this Mac. "
            "They are not stored in the public GitHub source repository."
        )
        profile_note.setWordWrap(True)
        profile_note.setStyleSheet("color: #666;")
        profile_layout.addRow(profile_note)
        tabs.addTab(profile_tab, "Profile")

        search_tab = QWidget()
        search_layout = QFormLayout(search_tab)

        self.jobs_check = QCheckBox("Jobs.cz")
        self.prace_check = QCheckBox("Prace.cz")
        src_row = QWidget()
        src_l = QHBoxLayout(src_row)
        src_l.setContentsMargins(0, 0, 0, 0)
        src_l.addWidget(self.jobs_check)
        src_l.addWidget(self.prace_check)
        src_l.addStretch()
        search_layout.addRow("Sources", src_row)

        self.prague_check = QCheckBox("Praha + allowed surroundings")
        search_layout.addRow("Location", self.prague_check)

        self.browser_check = QCheckBox("Render weak jobs in Chromium")
        search_layout.addRow("Evidence", self.browser_check)

        self.cover_check = QCheckBox("Write Průvodní dopis in Czech")
        search_layout.addRow("Cover letter", self.cover_check)

        self.max_apps_spin = QSpinBox()
        self.max_apps_spin.setRange(1, 5)
        search_layout.addRow("Applications / run", self.max_apps_spin)

        tabs.addTab(search_tab, "Search")

        scoring_tab = QWidget()
        scoring_layout = QFormLayout(scoring_tab)

        self.apply_spin = self._score_spin()
        self.verified_spin = self._score_spin()
        self.entry_spin = self._score_spin()
        self.expanded_spin = self._score_spin()
        self.review_spin = self._score_spin()

        scoring_layout.addRow("Target APPLY ≥", self.apply_spin)
        scoring_layout.addRow("Verified target ≥", self.verified_spin)
        scoring_layout.addRow("Junior / Intern ≥", self.entry_spin)
        scoring_layout.addRow("Expanded role ≥", self.expanded_spin)
        scoring_layout.addRow("REVIEW ≥", self.review_spin)
        tabs.addTab(scoring_tab, "Scoring")

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
        tabs.addTab(paths_tab, "Files")

        updates_tab = QWidget()
        updates_layout = QVBoxLayout(updates_tab)

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

        tabs.addTab(updates_tab, "Updates")

        button_row = QHBoxLayout()
        self.start_btn = QPushButton("▶ Start Search")
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setEnabled(False)

        self.start_btn.setMinimumHeight(40)
        self.stop_btn.setMinimumHeight(40)

        self.start_btn.clicked.connect(self.start_agent)
        self.stop_btn.clicked.connect(self.stop_agent)

        button_row.addWidget(self.start_btn, 2)
        button_row.addWidget(self.stop_btn, 1)
        left_layout.addLayout(button_row)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        log_header = QHBoxLayout()
        log_title = QLabel("Live log")
        lf = QFont()
        lf.setBold(True)
        log_title.setFont(lf)
        log_header.addWidget(log_title)
        log_header.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self.log.clear())
        log_header.addWidget(clear_btn)
        right_layout.addLayout(log_header)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(11)
        self.log.setFont(mono)
        right_layout.addWidget(self.log, 1)

        splitter.addWidget(right)
        splitter.setSizes([390, 660])

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

        self.jobs_check.setChecked(bool(s["source_jobs"]))
        self.prace_check.setChecked(bool(s["source_prace"]))
        self.prague_check.setChecked(bool(s["prague_only"]))
        self.browser_check.setChecked(bool(s["browser_evidence"]))
        self.cover_check.setChecked(bool(s["czech_cover_letter"]))

        self.max_apps_spin.setValue(int(s["max_applications"]))
        self.apply_spin.setValue(int(s["min_apply"]))
        self.verified_spin.setValue(int(s["verified_apply"]))
        self.entry_spin.setValue(int(s["entry_apply"]))
        self.expanded_spin.setValue(int(s["expanded_apply"]))
        self.review_spin.setValue(int(s["review"]))

        self.cv_edit.setText(str(s["cv_path"]))
        self.profile_edit.setText(str(s["browser_profile"]))
        self.channel_combo.setCurrentText(str(s.get("update_channel", "stable")))

        manifest_url = str(s.get("update_manifest_url", "")).strip()
        if not manifest_url:
            manifest_url = DEFAULT_UPDATE_MANIFEST_URL
        self.manifest_edit.setText(manifest_url)

        self.auto_update_check.setChecked(
            bool(s.get("auto_check_updates", True))
        )

    def _collect_settings(self):
        return {
            "first_name": self.first_name_edit.text().strip(),
            "last_name": self.last_name_edit.text().strip(),
            "email": self.email_edit.text().strip(),
            "phone": self.phone_edit.text().strip(),
            "source_jobs": self.jobs_check.isChecked(),
            "source_prace": self.prace_check.isChecked(),
            "prague_only": self.prague_check.isChecked(),
            "browser_evidence": self.browser_check.isChecked(),
            "czech_cover_letter": self.cover_check.isChecked(),
            "max_applications": self.max_apps_spin.value(),
            "min_apply": self.apply_spin.value(),
            "verified_apply": self.verified_spin.value(),
            "entry_apply": self.entry_spin.value(),
            "expanded_apply": self.expanded_spin.value(),
            "review": self.review_spin.value(),
            "cv_path": self.cv_edit.text().strip(),
            "browser_profile": self.profile_edit.text().strip(),
            "update_channel": self.channel_combo.currentText().strip(),
            "update_manifest_url": (
                self.manifest_edit.text().strip()
                or DEFAULT_UPDATE_MANIFEST_URL
            ),
            "auto_check_updates": self.auto_update_check.isChecked(),
        }

    def _validate_settings(self, s):
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
        if missing:
            return "Complete the Profile tab first: " + ", ".join(missing)

        if not s["source_jobs"] and not s["source_prace"]:
            return "Enable at least one source."

        cv = Path(s["cv_path"]).expanduser()
        if not cv.exists():
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
        self.log.append(str(text))
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

        self.status_label.setText("● Stopping…")
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

        if running:
            self.status_label.setText("● Running")
            self.status_label.setStyleSheet(
                "font-weight: 700; font-size: 15px; color: #1f6fbd;"
            )
        else:
            self.status_label.setText("● Ready")
            self.status_label.setStyleSheet(
                "font-weight: 700; font-size: 15px; color: #227722;"
            )
            self.run_started_at = None

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

    def _refresh_stats(self):
        self.processed_value.setText(str(processed_count()))
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
