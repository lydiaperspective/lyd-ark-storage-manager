# Lyd Storage Manager Web UI

The web interface is a client for the existing lydstore operations. The CLI remains the source of truth for storage configuration and systemd unit generation.

## First-time setup

Set a dedicated web-interface username and password:

~~~sh
sudo lydstore webui setup --username storage-admin
~~~

This guided command prompts for the password twice, saves the salted password hash, and enables and starts `lydstore-web.service`. Use a dedicated username and a password of at least 14 characters.

Passwords must be at least 14 characters. The password is stored as a salted scrypt hash in /etc/lydstore/webui.json, mode 0600.

Open the local interface at http://127.0.0.1:8765/.

## Secure remote access with Tailscale

The recommended remote-access path is a private Tailscale network. It avoids exposing the privileged storage API or opening an internet-facing port.

1. Install and authenticate Tailscale on the server and each client that needs access.
2. On the server, run the optional setup command:

   ~~~sh
   sudo lydstore webui tailscale
   ~~~

   This runs Tailscale Serve against the loopback-only web service. Tailscale must already be installed and signed in.

3. Use the HTTPS hostname reported by Tailscale Serve in the desktop launcher's Remote option.
4. Keep the Storage Manager username and password private. Tailscale access controls and the web login are separate layers.

Tailscale CLI syntax and Serve availability can vary by installed version. Check tailscale serve --help if the command differs. Do not expose port 8765 directly to the internet.

## Desktop launcher

The desktop application menu entry is Lyd Storage Manager. It offers:
- This desktop: opens the local loopback service.
- A remote Lyd Ark server: stores an HTTPS server URL in ~/.config/lydstore/remote-url and opens it in the default browser.

The launcher rejects non-HTTPS remote URLs.

## API and security

The API is versioned under /api/v1. It uses HTTP Basic authentication and requires same-origin Origin headers for state-changing requests. OpenAPI and interactive API documentation are disabled.

The service binds to 127.0.0.1:8765 and runs as root because existing lydstore operations manage system-wide mounts and systemd units. It exposes fixed CLI subcommands with validated request fields; it does not provide arbitrary command execution. Static assets are served separately from the API.

Remote access must use a trusted HTTPS transport. The recommended configuration is Tailscale Serve, with Tailscale access controls and the Storage Manager login both enabled.

## Current scope and safety limits

- Overview: layout, folders, drives, remotes, backups, and failed systemd units.
- Folders & Layout: standard folder locations, dry-run and confirmed folder relocation to a mounted drive, plus dry-run and confirmed /ark layout migration.
- Drives: add and remove UUID-based automounts.
- Cloud: add and remove existing rclone remotes.
- Backups: create scheduled copy/sync jobs, remove jobs, run backups, and confirmed restore.
- Folder relocation requires a mounted destination below /ark/Drives, verifies the copy, and retains the original folder as a rollback copy.
- Relocating /ark/Containers is blocked while containers are running.
- Restore copies the backup into the configured source and may overwrite files. It requires an explicit RESTORE confirmation.
- Sync requires an explicit acknowledgement because it may delete destination-only files.
- Drive removal disables its systemd units but does not erase drive data.

The first release does not include multi-user roles, audit history, or remote credential creation. The API is intended to be reused by a future native KDE client.
