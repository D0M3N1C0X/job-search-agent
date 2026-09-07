"""Make the dashboard reachable without a terminal.

The pipeline is a CLI, but the dashboard is something you open ten times a
week — and `cd`-ing to a repository to type a command is enough friction to
stop you opening it at all. This builds a real macOS application: click the
Dock icon, the server starts if it is not already up, the browser opens on the
dashboard.

Everything here is a plain file in the user's own home directory. Nothing needs
administrator rights, and `jsa uninstall` removes all of it.
"""

from __future__ import annotations

import os
import plistlib
import sysconfig
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Any

APP_NAME = "Job Pipeline"
BUNDLE_ID = "dev.jobsearchagent.dashboard"
LABEL = "dev.jobsearchagent.dashboard"
APPS_DIR = Path.home() / "Applications"
APP_PATH = APPS_DIR / f"{APP_NAME}.app"
AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
REPO_ROOT = Path(__file__).resolve().parent.parent

WINDOWS = sys.platform == "win32"

SHIM_POSIX = """#!/bin/bash
# jsa — run job-search-agent from any directory.
# Written by `jsa install`; delete it or run `jsa uninstall` to remove.
export PYTHONPATH="{repo}${{PYTHONPATH:+:$PYTHONPATH}}"
exec "{python}" -m jsa "$@"
"""

SHIM_WINDOWS = """@echo off
REM jsa - run job-search-agent from any directory.
REM Written by `jsa install`; delete it or run `jsa uninstall` to remove.
set "PYTHONPATH={repo};%PYTHONPATH%"
"{python}" -m jsa %*
"""

SHIM = SHIM_WINDOWS if WINDOWS else SHIM_POSIX
SHIM_NAME = "jsa.bat" if WINDOWS else "jsa"

# Where a command-line shim can go without administrator rights. First writable
# directory wins; being on PATH is checked separately and reported. On Windows
# the interpreter's Scripts directory is the one already on PATH.
if WINDOWS:
    SHIM_DIRS = [Path(sysconfig.get_path("scripts")),
                 Path.home() / "AppData" / "Local" / "Programs" / "jsa"]
else:
    SHIM_DIRS = [Path("/usr/local/bin"), Path.home() / ".local" / "bin"]

# Double-clickable launcher for Windows, since there is no .app bundle there.
LAUNCHER_WINDOWS = """@echo off
title Job Pipeline
set "PYTHONPATH={repo};%PYTHONPATH%"
set "URL=http://127.0.0.1:{port}/"
curl -s -o NUL --max-time 1 "%URL%"
if errorlevel 1 (
  start "" /B "{python}" -m jsa serve --port {port} --no-browser
  timeout /t 4 /nobreak >NUL
)
start "" "%URL%"
"""

LAUNCHER = """#!/bin/bash
# Opens the job-search dashboard, starting the local server if it is not up.
REPO="{repo}"
PY="{python}"
PORT={port}
URL="http://127.0.0.1:$PORT/"

if ! curl -s -o /dev/null --max-time 1 "$URL"; then
  cd "$REPO" || exit 1
  nohup "$PY" -m jsa serve --port "$PORT" --no-browser >/dev/null 2>&1 &
  for _ in $(seq 1 40); do
    curl -s -o /dev/null --max-time 1 "$URL" && break
    sleep 0.25
  done
fi
open "$URL"
"""


# --------------------------------------------------------------- icon

def _png(size: int, rgba_pixel: Any) -> bytes:
    """A square PNG, written with zlib and struct — no imaging library."""
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter type 0 for each scanline
        for x in range(size):
            raw.extend(rgba_pixel(x, y, size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">2I5B", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def _icon_pixel(x: int, y: int, size: int) -> tuple[int, int, int, int]:
    """A rounded square in the dashboard's accent blue, with a funnel mark."""
    unit, radius = size / 100, size * 0.22
    cx, cy = size / 2, size / 2
    dx, dy = abs(x - cx + 0.5), abs(y - cy + 0.5)
    limit = size / 2 - 1
    inside = (dx <= limit - radius or dy <= limit - radius
              or (dx - (limit - radius)) ** 2 + (dy - (limit - radius)) ** 2 <= radius ** 2)
    if not inside:
        return (0, 0, 0, 0)
    # Three descending bars: the funnel this whole tool is about.
    for row, (top, left, width) in enumerate(((30, 22, 56), (48, 30, 40), (66, 38, 24))):
        if top * unit <= y <= (top + 11) * unit and left * unit <= x <= (left + width) * unit:
            return (255, 255, 255, 255)
    shade = int(31 + 40 * (y / size))
    return (shade, 111 + int(20 * (y / size)), 235, 255)


def build_icon(target: Path) -> bool:
    """Write an .icns next to the bundle. Returns False if iconutil is absent."""
    if not shutil.which("iconutil"):
        return False
    iconset = target.parent / "icon.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    try:
        for size in (16, 32, 128, 256, 512):
            (iconset / f"icon_{size}x{size}.png").write_bytes(_png(size, _icon_pixel))
            (iconset / f"icon_{size}x{size}@2x.png").write_bytes(_png(size * 2, _icon_pixel))
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(target)],
                       check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, OSError):
        return False
    finally:
        shutil.rmtree(iconset, ignore_errors=True)


# --------------------------------------------------------------- shim

def shim_path() -> Path | None:
    """Where the `jsa` command is, or would go."""
    for directory in SHIM_DIRS:
        candidate = directory / SHIM_NAME
        if candidate.exists():
            return candidate
    for directory in SHIM_DIRS:
        if directory.is_dir() and os.access(directory, os.W_OK):
            return directory / SHIM_NAME
    return SHIM_DIRS[-1] / SHIM_NAME


def on_path(directory: Path) -> bool:
    entries = {Path(p).expanduser() for p in os.environ.get("PATH", "").split(os.pathsep) if p}
    return directory in entries


def build_shim() -> tuple[Path, bool]:
    """Install the `jsa` command. Returns (path, whether its directory is on PATH)."""
    target = shim_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(SHIM.format(repo=REPO_ROOT, python=sys.executable), encoding="utf-8")
    target.chmod(0o755)
    return target, on_path(target.parent)


# ---------------------------------------------------------------- app

def build_app(port: int) -> Path:
    macos = APP_PATH / "Contents" / "MacOS"
    resources = APP_PATH / "Contents" / "Resources"
    macos.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)

    launcher = macos / "launcher"
    launcher.write_text(
        LAUNCHER.format(repo=REPO_ROOT, python=sys.executable, port=port), encoding="utf-8"
    )
    launcher.chmod(0o755)

    info: dict[str, Any] = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": "launcher",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "LSMinimumSystemVersion": "11.0",
        "LSUIElement": True,  # no bouncing Dock icon while it starts the server
        "NSHighResolutionCapable": True,
    }
    if build_icon(resources / "icon.icns"):
        info["CFBundleIconFile"] = "icon"
    (APP_PATH / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
    # Nudge Launch Services so the app appears in Spotlight straight away.
    subprocess.run(
        ["/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework"
         "/Support/lsregister", "-f", str(APP_PATH)],
        capture_output=True, check=False,
    )
    return APP_PATH


# -------------------------------------------------------------- agent

def build_agent(port: int) -> Path:
    AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AGENT_PATH.write_bytes(plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "jsa", "serve",
                             "--port", str(port), "--no-browser"],
        "WorkingDirectory": str(REPO_ROOT),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardErrorPath": str(REPO_ROOT / "profile" / "serve.log"),
    }))
    subprocess.run(["launchctl", "unload", str(AGENT_PATH)], capture_output=True, check=False)
    subprocess.run(["launchctl", "load", str(AGENT_PATH)], capture_output=True, check=False)
    return AGENT_PATH


def build_windows_launcher(port: int) -> Path:
    """A double-clickable .bat on the Desktop, and in the Start Menu if it exists."""
    script = LAUNCHER_WINDOWS.format(repo=REPO_ROOT, python=sys.executable, port=port)
    targets = [Path.home() / "Desktop" / f"{APP_NAME}.bat"]
    start_menu = (Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows"
                  / "Start Menu" / "Programs")
    if start_menu.is_dir():
        targets.append(start_menu / f"{APP_NAME}.bat")
    written = None
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(script, encoding="utf-8")
            written = written or target
        except OSError:
            continue
    return written or targets[0]


def install(port: int = 8765, at_login: bool = False) -> dict[str, Any]:
    """Install the `jsa` command, and whatever passes for an app on this system."""
    shim, path_ok = build_shim()
    result: dict[str, Any] = {
        "shim": shim, "shim_on_path": path_ok, "app": None, "agent": None,
        "platform": sys.platform,
    }
    if sys.platform == "darwin":
        result["app"] = build_app(port)
        if at_login:
            result["agent"] = build_agent(port)
    elif WINDOWS:
        result["app"] = build_windows_launcher(port)
        if at_login:
            result["note"] = ("Starting at login is not set up automatically on Windows. "
                              "Put a shortcut to the launcher in your Startup folder "
                              "(Win+R, then: shell:startup).")
    else:
        result["note"] = ("On Linux there is no app bundle. Run `jsa serve` and bookmark "
                          f"http://127.0.0.1:{port}/ , or add a .desktop entry pointing at "
                          f"{shim} serve.")
    return result


def uninstall() -> list[str]:
    removed = []
    if WINDOWS:
        for candidate in (Path.home() / "Desktop" / f"{APP_NAME}.bat",
                          Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows"
                          / "Start Menu" / "Programs" / f"{APP_NAME}.bat"):
            if candidate.exists():
                candidate.unlink()
                removed.append(str(candidate))
    shim = shim_path()
    if shim.exists() and "job-search-agent" in shim.read_text(errors="ignore"):
        shim.unlink()
        removed.append(str(shim))
    if AGENT_PATH.exists():
        subprocess.run(["launchctl", "unload", str(AGENT_PATH)], capture_output=True, check=False)
        AGENT_PATH.unlink()
        removed.append(str(AGENT_PATH))
    if APP_PATH.exists():
        shutil.rmtree(APP_PATH)
        removed.append(str(APP_PATH))
    return removed


def status(port: int = 8765) -> dict[str, Any]:
    running = False
    try:
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/run", timeout=1):
            running = True
    except Exception:  # noqa: BLE001 - "not running" is the only thing we need
        running = False
    shim = shim_path()
    return {
        "command": shim if shim.exists() else None,
        "command_on_path": on_path(shim.parent) if shim.exists() else False,
        "app": APP_PATH.exists(),
        "login_agent": AGENT_PATH.exists(),
        "server_running": running,
        "port": port,
    }
