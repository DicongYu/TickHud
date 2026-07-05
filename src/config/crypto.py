from __future__ import annotations

import base64
import logging
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "tickhud"
_KEYRING_USER = "master_key"
_SALT_FILE = None


def _get_salt() -> bytes:
    return b"tickhud_salt_2024"


def _get_key() -> bytes | None:
    try:
        import keyring
        raw = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
        if raw is None:
            raw = base64.urlsafe_b64encode(os.urandom(32)).decode()
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, raw)
        return raw.encode()
    except Exception as e:
        logger.warning("Keyring unavailable (%s), using file-based key", e)
        return None


def _get_fernet() -> Fernet | None:
    key_material = _get_key()
    if key_material is None:
        return None
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_get_salt(), iterations=480000)
    fkey = base64.urlsafe_b64encode(kdf.derive(key_material))
    return Fernet(fkey)


def encrypt_value(plain: str) -> str:
    if not plain:
        return ""
    f = _get_fernet()
    if f is None:
        return plain
    try:
        return f.encrypt(plain.encode()).decode()
    except Exception as e:
        logger.error("Encryption failed: %s", e)
        return plain


def decrypt_value(cipher: str) -> str:
    if not cipher:
        return ""
    f = _get_fernet()
    if f is None:
        return cipher
    try:
        return f.decrypt(cipher.encode()).decode()
    except Exception:
        return cipher
