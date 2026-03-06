"""Config management for Astra"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

CONFIG_DIR = Path.home() / ".astra"
CONFIG_FILE = CONFIG_DIR / "config.json"
LAST_APOD_FILE = CONFIG_DIR / "last.json"
CACHE_DIR = CONFIG_DIR / "cache"
ARCHIVE_FILE = CONFIG_DIR / "archive.html"

ARCHIVE_URL = "https://apod.nasa.gov/apod/archivepixFull.html"

DEFAULT_CONFIG = {
    "size": "default",
    "bg": None,
    "greeter": False,
    "greeter_freq": "daily",
    "api_key": None,
    "greeter_last_run": None,
    "save_dir": None,
}

GREETER_TAG = "# astra-greeter"

# Shell-specific greeter lines
SHELL_LINES = {
    "cmd": "astra greet",
    "powershell": f"if (Get-Command astra -ErrorAction SilentlyContinue) {{ astra greet }}  {GREETER_TAG}",
    "bash": f"command -v astra >/dev/null 2>&1 && astra greet  {GREETER_TAG}",
    "zsh": f"command -v astra >/dev/null 2>&1 && astra greet  {GREETER_TAG}",
    "fish": f"command -v astra &>/dev/null; and astra greet  {GREETER_TAG}",
}

VALID_SHELLS = list(SHELL_LINES.keys())
WINDOWS_ONLY_SHELLS = {"cmd"}
POSIX_ONLY_SHELLS = {"zsh", "fish"}


def get_config_path() -> Path:
    """Return the path to the config file"""
    return CONFIG_FILE


def load_config() -> dict:
    """Load config from file, creating default if it doesnt exist"""
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        # Merge with defaults to handle missing keys
        return {**DEFAULT_CONFIG, **config}
    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Save config to file"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def save_last_apod(data: dict) -> None:
    """Save the last viewed APOD data"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LAST_APOD_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load_last_apod() -> dict | None:
    """Load the last viewed APOD data. Returns None if not found"""
    if not LAST_APOD_FILE.exists():
        return None
    try:
        with open(LAST_APOD_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def get_cache_path(date: str, ext: str) -> Path:
    """Return the path for a cached image"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{date}.{ext}"


def get_cached_image(date: str, ext: str) -> bytes | None:
    """Return cached image bytes if exists and not expired"""
    cache_path = get_cache_path(date, ext)
    if not cache_path.exists():
        return None

    # Check if older than 14 days
    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
    if datetime.now() - mtime > timedelta(days=14):
        cache_path.unlink()
        return None

    return cache_path.read_bytes()


def save_cached_image(date: str, ext: str, data: bytes) -> None:
    """Save image data to cache"""
    cache_path = get_cache_path(date, ext)
    cache_path.write_bytes(data)


def cleanup_expired_cache(max_age_days: int = 14) -> int:
    """Delete cached images older than max_age_days. Returns count of deleted files"""
    if not CACHE_DIR.exists():
        return 0

    deleted = 0
    now = datetime.now()
    for f in CACHE_DIR.iterdir():
        if f.is_file():
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if now - mtime > timedelta(days=max_age_days):
                f.unlink()
                deleted += 1
    return deleted


def clear_cache() -> tuple[int, int]:
    """Clear all cached images. Returns (files_deleted, bytes_freed)"""
    if not CACHE_DIR.exists():
        return 0, 0

    total_bytes = 0
    deleted = 0
    for f in CACHE_DIR.iterdir():
        if f.is_file():
            total_bytes += f.stat().st_size
            f.unlink()
            deleted += 1
    return deleted, total_bytes


def _get_profile_path(shell: str) -> Path | None:
    """Return the profile file path for a given shell. None if not applicable"""
    if shell == "cmd":
        return None  # CMD uses registry
    if shell == "powershell":
        return (
            Path.home()
            / "Documents"
            / "WindowsPowerShell"
            / "Microsoft.PowerShell_profile.ps1"
        )
    if shell == "bash":
        if sys.platform == "darwin":
            return Path.home() / ".bash_profile"
        return Path.home() / ".bashrc"
    if shell == "zsh":
        return Path.home() / ".zshrc"
    if shell == "fish":
        return Path.home() / ".config" / "fish" / "config.fish"
    return None


def _get_ps7_profile_path() -> Path:
    return Path.home() / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"


def _install_to_profile(profile_path: Path, line: str) -> None:
    """Append the greeter line to a shell profile file if not already present"""
    profile_path.parent.mkdir(parents=True, exist_ok=True)

    if profile_path.exists():
        content = profile_path.read_text(encoding="utf-8")
        if GREETER_TAG in content:
            return  # Already installed
    else:
        content = ""

    separator = "\n" if content and not content.endswith("\n") else ""
    with open(profile_path, "a", encoding="utf-8") as f:
        f.write(f"{separator}{line}\n")


def _uninstall_from_profile(profile_path: Path) -> None:
    """Remove the greeter line from a shell profile file"""
    if not profile_path.exists():
        return

    content = profile_path.read_text(encoding="utf-8")
    if GREETER_TAG not in content:
        return

    lines = content.splitlines()
    filtered = [ln for ln in lines if GREETER_TAG not in ln]
    while filtered and filtered[-1] == "":
        filtered.pop()
    profile_path.write_text(
        "\n".join(filtered) + "\n" if filtered else "", encoding="utf-8"
    )


def fetch_archive() -> str:
    """Fetch archive HTML"""
    if ARCHIVE_FILE.exists():
        mtime = datetime.fromtimestamp(ARCHIVE_FILE.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=24):
            return ARCHIVE_FILE.read_text(encoding="utf-8", errors="ignore")

    try:
        response = requests.get(ARCHIVE_URL, timeout=15)
        response.raise_for_status()
        html = response.text
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        ARCHIVE_FILE.write_text(html, encoding="utf-8", errors="ignore")
        return html
    except requests.RequestException:
        if ARCHIVE_FILE.exists():
            return ARCHIVE_FILE.read_text(encoding="utf-8", errors="ignore")
        raise


def parse_archive(html: str) -> list[tuple[str, str]]:
    """Parse archive HTML into list of tuples"""
    # Pattern: 2026 March 06:  <a href="ap260306.html">The Astrosphere of HD 61005</a>
    pattern = r"(\d{4} \w+ \d{1,2}):\s+<a href=\"ap\d{6}\.html\">(.*?)</a>"
    matches = re.findall(pattern, html)
    return matches


def search_archive(query: str) -> list[tuple[str, str]]:
    """Search archive titles for query. Returns newest first"""
    html = fetch_archive()
    entries = parse_archive(html)
    query = query.lower()
    return [e for e in entries if query in e[1].lower()]


def _install_cmd_autorun() -> None:
    """Add 'astra greet' to CMD's AutoRun registry key"""
    import winreg

    key_path = r"Software\Microsoft\Command Processor"
    greeter_cmd = SHELL_LINES["cmd"]

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE
        )
    except FileNotFoundError:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)

    try:
        existing, _ = winreg.QueryValueEx(key, "AutoRun")
    except FileNotFoundError:
        existing = ""

    if greeter_cmd in existing:
        winreg.CloseKey(key)
        return  # Already installed

    if existing:
        new_value = f"{existing} & {greeter_cmd}"
    else:
        new_value = greeter_cmd

    winreg.SetValueEx(key, "AutoRun", 0, winreg.REG_SZ, new_value)
    winreg.CloseKey(key)


def _uninstall_cmd_autorun() -> None:
    """Remove astra greet from CMD's AutoRun registry key"""
    import winreg

    key_path = r"Software\Microsoft\Command Processor"
    greeter_cmd = SHELL_LINES["cmd"]

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE
        )
    except FileNotFoundError:
        return

    try:
        existing, _ = winreg.QueryValueEx(key, "AutoRun")
    except FileNotFoundError:
        winreg.CloseKey(key)
        return

    if greeter_cmd not in existing:
        winreg.CloseKey(key)
        return

    new_value = existing.replace(f" & {greeter_cmd}", "")
    new_value = new_value.replace(f"{greeter_cmd} & ", "")
    new_value = new_value.replace(greeter_cmd, "")
    new_value = new_value.strip()

    if new_value:
        winreg.SetValueEx(key, "AutoRun", 0, winreg.REG_SZ, new_value)
    else:
        winreg.DeleteValue(key, "AutoRun")

    winreg.CloseKey(key)


def validate_shell(shell: str) -> str | None:
    """Validate shell choice for current OS. Returns error message or None if valid"""
    if shell not in VALID_SHELLS:
        return f"Unknown shell '{shell}'. Valid options: {', '.join(VALID_SHELLS)}"
    if shell in WINDOWS_ONLY_SHELLS and sys.platform != "win32":
        return f"'{shell}' is only available on Windows."
    if shell in POSIX_ONLY_SHELLS and sys.platform == "win32":
        return f"'{shell}' is not available on Windows."
    return None


def install_greeter(shell: str) -> None:
    """Install the greeter into a shell's startup configuration"""
    if shell == "cmd":
        _install_cmd_autorun()
        return

    line = SHELL_LINES[shell]

    if shell == "powershell":
        _install_to_profile(_get_profile_path("powershell"), line)
        _install_to_profile(_get_ps7_profile_path(), line)
        return

    profile_path = _get_profile_path(shell)
    if profile_path:
        _install_to_profile(profile_path, line)


def uninstall_greeter(shell: str) -> None:
    """Remove the greeter from a shell's startup configuration"""
    if shell == "cmd":
        _uninstall_cmd_autorun()
        return

    if shell == "powershell":
        _uninstall_from_profile(_get_profile_path("powershell"))
        _uninstall_from_profile(_get_ps7_profile_path())
        return

    profile_path = _get_profile_path(shell)
    if profile_path:
        _uninstall_from_profile(profile_path)
