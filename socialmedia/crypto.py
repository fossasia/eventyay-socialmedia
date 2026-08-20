import base64
import hashlib
import json
import logging

from cryptography.fernet import Fernet
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """Derive a url-safe 32-byte key from Django SECRET_KEY using SHA-256."""
    key_bytes = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_credentials(data: dict) -> str:
    """Serialize the credentials dictionary to JSON and encrypt it using Fernet."""
    if not data:
        return ""
    json_str = json.dumps(data)
    fernet = _get_fernet()
    encrypted_bytes = fernet.encrypt(json_str.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_credentials(encrypted_text: str) -> dict:
    """Decrypt the Fernet-encrypted cipher text and parse it as a dictionary."""
    if not encrypted_text:
        return {}
    try:
        fernet = _get_fernet()
        decrypted_bytes = fernet.decrypt(encrypted_text.encode("utf-8"))
        return json.loads(decrypted_bytes.decode("utf-8"))
    except Exception as exc:
        logger.warning("Failed to decrypt credentials: %s", exc)
        return {}
