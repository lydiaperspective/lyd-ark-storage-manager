# Configuration and usage

The system configuration is stored in `/etc/lydstore/config.json` with mode 0600. rclone credentials remain in the selected user's rclone configuration; generated systemd units reference its path and do not embed tokens.

## Local drives

Use `lsblk -f` or `blkid` to identify the filesystem UUID, then:

```sh
sudo lydstore drives add --uuid 1234-ABCD --name Backup --admin arkadmin --fstype exfat
```

The manager creates a systemd `.mount` and `.automount` pair at `/ark/Drives/Backup`. UUIDs are used instead of unstable kernel device names. exFAT, VFAT and NTFS-family filesystems receive UID/GID mount options and a restrictive group-accessible umask. Native Unix filesystems retain their on-disk ownership and ACLs; set the target directory ownership on the drive itself for the admin account. Removable media uses `nofail` and a short device timeout.

## rclone mounts

First configure and authenticate the remote as the target user, for example with `rclone config`. Then:

```sh
sudo lydstore remotes add --name GoogleDrive --remote gdrive: --target /ark/Drives/GoogleDrive --user arkadmin --config /home/arkadmin/.config/rclone/rclone.conf
```

This creates a system service started at boot after network-online. The service runs as the configured user, uses `--allow-other` and a VFS write cache. Ensure FUSE is installed and `user_allow_other` is enabled in `/etc/fuse.conf`. Use a dedicated rclone remote and config file for each account where needed.

## Backups

```sh
sudo lydstore backups add --name ark-share --source /ark/Share --destination gdrive:ArkBackups/Share --user arkadmin --schedule daily
sudo lydstore backups run ark-share
```

Backups use `rclone copy` by default, which does not delete destination-only files. `--mode sync` is an explicit mirror mode and can delete destination files; use it only when that is intended. Schedules are hourly, daily, weekly or monthly systemd timers. Inspect execution with `systemctl status lydstore-backup-ark-share.service` and `journalctl -u lydstore-backup-ark-share.service`.

## Commands

Run `lydstore --help` for the command tree. System-wide configuration operations require root; list/status commands can run unprivileged.
