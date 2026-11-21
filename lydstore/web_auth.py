"""Credential storage for the Lyd Storage Manager web interface."""
from __future__ import annotations
import hashlib, hmac, json, os, re, secrets
from pathlib import Path

AUTH_FILE = Path("/etc/lydstore/webui.json")
SCRYPT_N, SCRYPT_R, SCRYPT_P = 1 << 14, 8, 1

def set_credentials(username: str, password: str, path: Path = AUTH_FILE) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", username):
        raise ValueError("Username must be 1-64 characters: letters, numbers, dot, underscore, @ or hyphen")
    if len(password) < 14:
        raise ValueError("Password must be at least 14 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    payload = {"username": username, "salt": salt.hex(), "password_hash": digest.hex(),
               "scrypt_n": SCRYPT_N, "scrypt_r": SCRYPT_R, "scrypt_p": SCRYPT_P}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)

def verify_credentials(username: str, password: str, path: Path = AUTH_FILE) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not secrets.compare_digest(str(payload["username"]), username):
            return False
        salt, expected = bytes.fromhex(payload["salt"]), bytes.fromhex(payload["password_hash"])
        actual = hashlib.scrypt(password.encode(), salt=salt, n=int(payload["scrypt_n"]),
                                 r=int(payload["scrypt_r"]), p=int(payload["scrypt_p"]), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False

def credentials_configured(path: Path = AUTH_FILE) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return bool(payload.get("username") and payload.get("salt") and payload.get("password_hash"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
