"""AES-256-GCM encryption for the source-token vault.

Wire format (stored in source_token.encrypted_token):
    nonce (12 bytes) || ciphertext (variable) || tag (16 bytes)

Rotation-ready design
─────────────────────
1. Primary key  = VAULT_ENCRYPTION_KEY   (required)
2. Previous key = VAULT_ENCRYPTION_KEY_PREVIOUS  (optional, set during rotation)

encrypt() always uses the primary key.
decrypt() tries the primary key first; if it fails and a previous key is
configured it retries with that key.  A background task can re-encrypt
rows so the previous key can eventually be retired.
"""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

_NONCE_LEN = 12  # 96-bit nonce recommended for AES-GCM
_TAG_LEN = 16    # GCM tag is appended by cryptography lib


def _get_keys() -> list[bytes]:
    """Return [primary_key] or [primary_key, previous_key] as raw bytes."""
    keys: list[bytes] = []
    primary = settings.vault_encryption_key
    if primary and primary != "change_me_in_production_64_hex_chars_00000000000000000000000000000000":
        keys.append(bytes.fromhex(primary))
    else:
        raise ValueError(
            "VAULT_ENCRYPTION_KEY is not set or still has the placeholder value. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    prev = settings.vault_encryption_key_previous
    if prev:
        keys.append(bytes.fromhex(prev))
    return keys


def encrypt(plaintext: str) -> bytes:
    """Encrypt a plaintext string and return the wire-format blob."""
    key = _get_keys()[0]
    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # ct already includes the 16-byte tag appended by the library
    return nonce + ct


def decrypt(blob: bytes) -> str:
    """Decrypt a wire-format blob, trying primary then previous key."""
    if len(blob) < _NONCE_LEN + _TAG_LEN + 1:
        raise ValueError("Encrypted blob is too short")

    nonce = blob[:_NONCE_LEN]
    ct_with_tag = blob[_NONCE_LEN:]

    keys = _get_keys()
    last_err: Exception | None = None
    for key in keys:
        try:
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ct_with_tag, None)
            return plaintext.decode("utf-8")
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue

    raise ValueError("Decryption failed with all available keys") from last_err
