"""Command-line interface for lydstore."""
from __future__ import annotations
import argparse
import getpass
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path
from . import config
from . import units


def admin_identity(name: str):
    entry = pwd.getpwnam(name)
    return entry.pw_uid, entry.pw_gid


def run(args=None):
    p = argparse.ArgumentParser(prog="lydstore", description="Lyd Ark storage manager")
    sub = p.add_subparsers(dest="area", required=True)
    layout = sub.add_parser("layout", help="Inspect standardized Ark storage")
    layout.add_subparsers(dest="action", required=True).add_parser("status")
    drives = sub.add_parser("drives", help="Manage local SATA/USB automounts").add_subparsers(dest="action", required=True)
    drives.add_parser("list")
    da = drives.add_parser("add"); da.add_argument("--uuid", required=True); da.add_argument("--name", required=True); da.add_argument("--admin", default=getpass.getuser()); da.add_argument("--fstype", default="auto"); da.add_argument("--options", default="defaults,nofail,x-systemd.device-timeout=5s")
    dr = drives.add_parser("remove"); dr.add_argument("name")
    remotes = sub.add_parser("remotes", help="Manage rclone network mounts").add_subparsers(dest="action", required=True)
    remotes.add_parser("list")
    ra = remotes.add_parser("add"); ra.add_argument("--name", required=True); ra.add_argument("--remote", required=True, help="Configured rclone remote:path"); ra.add_argument("--target", required=True); ra.add_argument("--user", default=getpass.getuser()); ra.add_argument("--config", default=str(Path.home()/".config/rclone/rclone.conf"))
    rr = remotes.add_parser("remove"); rr.add_argument("name")
    backups = sub.add_parser("backups", help="Manage scheduled rclone backups").add_subparsers(dest="action", required=True)
    backups.add_parser("list")
    ba = backups.add_parser("add"); ba.add_argument("--name", required=True); ba.add_argument("--source", required=True); ba.add_argument("--destination", required=True); ba.add_argument("--user", default=getpass.getuser()); ba.add_argument("--schedule", choices=["hourly","daily","weekly","monthly"], default="daily"); ba.add_argument("--mode", choices=["copy","sync"], default="copy")
    br = backups.add_parser("remove"); br.add_argument("name")
    bx = backups.add_parser("run"); bx.add_argument("name")
    ns = p.parse_args(args)
    data = config.load()
    if ns.area == "layout":
        root = Path("/orundum/ark")
        print(f"Physical root: {root} ({'present' if root.exists() else 'missing'})")
        ark = Path("/ark")
        print(f"/ark: {ark} -> {os.readlink(ark) if ark.is_symlink() else 'not a symlink'}")
        for folder in ("Containers","Media","Share","Configs","Drives"):
            print(f"  {folder}: {'present' if (root/folder).exists() else 'missing'}")
    elif ns.area == "drives" and ns.action == "list":
        for d in data["drives"]: print(f"{d['name']}: UUID={d['uuid']} -> /ark/Drives/{d['name']} ({d['admin']})")
    elif ns.area == "drives" and ns.action == "add":
        units.require_root(); uid,gid=admin_identity(ns.admin)
        if any(d["name"] == ns.name or d["uuid"].lower() == ns.uuid.lower() for d in data["drives"]): raise ValueError("Drive name or UUID is already configured")
        d={"name":units.valid_name(ns.name),"uuid":ns.uuid,"admin":ns.admin,"uid":uid,"gid":gid,"fstype":ns.fstype,"options":ns.options}
        target=Path("/ark/Drives")/ns.name; target.mkdir(parents=True,exist_ok=True)
        for unit,content in units.drive_units(d): units.write_unit(unit,content)
        data["drives"].append(d); config.save(data); units.reload_systemd(); units.enable_now(units.systemd_escape(str(target),"automount")); print(f"Configured /ark/Drives/{ns.name}; it mounts on first access.")
    elif ns.area == "drives" and ns.action == "remove":
        units.require_root(); d=next((x for x in data["drives"] if x["name"]==ns.name),None)
        if not d: raise ValueError("Unknown drive")
        target=f"/ark/Drives/{ns.name}"; names=[units.systemd_escape(target,"automount"),units.systemd_escape(target,"mount")]
        units.disable_remove(names); data["drives"].remove(d); config.save(data)
    elif ns.area == "remotes" and ns.action == "list":
        for r in data["remotes"]: print(f"{r['name']}: {r['remote']} -> {r['target']} ({r['user']})")
    elif ns.area == "remotes" and ns.action == "add":
        units.require_root(); admin_identity(ns.user)
        if any(x["name"]==ns.name for x in data["remotes"]): raise ValueError("Remote name already configured")
        if not shutil.which("rclone"): raise RuntimeError("Install rclone first")
        if not Path(ns.config).is_file(): raise ValueError("rclone config not found; configure the remote with rclone config first")
        target=Path(ns.target); target.mkdir(parents=True,exist_ok=True)
        os.chown(target,*admin_identity(ns.user))
        r={"name":units.valid_name(ns.name),"remote":ns.remote,"target":str(target),"user":ns.user,"config":ns.config}
        unit,content=units.rclone_service(r); units.write_unit(unit,content); data["remotes"].append(r); config.save(data); units.reload_systemd(); units.enable_now(unit); print(f"Enabled rclone mount service {unit}")
    elif ns.area == "remotes" and ns.action == "remove":
        units.require_root(); r=next((x for x in data["remotes"] if x["name"]==ns.name),None)
        if not r: raise ValueError("Unknown remote")
        unit=f"lydstore-rclone-{ns.name}.service"; units.disable_remove([unit]); data["remotes"].remove(r); config.save(data)
    elif ns.area == "backups" and ns.action == "list":
        for b in data["backups"]: print(f"{b['name']}: {b['source']} -> {b['destination']} ({b['schedule']}, {b['mode']})")
    elif ns.area == "backups" and ns.action == "add":
        units.require_root(); admin_identity(ns.user)
        if any(x["name"]==ns.name for x in data["backups"]): raise ValueError("Backup name already configured")
        if not shutil.which("rclone"): raise RuntimeError("Install rclone first")
        b={"name":units.valid_name(ns.name),"source":ns.source,"destination":ns.destination,"user":ns.user,"schedule":ns.schedule,"mode":ns.mode}
        for unit,content in units.backup_units(b): units.write_unit(unit,content)
        data["backups"].append(b); config.save(data); units.reload_systemd(); units.enable_now(f"lydstore-backup-{ns.name}.timer"); print(f"Scheduled backup {ns.name}")
    elif ns.area == "backups" and ns.action == "remove":
        units.require_root(); b=next((x for x in data["backups"] if x["name"]==ns.name),None)
        if not b: raise ValueError("Unknown backup")
        units.disable_remove([f"lydstore-backup-{ns.name}.timer",f"lydstore-backup-{ns.name}.service"]); data["backups"].remove(b); config.save(data)
    elif ns.area == "backups" and ns.action == "run":
        b=next((x for x for x in data["backups"] if x["name"]==ns.name),None)
        if not b: raise ValueError("Unknown backup")
        subprocess.run(["systemctl","start",f"lydstore-backup-{ns.name}.service"],check=True)
    return 0


def main():
    try: return run()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, KeyError) as exc:
        print(f"lydstore: error: {exc}",file=sys.stderr); return 1
