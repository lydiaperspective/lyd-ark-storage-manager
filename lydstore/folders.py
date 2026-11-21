"""Safe relocation of standard shared Ark folders onto mounted data drives."""
from __future__ import annotations
import os
import subprocess
import time
from pathlib import Path
from .units import require_root

STANDARD_FOLDERS = ("Containers", "Media", "Share", "Configs")

def list_folders() -> list[tuple[str, str]]:
    result = []
    for name in STANDARD_FOLDERS:
        path = Path("/ark") / name
        if path.is_symlink():
            location = os.readlink(path)
        elif path.exists():
            location = str(path)
        else:
            location = "missing"
        result.append((name, location))
    return result

def _mounted_drive_parent(target: Path) -> Path:
    drives = Path("/ark/Drives").resolve()
    parent = target.parent.resolve()
    if not parent.is_relative_to(drives):
        raise ValueError("Folder destinations must be inside /ark/Drives")
    current = parent
    while current != drives and current.is_relative_to(drives):
        if os.path.ismount(current):
            return current
        current = current.parent
    raise ValueError("The destination must be on a mounted drive below /ark/Drives")

def move_folder(name: str, target_text: str, dry_run: bool = True, confirmation: str | None = None) -> Path | None:
    require_root()
    if name not in STANDARD_FOLDERS:
        raise ValueError("Only standard folders can be relocated")
    source = Path("/ark") / name
    target = Path(target_text)
    if not target.is_absolute() or ".." in target.parts:
        raise ValueError("Destination must be an absolute normalized path")
    if source.is_symlink():
        raise ValueError(f"{source} is already a symlink; move it back manually before relocating again")
    if not source.is_dir():
        raise ValueError(f"Source folder does not exist: {source}")
    if target == source or source in target.parents or target in source.parents:
        raise ValueError("Source and destination cannot overlap")
    if not target.parent.is_dir():
        raise ValueError("Destination parent must already exist on the mounted drive")
    mount = _mounted_drive_parent(target)
    if target.exists():
        if not target.is_dir() or any(target.iterdir()):
            raise ValueError("Destination already contains data; refusing to merge folders")
    if name == "Containers":
        from .migration import _container_contexts
        if any(ids for _, ids in _container_contexts()):
            raise RuntimeError("Stop all running containers before relocating /ark/Containers")
    if dry_run:
        print(f"DRY RUN: would copy {source} to {target}, verify checksums, retain the original folder as a rollback copy, and replace {source} with a symlink.")
        print(f"Destination drive: {mount}")
        return None
    if confirmation != "MOVE":
        raise ValueError("Applying a folder relocation requires confirmation MOVE")
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsync", "-aHAX", "--numeric-ids", f"{source}/", f"{target}/"], check=True)
    verify = subprocess.run(
        ["rsync", "-aHAXn", "--checksum", "--delete", "--numeric-ids", "--itemize-changes",
         f"{source}/", f"{target}/"], check=True, text=True, capture_output=True
    )
    differences = [line for line in verify.stdout.splitlines()
                   if line.strip() and not line.startswith(("sending incremental file list", "sent ", "total size is", "./"))]
    if differences:
        raise RuntimeError("Folder copy verification found differences: " + "; ".join(differences[:10]))
    backup = source.with_name(f".{name}.pre-lydstore-{int(time.time())}")
    os.rename(source, backup)
    try:
        source.symlink_to(target)
        if not source.is_symlink() or source.resolve() != target.resolve():
            raise RuntimeError("Could not verify the new folder symlink")
    except Exception:
        source.unlink(missing_ok=True)
        os.rename(backup, source)
        raise
    print(f"Relocated {source} to {target}. Original data retained at {backup}.")
    return backup
