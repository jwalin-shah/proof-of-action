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

VERSION_MASTER = 0x01   # encrypted with master key (G7)
VERSION_DERIVED = 0x02  # encrypted with HKDF(master, id) (H4)
NONCE_LEN = 12
MASTER_KEY_ENV = "POA_MASTER_KEY"
KEY_LEN = 32  # 256 bits

# Back-compat alias — G7 tests import this as the "current" version.
VERSION = VERSION_MASTER


class MasterKeyMissing(RuntimeError):
    pass


class EnvelopeCorrupt(ValueError):
    pass


KEYCHAIN_SERVICE = "proof-of-action"
KEYCHAIN_ACCOUNT = "master-key"


def _keychain_fetch() -> str | None:
    """Read the master key hex from macOS Keychain, or None on any failure.

    H6: prefer Keychain over POA_MASTER_KEY so the raw bytes never sit in a
    shell env var or dotfile. Non-macOS hosts fall through to env.
    """
    import shutil
    import subprocess

    if not shutil.which("security"):
        return None
    try:
        r = subprocess.run(
            [
                "security", "find-generic-password",
                "-s", KEYCHAIN_SERVICE,
                "-a", KEYCHAIN_ACCOUNT,
                "-w",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip() or None
    except Exception:
        return None
    return None


def master_key() -> bytes:
    """Read the 32-byte master key.

    Source priority (H6):
      1. macOS Keychain (service=proof-of-action account=master-key)
      2. POA_MASTER_KEY environment variable (dev fallback)

    Seed the Keychain with: scripts/keygen.sh --keychain
    """
    raw = _keychain_fetch() or os.environ.get(MASTER_KEY_ENV)
    if not raw:
        raise MasterKeyMissing(
            f"No master key found in Keychain ({KEYCHAIN_SERVICE}/{KEYCHAIN_ACCOUNT}) "
            f"or {MASTER_KEY_ENV}. Run: scripts/keygen.sh"
        )
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise MasterKeyMissing(f"master key is not valid hex") from exc
    if len(key) != KEY_LEN:
        raise MasterKeyMissing(
            f"master key must be {KEY_LEN} bytes ({KEY_LEN*2} hex chars)"
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


def _wrap(key: bytes, plaintext: bytes, aad: bytes = b"", version: int = VERSION_MASTER) -> bytes:
    if len(key) != KEY_LEN:
        raise ValueError(f"key must be {KEY_LEN} bytes, got {len(key)}")
    nonce = secrets.token_bytes(NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad or None)
    return bytes([version]) + nonce + ct


def _unwrap(key: bytes, envelope: bytes, aad: bytes = b"") -> bytes:
    if len(envelope) < 1 + NONCE_LEN + 16:
        raise EnvelopeCorrupt("envelope too short")
    if envelope[0] not in (VERSION_MASTER, VERSION_DERIVED):
        raise EnvelopeCorrupt(f"unknown envelope version {envelope[0]:#x}")
    nonce = envelope[1 : 1 + NONCE_LEN]
    ct = envelope[1 + NONCE_LEN :]
    try:
        return AESGCM(key).decrypt(nonce, ct, aad or None)
    except Exception as exc:
        raise EnvelopeCorrupt("GCM auth failure (wrong key or tampered)") from exc


def envelope_version(envelope: bytes) -> int:
    """Read the version byte so callers can route to master vs derived key."""
    if len(envelope) < 1:
        raise EnvelopeCorrupt("envelope empty")
    return envelope[0]


def encrypt_with_master(plaintext: bytes, aad: bytes = b"") -> bytes:
    """Encrypt with the raw master key. Phase G7 default."""
    return _wrap(master_key(), plaintext, aad, VERSION_MASTER)


def decrypt_with_master(envelope: bytes, aad: bytes = b"") -> bytes:
    return _unwrap(master_key(), envelope, aad)


def encrypt_derived(derivation_id: str, plaintext: bytes, aad: bytes = b"") -> bytes:
    """Encrypt with HKDF(master, derivation_id) — Phase H4.

    derivation_id scopes the key: same id → same key, different id → unrelated
    key. Leaking the key for action X gives nothing for action Y.
    """
    return _wrap(derive_action_key(derivation_id), plaintext, aad, VERSION_DERIVED)


def decrypt_derived(derivation_id: str, envelope: bytes, aad: bytes = b"") -> bytes:
    return _unwrap(derive_action_key(derivation_id), envelope, aad)
