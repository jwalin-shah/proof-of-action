# Proof-of-Action — Phase I Roadmap

**Status as of 2026-04-24:** Phases A–F complete, Phase G (supply-chain hardening,
Redis TLS, AES-GCM envelope, hash-chained audit) and Phase H (distroless, unix
sockets, HKDF per-action keys, keychain master, Guild-mirrored chain) scoped in
`docs/PLAN.md`. This document specifies **Phase I** — Tier 3, "math, not trust."

Phase I moves the private plane off the operator's laptop and into a verifiable
confidential-compute enclave. The goal is that a third party (a judge, an
auditor, a paranoid user) can take a `cited.md` file, run a single CLI command,
and receive a binary answer: "yes, this artifact was produced by the pinned
Chainguard image digest, running inside an SEV-SNP-attested TEE, signed by a key
that never left the enclave."

At Tier 3 we stop asking the verifier to trust our code, our CI, our machine, or
us. We ask them to trust AMD, Intel, Google, or Microsoft — and the math.

**This is a post-hackathon roadmap.** Nothing in Phase I ships in the submission.
The work items below are sized for a small team over ~3–5 weeks of focused work.

---

## Design principle

Every Phase I item is a **replacement of an accepted-trust assumption with a
verifiable one**. The README's "Accepted as trusted" list (Anthropic, local
ingest, operator machine) shrinks by one item per work unit:

| Today's trust assumption | Phase I replacement | Work unit |
|---|---|---|
| Operator laptop is private TCB | TEE with SEV-SNP attestation | I1, I2 |
| Artifact hash proves integrity | Enclave-held Ed25519 signature | I3 |
| Verifier trusts our audit dashboard | `poa-verify` — offline math | I4 |
| Redaction-by-string-scan is sufficient | Bounded mutual information | I5 |

Each unit is independently landable. I1 → I2 → I4 is the shortest path to a
demonstrable "run this, trust nobody" flow. I3 is parallel to I2. I5 is
orthogonal and can be designed while the attestation track lands.

---

## I1. Confidential compute deployment (5–7 days)

**Goal:** The public-plane container — today running as a Chainguard image on
whatever hosting the operator chose — runs inside a hardware-attested TEE. The
enclave measurement is recorded at deploy time and reproducible from the
Chainguard digest pinned in Phase G2.

### Candidate platforms

| Platform | Hardware | Attestation | Operator model | Price signal |
|---|---|---|---|---|
| **Azure Confidential Containers on ACI** | AMD SEV-SNP (Milan) | Microsoft Azure Attestation (MAA) | Managed — submit OCI image, get a URL | ~$0.13/vCPU-hr, SEV-SNP no premium over standard ACI |
| **GCP Confidential Space** | AMD SEV, Intel TDX (beta) | Google-attested "Workload Identity" tokens | Image must be published to Artifact Registry; runs as a one-shot or long-lived Compute Engine VM | Standard n2d-confidential pricing, ~15% over non-confidential |

### Comparison

**Azure Confidential Containers** is closer to our deployment model. Our public
plane is already a container; Azure accepts an OCI reference and attests the
running image without modification to the container code. The attestation
endpoint is a first-class Azure resource (MAA), and the quote format (a JWT
signed by Microsoft, wrapping the raw SEV-SNP quote) is trivial to consume from
Python. The ergonomic win is large.

**GCP Confidential Space** is more opinionated. It requires the container to
run as a "workload" on a Confidential Space image, which injects a sidecar that
issues attestation tokens on request (`metadata.google.internal`). Tokens are
OIDC-signed by Google, with custom claims binding `image_digest`,
`image_reference`, and optional `audience`. The upside is that Google takes care
of quote freshness and measurement → digest mapping. The downside is that any
feature we need beyond the default sidecar (e.g. egressing a quote to a
non-Google verifier) requires more glue.

### Preference

**Azure Confidential Containers.** Three reasons:

1. **Image portability.** Azure attests the OCI digest we already pin in Phase
   G2. No Artifact-Registry-specific republish step, no GCP-flavored wrapper
   image. The Chainguard digest stays the single source of truth.
2. **Attestation consumability.** MAA returns a JWT whose JWK set is public,
   stable, and documented. `poa-verify` (I4) can validate offline with any
   JWT library. GCP's workload identity tokens work too, but the claims we
   actually care about (the launch policy, the image digest) are further from
   the SEV-SNP raw measurement.
3. **No infra coupling.** GCP Confidential Space pushes us toward Compute
   Engine + VPC. Azure CACI is a single-resource deploy. For a hackathon
   project extending into a side-project, the lower-infra option wins.

### Fallback

If Azure pricing or availability changes, GCP Confidential Space is a drop-in
replacement for the attestation primitive. The rest of Phase I (I3, I4) is
portable across both — `poa-verify` simply switches JWK sources and claim
names.

### Acceptance

```bash
# One-shot deploy
az containerapp create \
  --resource-group poa \
  --name poa-public \
  --image ghcr.io/proof-of-action/public-worker@sha256:<pinned> \
  --cc-profile "confidentialContainers=on" \
  --environment poa-env

# Verify it's actually attested
az confcom attest --container-name poa-public
# → returns MAA JWT with claims.x-ms-sevsnpvm-reportdata and image digest
```

---

## I2. Attestation quote verification (4–5 days)

**Goal:** Every public artifact (`cited.md`) carries a MAA-signed attestation
quote proving that the container that produced it was running on attested
SEV-SNP hardware, executing the exact Chainguard image digest pinned in Phase
G2.

### Flow

```
┌───────────────────────────┐
│ Enclave (public worker)   │
│                           │
│ 1. On boot, request SEV-  │
│    SNP quote from PSP     │
│ 2. Send quote to MAA      │
│ 3. MAA verifies signature │
│    vs AMD root, returns   │
│    JWT wrapping quote     │
│ 4. Enclave caches JWT     │
│    until quote TTL (24h)  │
└───────────────────────────┘
             │
             │ (enclave writes artifact)
             ▼
┌───────────────────────────┐
│ cited.md                  │
│ ## Provenance             │
│   image_digest: sha256:…  │  ◀── from Phase G5
│   sbom_sha256: …          │
│   cosign_cert: …          │
│   attestation_jwt: eyJ…   │  ◀── NEW in I2
│   enclave_measurement: …  │  ◀── NEW in I2 (raw SEV-SNP MRENCLAVE-equivalent)
└───────────────────────────┘
             │
             │ (verifier fetches cited.md)
             ▼
┌───────────────────────────┐
│ poa-verify                │
│                           │
│ 1. Parse Provenance block │
│ 2. Decode attestation_jwt │
│ 3. Fetch MAA JWKS from    │
│    shared-eus.attest.     │
│    azure.net/certs        │
│ 4. Verify JWT sig chain   │
│ 5. Extract x-ms-sevsnp…   │
│    report-data + image    │
│    digest claim           │
│ 6. Assert image digest    │
│    matches pinned digest  │
│    from .chainguard-      │
│    digest or config       │
└───────────────────────────┘
```

### What each step defends

- **Step 3 (JWKS fetch)** means the verifier trusts Microsoft's attestation
  service signing keys, not our code. This is the trust reduction.
- **Step 5 (report-data)** contains a 64-byte slot populated by the enclave at
  quote-generation time. We use it to bind the Ed25519 public key (I3) to the
  quote — so a stolen key is not enough; you also need a fresh quote.
- **Step 6 (digest match)** is the money step. If our CI builds a new image
  with a supply-chain compromise, the pinned digest changes; the verifier
  detects mismatch and refuses the artifact.

### Why JWT over raw quote

The raw SEV-SNP quote is ~1.2 KB binary, signed by the AMD PSP (Platform
Secure Processor). Verifying it offline requires the AMD root VCEK cert chain,
which itself requires knowing the CPU's chip ID. MAA does that work and hands
back a JWT we can verify with a standard library. The cost is trusting
Microsoft's attestation endpoint to not lie — mitigated by MAA being open to
public scrutiny and pinning a specific MAA region endpoint.

### Non-goals

- We do not re-verify the AMD VCEK chain inside `poa-verify`. That's a 200-line
  ASN.1 dance. If a verifier wants that level of paranoia, they can run their
  own raw-quote verifier; the MAA response contains the raw quote verbatim.
- We do not attest the Anthropic API round-trip. Anthropic remains a trusted
  TCB element until a local-LLM path lands (separate roadmap item).

---

## I3. Enclave-held Ed25519 signing key (3 days)

**Goal:** Every `PublicArtifactView` (and the cited.md that embeds the view) is
signed by an Ed25519 key that was generated inside the TEE, whose private half
never leaves enclave memory, and whose public half is bound to the attestation
quote.

### Lifecycle

1. **Enclave boot.** `crypto.py::generate_signing_keypair()` runs inside the
   confidential container. Private key lives in enclave RAM only. Public key
   is emitted to stdout and written to `/artifacts/pubkey.ed25519`.
2. **Quote generation.** The SEV-SNP quote request populates the 64-byte
   `report_data` field with `sha256(pubkey_raw_32_bytes)`, padded to 64.
   This cryptographically binds the pubkey to the attested enclave — a
   stolen pubkey is worthless without a matching fresh quote.
3. **Pubkey publication.** On first boot, the enclave publishes the pubkey to
   Insforge Storage at `public/keys/<measurement>.ed25519`. The URL is
   recorded in cited.md's Provenance block.
4. **Per-artifact signing.** Before `publish_artifact`, the enclave computes
   `sig = ed25519_sign(priv, sha256(cited.md_body))` and appends a
   `## Signature` block:
   ```
   ## Signature
   pubkey_url: https://…/public/keys/<measurement>.ed25519
   body_sha256: sha256:…
   signature: ed25519:…
   ```
5. **Key rotation.** On every container restart (ACI restart, deploy), a new
   keypair is generated. Old pubkeys remain valid for their historical
   artifacts — the pubkey_url is content-addressed by measurement, so it
   survives rotation.

### Why Ed25519 not RSA

Ed25519 signatures are 64 bytes, pubkeys 32 bytes. Fits in the SEV-SNP
report_data slot with room to spare. Deterministic (no nonce reuse risk inside
an enclave where entropy may be questionable on boot). Fast enough that
per-artifact signing is free.

### What this buys us

Before I3: a verifier who re-fetches `cited.md` from Insforge Storage trusts
that (a) our publish code wrote the file faithfully and (b) Insforge hasn't
been tampered with. After I3: the verifier checks the signature against a
pubkey bound to an attested enclave measurement. Tampering is detectable
without trusting any hosting layer.

---

## I4. `poa-verify` CLI (4–6 days)

**Goal:** A single-binary, dependency-light CLI that any third party can run
against a `cited.md` URL or local path and get a green/red answer.

### Interface

```bash
poa-verify https://insforge.site/storage/poa/artifacts/a_001/cited.md
# or
poa-verify ./artifacts/cited.md --pinned-image sha256:abc…

# Output (green path):
# ✓ Provenance block parsed
# ✓ MAA JWT signature valid (issuer: sharedeus.eus.attest.azure.net)
# ✓ Enclave measurement matches pinned image digest
# ✓ Pubkey bound to attestation (report_data match)
# ✓ Artifact signature valid
# VERIFIED: this artifact was produced by image sha256:abc… inside
#           an SEV-SNP-attested enclave, signed by key 0xdeadbeef.

# Exit code: 0 if all green, 1 on any failure, 2 on malformed input.
```

### 5-step verify algorithm

```python
def verify(cited_md: str, pinned_image_digest: str | None) -> VerifyResult:
    # Step 1: parse
    prov = parse_provenance_block(cited_md)
    sig_block = parse_signature_block(cited_md)
    if not prov or not sig_block:
        return fail("malformed: missing Provenance or Signature block")

    # Step 2: fetch MAA JWKS and verify attestation JWT
    jwks = http_get(f"{prov.maa_issuer}/certs").json()
    try:
        claims = jwt.decode(
            prov.attestation_jwt,
            jwks,
            algorithms=["RS256"],
            issuer=prov.maa_issuer,
        )
    except InvalidSignatureError:
        return fail("attestation JWT signature invalid")

    # Step 3: measurement → image digest match
    enclave_image = claims["x-ms-sevsnpvm-hostdata"]  # image digest claim
    expected = pinned_image_digest or prov.image_digest
    if enclave_image != expected:
        return fail(f"image digest mismatch: enclave={enclave_image} "
                    f"expected={expected}")

    # Step 4: pubkey bound to attestation
    report_data = bytes.fromhex(claims["x-ms-sevsnpvm-reportdata"])
    pubkey = http_get(prov.pubkey_url).content  # 32 bytes ed25519
    if sha256(pubkey).digest() != report_data[:32]:
        return fail("pubkey not bound to attestation report_data")

    # Step 5: artifact signature
    body = strip_signature_block(cited_md).encode()
    if not ed25519_verify(pubkey, sig_block.signature, sha256(body).digest()):
        return fail("artifact signature invalid")

    return ok(image=enclave_image, pubkey_fp=fingerprint(pubkey))
```

### Distribution

Single `uv tool install proof-of-action-verify` — CLI ships as its own package
so the verifier doesn't install the full agent code (which they shouldn't need
to trust). Dependencies: `PyJWT`, `cryptography`, `httpx`. All three are
well-audited. Total closure <5 MB.

### Out of scope for v1

- Revocation checking (MAA doesn't publish a CRL for enclave measurements).
- Historical attestation replay — quotes have a TTL; verifying a 2-year-old
  artifact requires archived MAA JWKS, which Microsoft does not guarantee to
  retain. We document this as a known limitation and recommend mirroring JWKS
  at artifact-publish time (added as a roadmap item, not I4).

---

## I5. Differentially-private summary budget (6–8 days)

**Goal:** Bound the mutual information between private inputs (iMessage/Gmail
bodies, contact names) and public outputs (`PublicArtifactView`, public counts,
topic tags). Today's redaction is syntactic — we scan for substrings. I5 makes
it semantic and compositional: every public emission "spends" from a per-user
information budget, and actions are refused at the policy layer when the
budget is exhausted.

### Why string-scan isn't enough

The Phase F leak test catches direct substring leakage: names, emails,
phone numbers, 3-gram body phrases. It does not catch:

- **Correlation leaks.** Publishing "drafted 3 responses to investor threads"
  reveals the presence of investor conversations. Over many days, the joint
  distribution of published counts over topics is a fingerprint.
- **Topic inference.** `topic: "finance"` reveals the input was about money.
  One bit, but bits add up.
- **Timing.** Publishing "acted on a thread at 3:14 AM PT" localizes the user
  and may identify specific correspondents.

A differentially-private accountant gives us a principled way to reason about
these. Each public emission is modeled as a query; each query has an ε cost;
total spend over a time window is bounded.

### Design

```
┌─────────────────────────────────┐
│ boundary.py                     │
│                                 │
│ PublicArtifactView (typed)      │
│    │                            │
│    ▼                            │
│ dp_accountant.score(view)       │
│    │                            │
│    ▼                            │
│ if budget.remaining < cost:     │
│   raise BudgetExhausted         │
│ else:                           │
│   budget.spend(cost)            │
│   emit(view)                    │
└─────────────────────────────────┘
```

### Budget model

Per-user, per-rolling-window (7d default):

- **Privacy unit**: one user's inbox over the window.
- **Budget**: ε = 4.0, δ = 1e-6 (tunable per user; matches loose DP literature
  defaults for non-adversarial adversaries).
- **Composition**: Rényi DP (RDP) accountant — strictly tighter than basic
  composition, and it's what Opacus uses in PyTorch. Matches well-trod
  ground.

### Query cost table (initial calibration — requires sensitivity analysis)

| Emission | ε cost | Rationale |
|---|---|---|
| `count_drafts_today` (∈ [0, 50]) | 0.1 | Laplace noise σ=10; coarse |
| `topic_tag` (from fixed 20-topic vocab) | 0.5 | Exponential mechanism over topics |
| `boundary_crossing_summary` (68 private → 3 public) | 0.2 | Count of typed transitions |
| `action_timestamp` (day granularity) | 0.3 | Randomized rounding to day |
| `action_timestamp` (hour granularity) | 1.0 | Refused above ε=4 in most windows |
| `PublicArtifactView.preview` (redacted) | 0.8 | Already redacted; DP covers residual |

Total 7d emission budget ε=4 supports ~5–10 actions/day before refusal. This
is a feature: if a user runs the agent 50x/day, either the budget needs to
scale (per-day limit, not per-window) or the emissions need to be coarser.
The policy layer surfaces `BudgetExhausted` to the UI; the operator chooses
to refuse, coarsen, or extend.

### Why Opacus-style accounting

- **RDP is the right primitive.** It tracks ε as a function of α (Rényi
  order), not as a single number, which gives tight composition bounds for
  repeated small queries — exactly our pattern.
- **It's implemented and tested.** `opacus.accountants.RDPAccountant` is
  production-grade. We reuse the math, not the training-loop plumbing.
- **It composes with future queries.** Adding a new emission type is just
  characterizing its sensitivity and ε cost; the accountant handles the
  rest.

### What this does NOT claim

- **Not semantic privacy.** DP bounds statistical inference from published
  data. It does not prevent the LLM from gossiping in the private plane —
  that's the boundary's job, not the DP layer.
- **Not protection against a user who is the adversary.** The budget is
  per-user; if the user's own agent is the attacker, they can just read their
  own private data.
- **Not calibrated.** The ε costs above are engineering estimates, not
  theorems. A real deployment requires sensitivity analysis per emission:
  "what is the maximum change to this value from adding/removing one private
  record?" This is the standard DP calibration dance and is the bulk of the
  6–8 day estimate.

### Acceptance

```bash
# Run the agent 10x back-to-back on the same user
for i in {1..10}; do python -m proof_of_action.agent; done

# Observe budget drain
poa budget status --user jwalin@example.com
# Window: 2026-04-17..2026-04-24 (7d)
# Spent:  ε=3.8 / ε=4.0
# Next emission ≥ ε=0.3 will be REFUSED

# Next run refuses at the boundary layer, not mid-publish
python -m proof_of_action.agent
# [boundary] BudgetExhausted: ε=0.2 requested, ε=0.2 remaining.
#            Action refused. Coarsen emissions or wait until 2026-04-25.
```

---

## Effort summary

| Item | Days | Depends on | Parallel with |
|---|---|---|---|
| I1. Confidential compute deploy | 5–7 | Phase G2 (pinned digest) | I5 |
| I2. Attestation verification | 4–5 | I1 | I3, I5 |
| I3. Enclave Ed25519 signing | 3 | I1 | I2, I5 |
| I4. `poa-verify` CLI | 4–6 | I2, I3 | I5 |
| I5. DP summary budget | 6–8 | nothing (pure policy layer) | I1–I4 |

**Critical path:** I1 → I2 → I4 = 13–18 days of serial work.
**Total wall-clock** with one engineer on attestation track + one on DP track:
~3 weeks. With a solo contributor, ~5 weeks including calibration and writeup.

---

## What this does NOT do

Honest about the ceiling of Phase I:

- **Does not make the agent oblivious.** An observer with access to enclave
  I/O timing can still correlate actions. Side-channel defense is Phase J
  territory.
- **Does not eliminate Anthropic from the TCB.** Local LLM (Ollama,
  llama.cpp) is a separate track, dependent on model quality reaching
  acceptable floors for drafting workloads. Tracked separately.
- **Does not prove the agent's reasoning is correct.** Attestation proves the
  image that ran; it does not prove the image does what we claim. Code review
  and reproducible builds (Phase G/H) remain the only defense there.

Phase I is the "math, not trust" layer for **the boundary** — not for the
reasoning. That's the right scope. The boundary is the claim we make; the
boundary is what we should be willing to prove.
