"""Authenticated HTTP API for Lyd Storage Manager."""
from __future__ import annotations
import json, os, pwd, re, shutil, subprocess, sys
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, field_validator
import uvicorn
from .web_auth import credentials_configured, verify_credentials

APP_DIR = Path(__file__).resolve().parent / "webui"
security = HTTPBasic(auto_error=False)
app = FastAPI(title="Lyd Storage Manager", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=APP_DIR), name="static")

def authenticate(credentials: HTTPBasicCredentials | None = Depends(security)) -> str:
    if not credentials_configured():
        raise HTTPException(status_code=503, detail="Web credentials are not configured. Run: sudo lydstore webui set-password --username YOUR_USER")
    if credentials is None or not verify_credentials(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="Lyd Storage Manager", charset="UTF-8"'})
    return credentials.username

@app.middleware("http")
async def security_headers_and_origin_guard(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin, host = request.headers.get("origin"), request.headers.get("host", "")
        if not origin or urlsplit(origin).netloc.lower() != host.lower():
            return JSONResponse({"detail": "Cross-origin or origin-less state changes are not allowed"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    response.headers["Cache-Control"] = "no-store"
    return response

def run_cli(*args: str, timeout: int = 300) -> str:
    executable = shutil.which("lydstore")
    command = [executable, *args] if executable else [sys.executable, "-m", "lydstore", *args]
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="The storage operation timed out") from exc
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "Storage operation failed"
        raise HTTPException(status_code=400, detail=message[-1200:])
    return result.stdout.strip()

def parse_lines(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]

def parse_items(output: str) -> list[dict[str, str]]:
    items = []
    for line in parse_lines(output):
        if ": " in line:
            name, details = line.split(": ", 1)
            items.append({"name": name, "details": details})
    return items

class MigrationRequest(BaseModel):
    dry_run: bool = True
    confirmation: str | None = None

class DriveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=63)
    uuid: str = Field(min_length=8, max_length=64)
    admin: str = Field(min_length=1, max_length=64)
    mountpoint: str | None = Field(default=None, max_length=240)
    fstype: Literal["auto", "btrfs", "ext4", "xfs", "exfat", "vfat", "ntfs", "ntfs3"] = "auto"
    options: str = "defaults"
    @field_validator("uuid")
    @classmethod
    def valid_uuid(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9A-Fa-f-]{8,64}", value): raise ValueError("Invalid filesystem UUID")
        return value
    @field_validator("options")
    @classmethod
    def safe_options(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_,=.-]{1,200}", value):
            raise ValueError("Mount options contain unsupported characters")
        return value

class RemoteRequest(BaseModel):
    name: str = Field(min_length=1, max_length=63)
    remote: str = Field(min_length=3, max_length=512)
    target: str = Field(min_length=2, max_length=240)
    user: str = Field(min_length=1, max_length=64)
    config: str | None = Field(default=None, max_length=512)
    @field_validator("remote")
    @classmethod
    def safe_remote(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+:.+", value) or any(ord(ch) < 32 for ch in value):
            raise ValueError("Use an existing rclone remote and path, such as cloud:archive")
        return value

class BackupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=63)
    source: str = Field(min_length=2, max_length=512)
    destination: str = Field(min_length=3, max_length=512)
    user: str = Field(min_length=1, max_length=64)
    config: str | None = Field(default=None, max_length=512)
    schedule: Literal["hourly", "daily", "weekly", "monthly"] = "daily"
    mode: Literal["copy", "sync"] = "copy"
    confirm_sync: bool = False
    @field_validator("destination")
    @classmethod
    def safe_destination(cls, value: str) -> str:
        if value.startswith("-") or any(ord(ch) < 32 for ch in value): raise ValueError("Invalid rclone destination")
        return value

@app.get("/")
def index(_: str = Depends(authenticate)):
    return FileResponse(APP_DIR / "index.html")

@app.get("/api/v1/status")
def status(_: str = Depends(authenticate)):
    layout = run_cli("layout", "status")
    drives = run_cli("drives", "list")
    remotes = run_cli("remotes", "list")
    backups = run_cli("backups", "list")
    failed = subprocess.run(["systemctl", "--failed", "--no-legend", "--plain"],
        text=True, capture_output=True, timeout=10, check=False)
    return {"layout": parse_lines(layout), "drives": parse_items(drives),
            "remotes": parse_items(remotes), "backups": parse_items(backups),
            "failed_units": parse_lines(failed.stdout)}

@app.get("/api/v1/devices")
def devices(_: str = Depends(authenticate)):
    result = subprocess.run(["lsblk", "--json", "-o", "NAME,SIZE,FSTYPE,UUID,MOUNTPOINTS,MODEL,TYPE"],
        text=True, capture_output=True, timeout=15, check=False)
    if result.returncode: raise HTTPException(status_code=500, detail="Unable to enumerate block devices")
    try: return json.loads(result.stdout).get("blockdevices", [])
    except json.JSONDecodeError as exc: raise HTTPException(status_code=500, detail="Invalid block-device response") from exc

@app.get("/api/v1/users")
def users(_: str = Depends(authenticate)):
    return [{"username": a.pw_name, "home": a.pw_dir} for a in pwd.getpwall()
            if 1000 <= a.pw_uid < 60000 and a.pw_dir.startswith("/home/")]

@app.post("/api/v1/layout/migrate")
def migrate(request: MigrationRequest, _: str = Depends(authenticate)):
    if not request.dry_run and request.confirmation != "MIGRATE":
        raise HTTPException(status_code=400, detail='Applying migration requires confirmation="MIGRATE"')
    args = ["layout", "migrate"] + (["--dry-run"] if request.dry_run else [])
    return {"output": run_cli(*args, timeout=1800), "dry_run": request.dry_run}

@app.post("/api/v1/drives")
def add_drive(request: DriveRequest, _: str = Depends(authenticate)):
    args = ["drives", "add", "--uuid", request.uuid, "--name", request.name, "--admin", request.admin,
            "--fstype", request.fstype, "--options", request.options]
    if request.mountpoint: args += ["--mountpoint", request.mountpoint]
    return {"output": run_cli(*args, timeout=180)}

@app.delete("/api/v1/drives/{name}")
def remove_drive(name: str, _: str = Depends(authenticate)):
    return {"output": run_cli("drives", "remove", name, timeout=180)}

@app.post("/api/v1/remotes")
def add_remote(request: RemoteRequest, _: str = Depends(authenticate)):
    args = ["remotes", "add", "--name", request.name, "--remote", request.remote,
            "--target", request.target, "--user", request.user]
    if request.config: args += ["--config", request.config]
    return {"output": run_cli(*args, timeout=180)}

@app.delete("/api/v1/remotes/{name}")
def remove_remote(name: str, _: str = Depends(authenticate)):
    return {"output": run_cli("remotes", "remove", name, timeout=180)}

@app.post("/api/v1/backups")
def add_backup(request: BackupRequest, _: str = Depends(authenticate)):
    if request.mode == "sync" and not request.confirm_sync:
        raise HTTPException(status_code=400, detail="Sync may delete destination-only files; explicitly confirm it")
    args = ["backups", "add", "--name", request.name, "--source", request.source,
            "--destination", request.destination, "--user", request.user,
            "--schedule", request.schedule, "--mode", request.mode]
    if request.config: args += ["--config", request.config]
    return {"output": run_cli(*args, timeout=180)}

@app.delete("/api/v1/backups/{name}")
def remove_backup(name: str, _: str = Depends(authenticate)):
    return {"output": run_cli("backups", "remove", name, timeout=180)}

class RestoreRequest(BaseModel):
    confirmation: str | None = None

@app.post("/api/v1/backups/{name}/{action}")
def run_backup(name: str, action: Literal["run", "restore"], request: RestoreRequest, _: str = Depends(authenticate)):
    if action == "restore" and request.confirmation != "RESTORE":
        raise HTTPException(status_code=400, detail="Restoring requires the exact confirmation word RESTORE")
    return {"output": run_cli("backups", action, name, timeout=1800)}

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Lyd Storage Manager web service")
    parser.add_argument("--host", default=os.environ.get("LYDSTORE_WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("LYDSTORE_WEB_PORT", "8765")))
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("The application must bind to loopback; use a trusted HTTPS reverse proxy for remote access")
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)

if __name__ == "__main__":
    main()
