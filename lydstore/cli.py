"""Command-line interface for lydstore."""
from __future__ import annotations
import argparse
import grp
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path
from . import config, units


def identity(name):
    p = pwd.getpwnam(name)
    return p.pw_uid, p.pw_gid, p.pw_dir


def init_layout(admin):
    units.require_root()
    root, link = Path("/orundum/ark"), Path("/ark")
    if link.exists() and not link.is_symlink():
        raise RuntimeError("/ark already exists as a real directory; refusing to move or overwrite it automatically")
    if link.is_symlink() and os.readlink(link) != str(root):
        raise RuntimeError(f"/ark points to {os.readlink(link)}, not /orundum/ark; refusing to replace it")
    group = grp.getgrnam("ark")
    root.mkdir(parents=True, exist_ok=True)
    for name in ("Containers", "Media", "Share", "Configs", "Drives"):
        p = root / name
        p.mkdir(exist_ok=True)
        os.chown(p, 0, group.gr_gid)
        os.chmod(p, 0o2775)
    os.chown(root, 0, group.gr_gid)
    os.chmod(root, 0o2775)
    if not link.is_symlink():
        link.symlink_to(root)
    uid, _, _ = identity(admin)
    subprocess.run(["usermod", "-aG", "ark", admin], check=True)
    print(f"Initialized {root}; /ark -> {root}. Added {admin} (uid {uid}) to group ark; log out and back in for group changes.")


def main_run(argv=None):
    p = argparse.ArgumentParser(prog="lydstore", description="Lyd Ark storage manager")
    sub = p.add_subparsers(dest="area", required=True)
    layout = sub.add_parser("layout", help="Manage standardized Ark storage")
    ls = layout.add_subparsers(dest="action", required=True)
    ls.add_parser("status")
    li = ls.add_parser("init"); li.add_argument("--admin", required=True)
    drives = sub.add_parser("drives", help="Manage SATA/USB automounts").add_subparsers(dest="action", required=True)
    drives.add_parser("list")
    da = drives.add_parser("add"); da.add_argument("--uuid", required=True); da.add_argument("--name", required=True); da.add_argument("--admin", required=True); da.add_argument("--fstype", default="auto"); da.add_argument("--options", default="defaults")
    dr = drives.add_parser("remove"); dr.add_argument("name")
    remotes = sub.add_parser("remotes", help="Manage rclone network mounts").add_subparsers(dest="action", required=True)
    remotes.add_parser("list")
    ra = remotes.add_parser("add"); ra.add_argument("--name", required=True); ra.add_argument("--remote", required=True); ra.add_argument("--target", required=True); ra.add_argument("--user", required=True); ra.add_argument("--config")
    rr = remotes.add_parser("remove"); rr.add_argument("name")
    backups = sub.add_parser("backups", help="Manage scheduled rclone backups").add_subparsers(dest="action", required=True)
    backups.add_parser("list")
    ba = backups.add_parser("add"); ba.add_argument("--name", required=True); ba.add_argument("--source", required=True); ba.add_argument("--destination", required=True); ba.add_argument("--user", required=True); ba.add_argument("--config"); ba.add_argument("--schedule", choices=["hourly","daily","weekly","monthly"], default="daily"); ba.add_argument("--mode", choices=["copy","sync"], default="copy")
    br = backups.add_parser("remove"); br.add_argument("name")
    bx = backups.add_parser("run"); bx.add_argument("name")
    ns = p.parse_args(argv)
    data = config.load()

    if ns.area == "layout" and ns.action == "status":
        root, link = Path("/orundum/ark"), Path("/ark")
        print(f"Physical root: {root} ({'present' if root.exists() else 'missing'})")
        print(f"/ark: {os.readlink(link) if link.is_symlink() else 'not a symlink'}")
        for folder in ("Containers","Media","Share","Configs","Drives"):
            print(f"  {folder}: {'present' if (root/folder).exists() else 'missing'}")
    elif ns.area == "layout" and ns.action == "init":
        init_layout(ns.admin)
    elif ns.area == "drives" and ns.action == "list":
        for d in data["drives"]: print(f"{d['name']}: UUID={d['uuid']} -> /ark/Drives/{d['name']} ({d['admin']})")
    elif ns.area == "drives" and ns.action == "add":
        units.require_root()
        uid, gid, _ = identity(ns.admin)
        if any(d["name"] == ns.name or d["uuid"].lower() == ns.uuid.lower() for d in data["drives"]): raise ValueError("Drive name or UUID already configured")
        device = Path("/dev/disk/by-uuid") / ns.uuid
        if not device.exists(): raise ValueError(f"Device {device} is not present")
        fs = ns.fstype
        if fs == "auto":
            fs = subprocess.check_output(["blkid", "-o", "value", "-s", "TYPE", str(device)], text=True).strip()
        d = {"name":units.valid_name(ns.name),"uuid":ns.uuid,"admin":ns.admin,"uid":uid,"gid":gid,"fstype":fs,"options":ns.options}
        target = Path("/ark/Drives") / ns.name
        if not Path("/ark").is_symlink() or os.readlink("/ark") != "/orundum/ark": raise RuntimeError("Initialize the Ark layout first with lydstore layout init")
        target.mkdir(parents=True, exist_ok=True)
        generated = units.drive_units(d)
        for unit, content in generated: units.write_unit(unit, content)
        units.reload_systemd()
        if fs not in ("exfat", "vfat", "ntfs", "ntfs3", "fuseblk"):
            mount_unit = generated[0][0]
            try:
                subprocess.run(["systemctl", "start", mount_unit], check=True)
                subprocess.run(["setfacl", "-R", "-m", f"u:{uid}:rwX", str(target)], check=True)
                subprocess.run(["find", str(target), "-type", "d", "-exec", "setfacl", "-m", f"d:u:{uid}:rwx", "{}", "+"], check=True)
            finally:
                subprocess.run(["systemctl", "stop", mount_unit], check=False)
        data["drives"].append(d); config.save(data); units.reload_systemd(); units.enable_now(units.systemd_escape(str(target), "automount"))
        print(f"Configured {device} at {target}; admin write ACLs are prepared and systemd mounts it on first access.")
    elif ns.area == "drives" and ns.action == "remove":
        units.require_root(); d = next((x for x in data["drives"] if x["name"] == ns.name), None)
        if not d: raise ValueError("Unknown drive")
        target = f"/ark/Drives/{ns.name}"
        units.disable_remove([units.systemd_escape(target,"automount"), units.systemd_escape(target,"mount")])
        data["drives"].remove(d); config.save(data)
    elif ns.area == "remotes" and ns.action == "list":
        for r in data["remotes"]: print(f"{r['name']}: {r['remote']} -> {r['target']} ({r['user']})")
    elif ns.area == "remotes" and ns.action == "add":
        units.require_root()
        _, _, home = identity(ns.user)
        cfg = ns.config or str(Path(home)/".config/rclone/rclone.conf")
        if any(x["name"] == ns.name for x in data["remotes"]): raise ValueError("Remote name already configured")
        if not shutil.which("rclone"): raise RuntimeError("Install rclone first")
        if not Path(cfg).is_file(): raise ValueError(f"rclone config not found: {cfg}; configure the remote as that user first")
        if not Path("/ark").is_symlink(): raise RuntimeError("Initialize the Ark layout first")
        target = Path(ns.target)
        if not target.is_absolute() or ".." in target.parts: raise ValueError("Mount target must be an absolute normalized path")
        target.mkdir(parents=True, exist_ok=True)
        uid, gid, _ = identity(ns.user); os.chown(target, uid, gid)
        r = {"name":units.valid_name(ns.name),"remote":ns.remote,"target":str(target),"user":ns.user,"config":cfg}
        unit, content = units.rclone_service(r); units.write_unit(unit, content)
        data["remotes"].append(r); config.save(data); units.reload_systemd(); units.enable_now(unit)
        print(f"Enabled rclone mount {unit}")
    elif ns.area == "remotes" and ns.action == "remove":
        units.require_root(); r = next((x for x in data["remotes"] if x["name"] == ns.name), None)
        if not r: raise ValueError("Unknown remote")
        units.disable_remove([f"lydstore-rclone-{ns.name}.service"]); data["remotes"].remove(r); config.save(data)
    elif ns.area == "backups" and ns.action == "list":
        for b in data["backups"]: print(f"{b['name']}: {b['source']} -> {b['destination']} ({b['schedule']}, {b['mode']})")
    elif ns.area == "backups" and ns.action == "add":
        units.require_root()
        _, _, home = identity(ns.user); cfg = ns.config or str(Path(home)/".config/rclone/rclone.conf")
        if any(x["name"] == ns.name for x in data["backups"]): raise ValueError("Backup name already configured")
        if not shutil.which("rclone"): raise RuntimeError("Install rclone first")
        if not Path(cfg).is_file(): raise ValueError(f"rclone config not found: {cfg}")
        b = {"name":units.valid_name(ns.name),"source":ns.source,"destination":ns.destination,"user":ns.user,"config":cfg,"schedule":ns.schedule,"mode":ns.mode}
        for unit, content in units.backup_units(b): units.write_unit(unit, content)
        data["backups"].append(b); config.save(data); units.reload_systemd(); units.enable_now(f"lydstore-backup-{ns.name}.timer")
        print(f"Scheduled backup {ns.name}")
    elif ns.area == "backups" and ns.action == "remove":
        units.require_root(); b = next((x for x in data["backups"] if x["name"] == ns.name), None)
        if not b: raise ValueError("Unknown backup")
        units.disable_remove([f"lydstore-backup-{ns.name}.timer",f"lydstore-backup-{ns.name}.service"])
        data["backups"].remove(b); config.save(data)
    elif ns.area == "backups" and ns.action == "run":
        if not any(x["name"] == ns.name for x in data["backups"]): raise ValueError("Unknown backup")
        subprocess.run(["systemctl","start",f"lydstore-backup-{ns.name}.service"],check=True)
    return 0


def main():
    try: return main_run()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, KeyError, PermissionError) as exc:
        print(f"lydstore: error: {exc}", file=sys.stderr); return 1
