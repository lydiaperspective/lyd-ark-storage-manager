"""Desktop entry point for choosing a local or remote Storage Manager."""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path
from urllib.parse import urlsplit
from shutil import which

def run(*args: str) -> str | None:
    try:
        result = subprocess.run(args, text=True, capture_output=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    except OSError:
        return None

def open_url(url: str) -> int:
    try:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    except OSError:
        return 1

def main() -> int:
    config_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lydstore"
    remote_file = config_dir / "remote-url"
    local_url = "http://127.0.0.1:8765/"
    if not which("kdialog"):
        return open_url(local_url)
    choice = run("kdialog", "--title", "Lyd Storage Manager", "--menu",
                 "Choose which Storage Manager to open:", "local", "This desktop",
                 "remote", "A remote Lyd Ark server")
    if choice == "local":
        return open_url(local_url)
    if choice != "remote":
        return 0
    previous = remote_file.read_text(encoding="utf-8").strip() if remote_file.exists() else ""
    remote = run("kdialog", "--title", "Remote Storage Manager", "--inputbox",
                 "Enter the HTTPS address of your Lyd Ark server:", previous)
    if not remote: return 0
    parsed = urlsplit(remote)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        run("kdialog", "--error", "Remote connections must use an HTTPS URL without embedded credentials.")
        return 1
    if any(ord(char) < 32 for char in remote):
        run("kdialog", "--error", "The address contains invalid characters.")
        return 1
    config_dir.mkdir(parents=True, exist_ok=True)
    remote_file.write_text(remote.rstrip("/") + "/\n", encoding="utf-8")
    os.chmod(remote_file, 0o600)
    return open_url(remote.rstrip("/") + "/")

if __name__ == "__main__":
    sys.exit(main())
