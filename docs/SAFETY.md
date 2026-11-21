# Safety and design constraints

- Persistent drive identity is based on filesystem UUID, never `/dev/sdX`.
- Removable drives are mounted with systemd automount and `nofail`; a missing drive must not block boot.
- Mount locations are restricted to named children of `/ark/Drives` for local devices.
- Admin write access is granted with filesystem-specific UID/GID options for filesystems without Unix ownership. Native Unix filesystems retain ownership/ACL semantics and must be provisioned accordingly.
- rclone credentials are not copied into unit files. Units run as the configured account and refer to its rclone config file.
- rclone network mounts start after network-online and restart after failures; a missing network must not prevent the rest of the system from booting.
- Backups default to `rclone copy`. `sync` is opt-in because it can delete destination-only data.
- Rootless Podman graphroots remain per-user under `/orundum/users/<uid>/containers/storage`. Shared persistent container data belongs under `/ark/Containers`.
- Moving existing Podman graphroots is not performed by this initial command set. A future migration command must snapshot running-container state across users, stop all affected containers, copy with numeric ownership/xattrs/ACLs/hardlinks, validate storage metadata, switch configuration atomically, and restart only containers that were running before migration. It must support rollback and dry-run.
