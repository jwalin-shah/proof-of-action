"""AES-256-GCM envelope for private values.

Every value written to private:* in Redis is wrapped with this envelope so
that a `.rdb` dump, an `scp` of the dump, or even a SHOW COMMAND leak reveals
only ciphertext. The master key stays on the operator's machine (env for
now, Keychain in Phase H6).

Envelope format (raw bytes):
    [1 byte version=0x01]
    [12 byte nonce]
    [ciphertext]
    [16 byte GCM tag]

Phase H4 swaps the raw master key for an HKDF-derived per-action key;
this module exposes both `encrypt_with_master` and `encrypt_derived` so
callers can opt into derivation once that lands.
"""
from __future__ import annotations

import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

VERSION = 0x01
NONCE_LEN = 12
MASTER_KEY_ENV = "POA_MASTER_KEY"
KEY_LEN = 32  # 256 bits


class MasterKeyMissing(RuntimeError):
    pass


class EnvelopeCorrupt(ValueError):
    pass


def master_key() -> bytes:
    """Read the 32-byte master key from POA_MASTER_KEY (hex-encoded).

    Phase H6 replaces this with Keychain access.
    """
    raw = os.environ.get(MASTER_KEY_ENV)
    if not raw:
        raise MasterKeyMissing(
            f"{MASTER_KEY_ENV} not set. Run: scripts/keygen.sh"
        )
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise MasterKeyMissing(f"{MASTER_KEY_ENV} is not valid hex") from exc
    if len(key) != KEY_LEN:
        raise MasterKeyMissing(
            f"{MASTER_KEY_ENV} must be {KEY_LEN} bytes ({KEY_LEN*2} hex chars)"
        )
    return key


def derive_action_key(action_id: str, master: bytes | None = None) -> bytes:
    """HKDF(master, info='poa/v1/action/<action_id>') -> 32-byte key.

    Used by Phase H4 so old-action keys cannot decrypt new actions.
    Callers that do not yet opt in just use encrypt_with_master.
    """
    master = master if master is not None else master_key()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_LEN,
        salt=None,
        info=f"poa/v1/action/{action_id}".encode(),
    )
    return hkdf.derive(master)


def _wrap(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    if len(key) != KEY_LEN:
        raise ValueError(f"key must be {KEY_LEN} bytes, got {len(key)}")
    nonce = secrets.token_bytes(NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad or None)
    return bytes([VERSION]) + nonce + ct


def _unwrap(key: bytes, envelope: bytes, aad: bytes = b"") -> bytes:
    if len(envelope) < 1 + NONCE_LEN + 16:
        raise EnvelopeCorrupt("envelope too short")
    if envelope[0] != VERSION:
        raise EnvelopeCorrupt(f"unknown envelope version {envelope[0]:#x}")
    nonce = envelope[1 : 1 + NONCE_LEN]
    ct = envelope[1 + NONCE_LEN :]
    try:
        return AESGCM(key).decrypt(nonce, ct, aad or None)
    except Exception as exc:
        raise EnvelopeCorrupt("GCM auth failure (wrong key or tampered)") from exc


def encrypt_with_master(plaintext: bytes, aad: bytes = b"") -> bytes:
    """Encrypt with the raw master key. Phase G7 default."""
    return _wrap(master_key(), plaintext, aad)


def decrypt_with_master(envelope: bytes, aad: bytes = b"") -> bytes:
    return _unwrap(master_key(), envelope, aad)


def encrypt_derived(action_id: str, plaintext: bytes, aad: bytes = b"") -> bytes:
    """Encrypt with HKDF(master, action_id) — Phase H4 opt-in."""
    return _wrap(derive_action_key(action_id), plaintext, aad)


def decrypt_derived(action_id: str, envelope: bytes, aad: bytes = b"") -> bytes:
    return _unwrap(derive_action_key(action_id), envelope, aad)
