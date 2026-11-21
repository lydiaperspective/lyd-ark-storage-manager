# Lyd Ark Storage Manager

`lydstore` is the storage administration CLI for Lyd Ark Linux. It is designed for immutable bootc-based desktop and server images.

## Scope

- Standardized shared data at `/orundum/ark`, exposed at the stable `/ark` path.
- Persistent SATA/USB filesystem automounts identified by filesystem UUID (PARTUUID is also recorded when available).
- rclone remote mounts (including Google Drive) managed as systemd automount services.
- Scheduled backups using rclone and systemd timers.

Rootless Podman's private graphroots remain separate at `/orundum/users/<uid>/containers/storage`. `/ark/Containers` is for persistent application/container data and bind mounts, not a shared Podman graphroot.

## Safety model

All configuration changes are explicit. Device mounts are generated from persistent IDs, never transient `/dev/sdX` names. Missing removable/network storage must not block boot. Backup defaults to non-destructive `rclone copy`; mirror/delete behavior must be explicitly selected. Secrets stay in the invoking user's rclone config and are not copied into generated unit files.

The migration of existing live Podman graphroots is intentionally a separate, state-aware operation; it must not be approximated by moving a directory while containers are running.

## Development

Python 3.11+, systemd, rclone (for remote/backup commands), and root privileges for system-wide mount configuration.

```sh
python -m lydstore --help
python -m unittest discover -s tests -v
```

## Initial command surface

```sh
lydstore layout status
lydstore drives list
lydstore drives add --uuid UUID --name Backup --admin USER
lydstore drives remove Backup
lydstore remotes list
lydstore remotes add --name cloud --type drive
lydstore remotes mount cloud --name GoogleDrive
lydstore backups add --name home --source /ark/Share --remote cloud:ArkBackups --schedule daily
lydstore backups run home
lydstore backups list
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) and [docs/SAFETY.md](docs/SAFETY.md).
