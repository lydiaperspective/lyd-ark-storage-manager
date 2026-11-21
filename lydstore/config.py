"""Persistent lydstore configuration helpers."""
from __future__ import annotations
import grp
import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("LYDSTORE_CONFIG_DIR", "/etc/lydstore"))
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT = {"schema": 1, "drives": [], "remotes": [], "backups": []}


def load() -> dict:
    if not CONFIG_FILE.exists():
        return DEFAULT.copy()
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read {CONFIG_FILE}: {exc}") from exc
    if data.get("schema") != 1:
        raise RuntimeError("Unsupported lydstore configuration schema")
    for key in ("drives", "remotes", "backups"):
        if not isinstance(data.get(key), list):
            raise RuntimeError(f"Invalid configuration: {key} must be a list")
    return data


def save(data: dict) -> None:
    if os.geteuid() != 0 and CONFIG_DIR == Path("/etc/lydstore"):
        raise PermissionError("Run this configuration command with sudo")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.chmod(tmp, 0o640)
    try:
        group = grp.getgrnam("ark")
        os.chown(tmp, 0, group.gr_gid)
        os.chown(CONFIG_DIR, 0, group.gr_gid)
        os.chmod(CONFIG_DIR, 0o750)
    except KeyError:
        os.chmod(CONFIG_DIR, 0o700)
    os.replace(tmp, CONFIG_FILE)
