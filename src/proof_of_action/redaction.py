"""Leak detection for the boundary test.

Given a public artifact string, assert no PII or private field value from
any PrivateContext / PrivateDraft leaked through.

Rewrite note (post-review): the previous implementation only caught
substrings of length >= 20. That silently let names, emails under 20
chars, phone numbers, and short participant tokens pass. This version
scans explicit PII patterns + all name tokens down to length 3, and the
full participant strings verbatim.
"""
from __future__ import annotations

import re
from typing import Iterable

from proof_of_action.boundary import PrivateContext, PrivateDraft


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
URL_RE = re.compile(r"https?://[^\s<>\"']+")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
API_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9-]{16,}\b")
INSURANCE_ID_RE = re.compile(r"\b[A-Z]{3,5}-\d{3,5}-[A-Z0-9]{3,8}\b")


def private_fingerprints(
    contexts: Iterable[PrivateContext], drafts: Iterable[PrivateDraft]
) -> list[str]:
    """Return substrings that MUST NOT appear in any public artifact.

    Strategy:
      * Exact PII — emails, phones, URLs, whole names, participants — always.
      * Name tokens (First, Last, etc.) down to len >= 3 — always.
      * Body/subject — multi-word phrases only (>= 3 consecutive words).
        Single common words would create false positives against ordinary
        English in the public artifact (e.g. "review", "timing"). Multi-word
        phrases are virtually unique to the private content.
    """
    out: set[str] = set()
    for c in contexts:
        out.add(c.from_email)
        out.update(_email_handles(c.from_email))
        out.add(c.from_name)
        for token in _name_tokens(c.from_name):
            out.add(token)
        for p in c.participants:
            out.add(p)
            out.update(_email_handles(p))
            for token in _name_tokens(p):
                out.add(token)
        out.update(EMAIL_RE.findall(c.body))
        out.update(PHONE_RE.findall(c.body))
        out.update(URL_RE.findall(c.body))
        out.update(SSN_RE.findall(c.body))
        out.update(API_KEY_RE.findall(c.body))
        out.update(INSURANCE_ID_RE.findall(c.body))
        out.update(_ngram_phrases(c.body, n=3))
        out.update(_ngram_phrases(c.subject, n=3))
        if len(c.subject.split()) <= 4:
            out.add(c.subject)
    for d in drafts:
        out.update(EMAIL_RE.findall(d.body))
        out.update(PHONE_RE.findall(d.body))
        out.update(URL_RE.findall(d.body))
        out.update(SSN_RE.findall(d.body))
        out.update(API_KEY_RE.findall(d.body))
        out.update(INSURANCE_ID_RE.findall(d.body))
        out.update(_ngram_phrases(d.body, n=3))
    return [s for s in out if s and s.strip() and len(s) >= 3]


def _ngram_phrases(text: str, n: int) -> list[str]:
    """Sliding window of n consecutive word tokens → joined phrase."""
    words = [w for w in re.split(r"[\s\n]+", text) if w]
    if len(words) < n:
        return []
    return [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]


def _email_handles(email: str) -> list[str]:
    """Extract the local-part and capitalize variants (jamie → Jamie)."""
    if "@" not in email:
        return []
    local = email.split("@", 1)[0]
    out = [local]
    if local and len(local) >= 3:
        out.append(local.capitalize())
    return out


def _name_tokens(full_name: str) -> list[str]:
    return [
        t.strip()
        for t in re.split(r"[\s,]+", full_name)
        if t.strip() and len(t.strip()) >= 3
    ]


def _word_chunks(text: str, min_len: int) -> list[str]:
    pieces = re.split(r"[\s,.;:!?\n\(\)\[\]{}<>\"']+", text)
    return [p for p in pieces if len(p) >= min_len]


def scan_for_leaks(artifact: str, fingerprints: list[str]) -> list[str]:
    return [fp for fp in fingerprints if fp in artifact]
