
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import ssl
import certifi
import zipfile
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Job Agent"
APP_SUPPORT = Path.home() / "Library" / "Application Support" / APP_NAME
BACKUP_DIR = APP_SUPPORT / "backups"
DOWNLOAD_DIR = APP_SUPPORT / "updates"
SETTINGS_FILE = APP_SUPPORT / "settings.json"
HISTORY_FILE = Path.home() / ".job_agent" / "applications.csv"

BACKUP_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def ssl_context():
    """
    Use certifi's bundled Mozilla CA store explicitly.

    PyInstaller macOS apps cannot always rely on the system/Python framework
    certificate paths, which can lead to CERTIFICATE_VERIFY_FAILED.
    """
    return ssl.create_default_context(cafile=certifi.where())



def parse_version(v: str):
    out = []
    for part in (v or "0").split("."):
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        out.append(int(digits or 0))
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


@dataclass
class UpdateInfo:
    version: str
    channel: str
    url: str
    sha256: str
    notes: str
    min_version: str = ""


def read_manifest(url: str, channel: str, timeout=12):
    if not url:
        raise ValueError("Update manifest URL is not configured.")

    req = urllib.request.Request(url, headers={"User-Agent": "JobAgentDesktop/2.8.1"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    selected = (payload.get("releases") or {}).get(channel)
    if not selected:
        return None

    return UpdateInfo(
        version=str(selected.get("version", "")).strip(),
        channel=channel,
        url=str(selected.get("url", "")).strip(),
        sha256=str(selected.get("sha256", "")).strip().lower(),
        notes=str(selected.get("notes", "")).strip(),
        min_version=str(selected.get("min_version", "")).strip(),
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_update(info: UpdateInfo, progress_cb=None) -> Path:
    if not info.url:
        raise ValueError("Release URL is missing in update manifest.")

    target = DOWNLOAD_DIR / f"job-agent-{info.version}.zip"
    temp = target.with_suffix(".download")

    req = urllib.request.Request(info.url, headers={"User-Agent": "JobAgentDesktop/2.8.1"})
    with urllib.request.urlopen(req, timeout=30, context=ssl_context()) as resp, temp.open("wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            block = resp.read(1024 * 256)
            if not block:
                break
            fh.write(block)
            done += len(block)
            if progress_cb and total:
                progress_cb(min(100, int(done * 100 / total)))

    temp.replace(target)

    if info.sha256:
        actual = sha256_file(target)
        if actual.lower() != info.sha256.lower():
            target.unlink(missing_ok=True)
            raise ValueError(
                "Downloaded update failed SHA-256 verification.\n"
                f"Expected: {info.sha256}\nActual: {actual}"
            )

    if progress_cb:
        progress_cb(100)
    return target


def backup_user_data() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / stamp
    dest.mkdir(parents=True, exist_ok=True)

    if SETTINGS_FILE.exists():
        shutil.copy2(SETTINGS_FILE, dest / "settings.json")
    if HISTORY_FILE.exists():
        shutil.copy2(HISTORY_FILE, dest / "applications.csv")

    (dest / "backup.json").write_text(
        json.dumps({"created_at": stamp}, indent=2),
        encoding="utf-8",
    )
    return dest


def current_app_bundle():
    exe = Path(sys.executable).resolve()
    for idx, part in enumerate(exe.parts):
        if part.endswith(".app"):
            return Path(*exe.parts[: idx + 1])
    return None


def find_app_in_zip(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as z:
        apps = []
        for name in z.namelist():
            parts = Path(name).parts
            for idx, part in enumerate(parts):
                if part.endswith(".app"):
                    apps.append("/".join(parts[: idx + 1]))
                    break
    if not apps:
        raise ValueError("Update ZIP does not contain a macOS .app bundle.")
    apps.sort(key=lambda x: len(Path(x).parts))
    return apps[0]


def extract_app(zip_path: Path) -> Path:
    """
    Extract a macOS .app without destroying symlinks/framework layout.

    Python's zipfile extractor does not faithfully preserve all macOS bundle
    metadata and symlink semantics. Update archives are created with ditto, so
    on macOS they must also be extracted with ditto.
    """
    app_entry = find_app_in_zip(zip_path)
    temp_root = Path(tempfile.mkdtemp(prefix="job-agent-update-"))

    if sys.platform == "darwin":
        subprocess.run(
            ["/usr/bin/ditto", "-x", "-k", str(zip_path), str(temp_root)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    else:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(temp_root)

    app_path = temp_root / app_entry
    if not app_path.exists() or not app_path.is_dir():
        raise ValueError("Failed to extract .app bundle.")
    return app_path


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def create_install_helper(new_app: Path, current_app: Path, relaunch=True) -> Path:
    helper = DOWNLOAD_DIR / "install_update.command"
    backup_app = current_app.with_name(current_app.name + ".previous")

    relaunch_line = f"open {sh_quote(str(current_app))}" if relaunch else ":"
    script = f"""#!/bin/bash
set -euo pipefail
PID="{os.getpid()}"
NEW_APP={sh_quote(str(new_app))}
CURRENT_APP={sh_quote(str(current_app))}
BACKUP_APP={sh_quote(str(backup_app))}

for i in $(seq 1 60); do
  if ! kill -0 "$PID" 2>/dev/null; then
    break
  fi
  sleep 0.5
done

rm -rf "$BACKUP_APP" || true
if [ -d "$CURRENT_APP" ]; then
  mv "$CURRENT_APP" "$BACKUP_APP"
fi

if mv "$NEW_APP" "$CURRENT_APP"; then
  :
else
  if [ -d "$BACKUP_APP" ]; then
    mv "$BACKUP_APP" "$CURRENT_APP"
  fi
  exit 1
fi

xattr -dr com.apple.quarantine "$CURRENT_APP" 2>/dev/null || true
{relaunch_line}
"""
    helper.write_text(script, encoding="utf-8")
    helper.chmod(0o755)
    return helper


def stage_install(zip_path: Path, relaunch=True):
    current = current_app_bundle()
    if current is None:
        raise RuntimeError(
            "Automatic install is only available when running from a built macOS .app."
        )

    backup_user_data()
    new_app = extract_app(zip_path)
    helper = create_install_helper(new_app, current, relaunch=relaunch)

    subprocess.Popen(
        ["/bin/bash", str(helper)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return helper, current
