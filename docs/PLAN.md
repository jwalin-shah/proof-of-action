# Proof-of-Action — Hardening Plan

**Status as of 2026-04-24:** Phases A–F complete (dashboard live, Gmail source wired,
demo end-to-end). This plan covers phases G / H / I — turning every infra-layer
claim in the README from "trust us" to "run this command and verify."

## Design principle

Each work unit below is **parallelizable**: it specifies its own files, acceptance test,
and dependencies. Independent units can be dispatched to different subagents or workers
without coordination. Dependent units declare what they need upstream.

## Track layout

Four orthogonal tracks. Sequence within a track is serial; across tracks is parallel.

| Track | Owns | Parallel-safe with |
|---|---|---|
| **A. Supply chain** | `Dockerfile`, `.github/workflows/supply-chain.yml`, cosign, grype | B, C, D |
| **B. Data encryption** | `src/proof_of_action/crypto.py`, `stores/private_store.py`, `stores/public_store.py`, Redis TLS config | A, C, D |
| **C. Audit & artifact** | `stores/public_store.py::build_cited_md`, `scripts/doctor.sh`, `scripts/demo.sh`, `README.md`, `SUBMIT.md` | A, B partial (C integrations land last) |
| **D. TEE / research roadmap** | `docs/ROADMAP.md` only (no code this cycle) | always |

---

## Phase G — Tier 1: "Actually hardened" (4–6h)

### Track A (Supply chain)

#### G1. Fix Dockerfile multi-stage and test `docker run`
**Deliverable:** `Dockerfile` that produces an image in which `docker run <image>` completes a full agent run against the Gmail fixture fallback without errors.
**Depends on:** nothing.
**Acceptance:**
```bash
docker build -t poa:dev .
docker run --rm --network host \
  -e POA_FIXTURE=fixtures/adversarial_threads.json \
  -e POA_INSFORGE_URL=... -e POA_INSFORGE_EMAIL=... -e POA_INSFORGE_PASSWORD=... \
  poa:dev
# exits 0, prints [private]... [boundary]... [insforge]... lines
```

#### G2. Pin Chainguard base digest
**Deliverable:** `Dockerfile` uses `FROM cgr.dev/chainguard/python@sha256:...` for both stages. `.chainguard-digest` file committed with pinned digests.
**Depends on:** G1.
**Acceptance:** `grep '@sha256' Dockerfile | wc -l` returns 2; `cat .chainguard-digest` shows the pinned SHAs.

#### G3. `grype` scan gate in CI
**Deliverable:** `.github/workflows/supply-chain.yml` — runs on push, builds image, runs `grype`, fails on CVE ≥ high.
**Depends on:** G1.
**Acceptance:** Workflow file syntactically valid; `act` dry-run or push-to-branch confirms green on current image.

#### G4. `cosign` keyless signing
**Deliverable:** CI step after G3 that runs `cosign sign` using GitHub OIDC against GHCR push. `.github/workflows/supply-chain.yml` emits `cosign.pub` (or cert chain) as artifact.
**Depends on:** G3.
**Acceptance:** After push, `cosign verify <image>@sha256:... --certificate-identity-regexp='.*proof-of-action.*' --certificate-oidc-issuer='https://token.actions.githubusercontent.com'` returns OK.

### Track B (Data encryption)

#### G6. Redis TLS
**Deliverable:** `scripts/setup_redis.sh` generates self-signed cert + key; launches Redis with `--tls-port 6391 --port 0 --tls-cert-file ... --tls-key-file ... --tls-ca-cert-file ...`. `stores/private_store.py` + `public_store.py` connect with `ssl=True` and verify cert. Old plaintext port disabled.
**Depends on:** nothing.
**Acceptance:**
```bash
redis-cli -p 6391 --tls --cacert ./certs/ca.crt --cert ./certs/client.crt --key ./certs/client.key ping
# PONG

redis-cli -p 6390 ping 2>&1
# Could not connect (plaintext port closed)

python -m proof_of_action.agent  # still works, now over TLS
```

#### G7. AES-GCM envelope on private values
**Deliverable:** `src/proof_of_action/crypto.py` exposing `encrypt(action_id, plaintext: bytes) -> bytes` (nonce || ciphertext || tag) and `decrypt(action_id, envelope) -> bytes`. `save_thread` / `save_draft` in `private_store.py` wrap values before `SET`; `load_thread` / `all_threads` unwrap after `GET`. Master key from `POA_MASTER_KEY` env; generated once via `scripts/keygen.sh`.
**Depends on:** nothing.
**Acceptance:**
```bash
# As the public user, fetch the raw bytes of a private key — should be
# ciphertext, not plaintext. Then decrypt and verify it matches.
redis-cli -p 6391 --tls ... --user agent_private GET private:thread:t_001 | head -c 32 | xxd
# Not readable as JSON — binary envelope

python -m proof_of_action.agent  # runs clean
tests/test_crypto.py::test_roundtrip  # passes
```

### Track C (Audit & artifact — integrations)

#### G5. `cited.md` emits image digest + SBOM hash + cosign cert fingerprint
**Deliverable:** `stores/public_store.py::build_cited_md` (or wherever cited.md is constructed) appends a `## Provenance` section with:
- `image_digest` (from env `POA_IMAGE_DIGEST` populated by CI or local build)
- `sbom_sha256` (syft output hashed)
- `cosign_cert_fingerprint` (from signing log)
- `chainguard_base_digest` (from `.chainguard-digest`)
**Depends on:** G2, G4.
**Acceptance:** `./scripts/demo.sh && grep -A4 "## Provenance" artifacts/cited.md` shows all four values non-empty.

#### G8. `scripts/doctor.sh` — single-command verification
**Deliverable:** Shell script that runs, in order:
1. Verify image pulled matches pinned digest
2. `cosign verify` on the image
3. `grype` no findings ≥ high
4. Redis TLS handshake + cert chain valid
5. Public user fetch of a private key returns ciphertext (not plaintext JSON)
6. Agent run completes, `cited.md` Provenance block populated
**Depends on:** G1, G2, G4, G6, G7, G5.
**Acceptance:** `./scripts/doctor.sh && echo OK` exits 0 green.

#### G9. Update `README.md` + `SUBMIT.md`
**Deliverable:** README "Verify it yourself" section with the 6 commands above. SUBMIT.md Accomplishments list updated.
**Depends on:** G8.
**Acceptance:** Follow the README copy-paste, everything returns OK.

---

## Phase H — Tier 2: "Cryptographically isolated" (1–2 days, post-G)

### Track A (Supply chain)

#### H5. Distroless final image
**Deliverable:** Final stage is `cgr.dev/chainguard/python:latest-nonroot` (minimal) or if static-Python works, `chainguard/static`. Document attack-surface delta (syscalls, installed packages).
**Depends on:** G2.

### Track B (Data encryption)

#### H1. Two separate Redis processes (unix sockets, disjoint data dirs)
**Deliverable:** `deploy/redis/private.conf` + `deploy/redis/public.conf`. `scripts/setup_redis.sh` starts both. `private_store` connects to `/tmp/poa-private.sock` with 0600 perms; `public_store` to `/tmp/poa-public.sock`. ACL is now defense-in-depth, not the trust root.
**Depends on:** G6.

#### H4. Per-action key derivation
**Deliverable:** `crypto.py::derive_action_key(master, action_id) -> bytes` via HKDF(SHA256, master, info=`poa/v1/action/{action_id}`). `encrypt` / `decrypt` use the derived key, not the master. Stored envelopes carry a version byte.
**Depends on:** G7.

#### H6. Master key from secure store (not env)
**Deliverable:** `scripts/keygen.sh` writes the master key to macOS Keychain (`security add-generic-password`) or `age`-encrypted file at `~/.config/proof-of-action/master.key.age`. Agent prompts for Keychain access / age passphrase on startup. Env var fallback only for CI.
**Depends on:** G7.

### Track C (Audit & artifact)

#### H2. Hash-chained append-only audit stream
**Deliverable:** `src/proof_of_action/audit.py` — `append_event(kind, payload)` writes `(prev_hash, event_hash, ts, payload_sha256, payload)` to a file under `private/audit.log` and Redis `private:audit:log` stream. `verify_chain()` walks the log and confirms no entry tampered.
**Depends on:** nothing (can run parallel).

#### H3. Mirror audit stream to Guild
**Deliverable:** On each `append_event`, also `guild session send` the event_hash + payload_sha256. Divergence is detectable by comparing chains.
**Depends on:** H2.

---

## Phase I — Tier 3: "Math, not trust" (post-hackathon roadmap)

**In this cycle: docs only — `docs/ROADMAP.md` with the below as future work.**

### I1. Azure Confidential Containers (SEV-SNP) or GCP Confidential Space deployment
### I2. Attestation quote verification via Microsoft Azure Attestation / Google CS
### I3. Enclave-held Ed25519 key — artifact signing
### I4. `poa-verify cited.md` — end-user tool that checks attestation quote vs Chainguard image digest
### I5. Differential-privacy bounded summaries — bits-of-information accountant

---

## Parallelization map

```
Tracks kick off simultaneously. G1 is root; once complete, A fans out, B/C run mostly independent.

Time →
t=0h   [G1 docker fix]              [G6 Redis TLS]     [G7 AES-GCM]     [D ROADMAP.md]
t=1h   [G2 pin digest] [G3 grype]                                       (idle)
t=2h   [G4 cosign    ]
t=3h                    [G5 cited.md provenance]       (converges)
t=4h                                 [G8 doctor.sh integration]
t=5h                                 [G9 README]
         ────────── Phase G complete ──────────
t=6h   [H5 distroless]  [H1 unix sockets]  [H4 HKDF]  [H2 audit chain]
t=8h                     [H6 keychain]                 [H3 guild mirror]
```

## How to dispatch

Each task block above is self-contained: files listed, acceptance command listed, dependencies listed. To spawn a subagent for Track B:

> "Implement G6 and G7 per `docs/PLAN.md`. Do not touch Track A or C files. Report back with the acceptance command output."

Same pattern for Track A or Track C.

## Stop conditions

- **Stop and report** if a task's acceptance test fails after one honest fix attempt — do not recurse.
- **Stop and report** if a dependency is missing (e.g., G5 starting before G2 lands).
- **Stop and report** before any operation that pushes to a registry, modifies GHA secrets, or rotates the master key.
