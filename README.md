# Lyd Ark Storage Manager

`lydstore` is the storage administration CLI for Lyd Ark Linux, designed for immutable bootc-based desktop and server images.

## Managed storage

- Shared Ark directories physically stored at `/orundum/ark`, exposed through the stable `/ark` path.
- SATA/USB filesystem automounts identified by filesystem UUID, never transient `/dev/sdX` names.
- rclone network mounts (including Google Drive), started by systemd after network availability.
- Scheduled rclone backups using systemd timers.

Rootless Podman's private graphroots remain separate at `/orundum/users/<uid>/containers/storage`. `/ark/Containers` is for persistent application/container data and bind mounts, not a shared Podman graphroot.

## Quick start

Initialize the standard directory layout once the admin account exists:

```sh
sudo lydstore layout migrate --dry-run
sudo lydstore layout migrate
sudo lydstore layout init --admin ADMIN_USER
```

Configure a local drive:

```sh
lsblk -f
sudo lydstore drives add --uuid FILESYSTEM_UUID --name Backup --admin ADMIN_USER
```

Configure rclone as the target user first (`rclone config`), then register a boot-time mount:

```sh
sudo lydstore remotes add --name GoogleDrive --remote gdrive: --target /ark/Drives/GoogleDrive --user ADMIN_USER
```

Schedule a backup:

```sh
sudo lydstore backups add --name ark-share --source /ark/Share --destination gdrive:ArkBackups/Share --user ADMIN_USER --schedule daily
sudo lydstore backups run ark-share
sudo lydstore backups restore ark-share
```

Use `lydstore --help` for the full command tree.

## Safety model

Drive identity is persistent. Missing removable/network storage must not block boot. rclone credentials remain in the configured user's rclone config and are not copied into systemd unit files. Backups default to non-destructive `rclone copy`; mirror/delete behavior requires explicitly selecting `--mode sync`.

The layout migration stops running Podman containers for root and active rootless users, copies and verifies the shared /ark tree, replaces /ark with a symlink, and restarts only containers that were running. The old directory is retained as a rollback copy. Podman's private graphroots remain separate and are never moved by this operation.

## Development

Python 3.11+, systemd, rclone (for remote/backup commands), util-linux, ACL tools, and root privileges for system-wide configuration.

```sh
python -m lydstore --help
python -m unittest discover -s tests -v
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) and [docs/SAFETY.md](docs/SAFETY.md).
