import base64
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)
LOCAL_SECRETS = INSTANCE_DIR / "local_secrets.json"


def _load_or_create_local_secret(name: str, factory):
    data = {}
    if LOCAL_SECRETS.exists():
        try:
            data = json.loads(LOCAL_SECRETS.read_text())
        except Exception:
            data = {}
    if name not in data:
        data[name] = factory()
        LOCAL_SECRETS.write_text(json.dumps(data, indent=2))
        os.chmod(LOCAL_SECRETS, 0o600)
    return data[name]


def get_secret_key() -> str:
    return os.environ.get("SECRET_KEY") or _load_or_create_local_secret(
        "SECRET_KEY", lambda: secrets.token_urlsafe(48)
    )


def get_fernet_key() -> bytes:
    key = os.environ.get("APP_FERNET_KEY") or _load_or_create_local_secret(
        "APP_FERNET_KEY", lambda: Fernet.generate_key().decode()
    )
    return key.encode()


def get_hmac_key() -> bytes:
    key = os.environ.get("APP_HMAC_KEY") or _load_or_create_local_secret(
        "APP_HMAC_KEY", lambda: secrets.token_urlsafe(48)
    )
    return key.encode()


_fernet = Fernet(get_fernet_key())


def encrypt_text(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return value
    return _fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return _fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except Exception:
        return "[encrypted-value-unavailable]"


def stable_email_hash(email: str) -> str:
    normalized = email.strip().lower().encode("utf-8")
    digest = hmac.new(get_hmac_key(), normalized, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


ALLOWED_UPLOADS = {".html", ".htm", ".zip"}


def allowed_training_upload(filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    return suffix in ALLOWED_UPLOADS


def safe_filename(filename: str) -> str:
    cleaned = secure_filename(filename)
    return cleaned or f"training_{secrets.token_hex(8)}.html"


def safe_extract_zip(zip_file, destination: Path) -> None:
    """Extract a zip while blocking zip-slip path traversal."""
    destination = destination.resolve()
    for member in zip_file.infolist():
        member_path = (destination / member.filename).resolve()
        if destination not in member_path.parents and member_path != destination:
            raise ValueError("Unsafe zip path detected.")
    zip_file.extractall(destination)


def make_csrf_token(session) -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def verify_csrf_token(session, submitted: str) -> bool:
    token = session.get("csrf_token")
    return bool(token and submitted and hmac.compare_digest(token, submitted))
