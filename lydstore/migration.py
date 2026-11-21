"""State-aware migration of shared /ark data to /orundum/ark."""
from __future__ import annotations
import os
import pwd
import shutil
import subprocess
import time
from pathlib import Path


def _run_podman(user: str | None, args: list[str]) -> list[str]:
    if user is None:
        cmd = ["podman", *args]
        env = os.environ.copy()
    else:
        account = pwd.getpwnam(user)
        runtime = Path(f"/run/user/{account.pw_uid}")
        if not runtime.is_dir():
            return []
        cmd = ["runuser", "-u", user, "--", "env", f"HOME={account.pw_dir}",
               f"XDG_RUNTIME_DIR={runtime}", "podman", *args]
        env = os.environ.copy()
    result = subprocess.run(cmd, check=True, text=True, capture_output=True, env=env)
    return [line for line in result.stdout.splitlines() if line.strip()]


def _container_contexts() -> list[tuple[str | None, list[str]]]:
    contexts: list[tuple[str | None, list[str]]] = []
    if Path("/var/lib/containers/storage").exists():
        ids = _run_podman(None, ["ps", "-q"])
        if ids:
            contexts.append((None, ids))
    for entry in pwd.getpwall():
        if entry.pw_uid < 1000 or entry.pw_uid == 65534:
            continue
        store = Path(f"/orundum/users/{entry.pw_uid}/containers/storage")
        if not store.exists():
            continue
        ids = _run_podman(entry.pw_name, ["ps", "-q"])
        if ids:
            contexts.append((entry.pw_name, ids))
    return contexts


def _restart(contexts: list[tuple[str | None, list[str]]]) -> None:
    errors = []
    for user, ids in contexts:
        try:
            _run_podman(user, ["start", *ids])
        except subprocess.CalledProcessError as exc:
            errors.append(f"{user or 'root'}: {exc.stderr or exc}")
    if errors:
        raise RuntimeError("Some previously running containers could not be restarted: " + "; ".join(errors))


def migrate_ark(dry_run: bool = False) -> Path | None:
    if os.geteuid() != 0:
        raise PermissionError("Run the storage migration with sudo")
    source, destination = Path("/ark"), Path("/orundum/ark")
    if source.is_symlink():
        if os.readlink(source) == str(destination):
            return destination
        raise RuntimeError(f"/ark is already a symlink to {os.readlink(source)}")
    if not source.is_dir():
        raise RuntimeError("The existing /ark directory does not exist")
    destination.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(destination):
        if files or any(Path(root, d).is_file() for d in dirs):
            raise RuntimeError("/orundum/ark already contains data; refusing to merge two storage trees")
    contexts = _container_contexts()
    if dry_run:
        count = sum(len(ids) for _, ids in contexts)
        print(f"DRY RUN: would stop {count} running containers, copy {source} to {destination}, verify the copy, replace /ark with a symlink, then restart those containers.")
        return None
    stopped: list[tuple[str | None, list[str]]] = []
    try:
        for user, ids in contexts:
            _run_podman(user, ["stop", "--time", "30", *ids])
            stopped.append((user, ids))
        subprocess.run(["rsync", "-aHAX", "--numeric-ids", f"{source}/", f"{destination}/"], check=True)
        verify = subprocess.run(
            ["rsync", "-aHAXn", "--checksum", "--delete", "--numeric-ids", "--itemize-changes",
             f"{source}/", f"{destination}/"], check=True, text=True, capture_output=True
        )
        differences = [line for line in verify.stdout.splitlines()
                       if line.strip() and not line.startswith(("sending incremental file list", "sent ", "total size is", "./"))]
        if differences:
            raise RuntimeError("Storage copy verification found differences: " + "; ".join(differences[:10]))
        backup = Path(f"/ark.pre-lydstore-{int(time.time())}")
        os.rename(source, backup)
        try:
            source.symlink_to(destination)
            if not source.is_symlink() or source.resolve() != destination.resolve():
                raise RuntimeError("Could not verify the new /ark symlink")
        except Exception:
            source.unlink(missing_ok=True)
            os.rename(backup, source)
            raise
        _restart(stopped)
        return backup
    except Exception:
        # If the old path has not been replaced, the copied target is harmless.
        # If containers were stopped, restore only their original running state.
        try:
            _restart(stopped)
        except Exception:
            pass
        raise
