"""Generate and install systemd units for lydstore-managed resources."""
from __future__ import annotations
import os
import re
import subprocess
from pathlib import Path

UNIT_DIR = Path("/etc/systemd/system")
UUID_RE = re.compile(r"^[0-9A-Fa-f-]{8,64}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")


def require_root():
    if os.geteuid() != 0:
        raise PermissionError("This operation changes system-wide storage configuration; run with sudo")


def valid_name(name: str) -> str:
    if not NAME_RE.fullmatch(name):
        raise ValueError("Name must use letters, numbers, dot, underscore or hyphen")
    return name


def systemd_escape(path: str, suffix: str) -> str:
    return subprocess.check_output(["systemd-escape", "--path", "--suffix", suffix, path], text=True).strip()


def systemd_arg(value: str) -> str:
    value = str(value).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return '"' + value + '"'


def write_unit(name: str, content: str) -> Path:
    require_root()
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    path = UNIT_DIR / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
    return path


def reload_systemd():
    subprocess.run(["systemctl", "daemon-reload"], check=True)


def enable_now(unit: str):
    subprocess.run(["systemctl", "enable", "--now", unit], check=True)


def disable_remove(names: list[str]):
    require_root()
    for unit in names:
        subprocess.run(["systemctl", "disable", "--now", unit], check=False)
        (UNIT_DIR / unit).unlink(missing_ok=True)
    reload_systemd()


def drive_units(drive: dict) -> list[tuple[str, str]]:
    name = valid_name(drive["name"])
    uuid = drive["uuid"]
    if not UUID_RE.fullmatch(uuid):
        raise ValueError("UUID does not look valid")
    where = drive.get("mountpoint", f"/ark/Drives/{name}")
    if not where.startswith("/ark/") or ".." in Path(where).parts:
        raise ValueError("Local drive mountpoints must be safe paths below /ark")
    mount_unit = systemd_escape(where, "mount")
    auto_unit = systemd_escape(where, "automount")
    fs = drive.get("fstype", "auto")
    options = drive.get("options", "defaults")
    uid, gid = int(drive["uid"]), int(drive["gid"])
    if fs in ("exfat", "vfat", "ntfs", "ntfs3", "fuseblk"):
        options += f",uid={uid},gid={gid},umask=0007"
    mount = (f"[Unit]\nDescription=Lyd Ark drive {name}\nJobTimeoutSec=5s\n\n[Mount]\n"
             f"What=/dev/disk/by-uuid/{uuid}\nWhere={where}\nType={fs}\nOptions={options}\n")
    auto = (f"[Unit]\nDescription=Automount Lyd Ark drive {name}\n\n[Automount]\nWhere={where}\n"
            "TimeoutIdleSec=300\n\n[Install]\nWantedBy=multi-user.target\n")
    return [(mount_unit, mount), (auto_unit, auto)]


def rclone_service(remote: dict) -> tuple[str, str]:
    name = valid_name(remote["name"])
    user, target, config = remote["user"], remote["target"], remote["config"]
    if not target.startswith("/") or ".." in Path(target).parts:
        raise ValueError("Remote mount target must be an absolute safe path")
    unit = f"lydstore-rclone-{name}.service"
    content = (f"[Unit]\nDescription=Lyd Ark rclone mount {name}\nWants=network-online.target\n"
               f"After=network-online.target\n\n[Service]\nType=simple\nUser={user}\n"
               f"ExecStart=/usr/bin/rclone mount {systemd_arg(remote['remote'])} {systemd_arg(target)} "
               f"--config {systemd_arg(config)} --allow-other --vfs-cache-mode writes --dir-cache-time 5m\n"
               f"ExecStop=/usr/bin/fusermount3 -u {systemd_arg(target)}\n"
               "Restart=on-failure\nRestartSec=15s\nTimeoutStopSec=30s\n"
               "\n[Install]\nWantedBy=multi-user.target\n")
    return unit, content


def backup_units(backup: dict) -> list[tuple[str, str]]:
    name = valid_name(backup["name"])
    user = backup["user"]
    source, destination = backup["source"], backup["destination"]
    if not source.startswith("/") or ".." in Path(source).parts:
        raise ValueError("Backup source must be an absolute safe path")
    if not destination or destination.startswith("-"):
        raise ValueError("Invalid rclone destination")
    mode = backup.get("mode", "copy")
    if mode not in ("copy", "sync"):
        raise ValueError("Backup mode must be copy or sync")
    service, timer = f"lydstore-backup-{name}.service", f"lydstore-backup-{name}.timer"
    svc = (f"[Unit]\nDescription=Lyd Ark backup {name}\n\n[Service]\nType=oneshot\nUser={user}\n"
           f"ExecStart=/usr/bin/rclone {mode} {systemd_arg(source)} {systemd_arg(destination)} "
           f"--create-empty-src-dirs --config {systemd_arg(backup['config'])}\n")
    schedule = backup.get("schedule", "daily")
    if schedule not in ("hourly", "daily", "weekly", "monthly"):
        raise ValueError("Schedule must be hourly, daily, weekly or monthly")
    tmr = (f"[Unit]\nDescription=Schedule Lyd Ark backup {name}\n\n[Timer]\nOnCalendar={schedule}\n"
           f"Persistent=true\nUnit={service}\n\n[Install]\nWantedBy=timers.target\n")
    restore = f"lydstore-restore-{name}.service"
    restore_svc = (f"[Unit]\nDescription=Restore Lyd Ark backup {name}\n\n[Service]\nType=oneshot\nUser={user}\n"
                   f"ExecStart=/usr/bin/rclone copy {systemd_arg(destination)} {systemd_arg(source)} "
                   f"--create-empty-src-dirs --config {systemd_arg(backup['config'])}\n")
    return [(service, svc), (timer, tmr), (restore, restore_svc)]
