"""Envelope tests — ciphertext round-trip, tamper-detection, AAD binding."""
from __future__ import annotations

import os

import pytest

from proof_of_action import crypto


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv(crypto.MASTER_KEY_ENV, "11" * 32)
    yield


def test_roundtrip():
    pt = b"hello private"
    env = crypto.encrypt_with_master(pt, aad=b"key:thread:1")
    assert env[0] == crypto.VERSION
    # ciphertext must not contain plaintext
    assert b"hello" not in env
    out = crypto.decrypt_with_master(env, aad=b"key:thread:1")
    assert out == pt


def test_wrong_aad_fails():
    env = crypto.encrypt_with_master(b"x", aad=b"aad-a")
    with pytest.raises(crypto.EnvelopeCorrupt):
        crypto.decrypt_with_master(env, aad=b"aad-b")


def test_tamper_fails():
    env = bytearray(crypto.encrypt_with_master(b"x", aad=b""))
    env[-1] ^= 0x01  # flip a tag bit
    with pytest.raises(crypto.EnvelopeCorrupt):
        crypto.decrypt_with_master(bytes(env), aad=b"")


def test_derived_keys_isolate_actions():
    pt = b"secret"
    e1 = crypto.encrypt_derived("act_aaa", pt)
    e2 = crypto.encrypt_derived("act_bbb", pt)
    assert e1 != e2  # different derived keys → different ciphertexts
    assert crypto.decrypt_derived("act_aaa", e1) == pt
    # key for act_bbb cannot decrypt envelope from act_aaa
    with pytest.raises(crypto.EnvelopeCorrupt):
        crypto.decrypt_derived("act_bbb", e1)


def test_missing_key_raises():
    os.environ.pop(crypto.MASTER_KEY_ENV, None)
    with pytest.raises(crypto.MasterKeyMissing):
        crypto.encrypt_with_master(b"x")
