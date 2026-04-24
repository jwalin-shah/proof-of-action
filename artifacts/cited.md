# Proof-of-Action — Public Citation

> An agent took action on private context. This artifact is the
> public, redacted, verifiable record. Private content stays local.

## What this artifact proves

**Defended (by our code):** No private field value appears in this
document. Refs are peppered sha256 commitments, not reversible.
Downstream services (Guild, Insforge) only see typed projections.

**Trusted (inside the private TCB):** Anthropic API (no ZDR by
default — documented), local inbox ingest server, operator machine.

**Out of scope (would be overclaim):** cryptographic privacy,
oblivious execution, side-channel resistance beyond day-granularity batching.

## Activity summary

- Actions: **1**
- Days active: 2026-04-24
- By kind: {'draft_reply': 1}
- By status: {'pending_review': 1}

## Actions (hashed)

### `act_9b6ac121` — draft_reply — 2026-04-24

- Status: `pending_review`
- Private evidence referenced:
  - `inbox_thread` → `sha256:aeecff973b28a3ba2562f81e28f6b231`
  - `draft` → `sha256:ed2884acbfce81a77a65f744cfdcb9d3`

## Verifiability

Each sha256 hash commits to a private item held only on the
operator's machine. A reviewer can request a local verification
(`scripts/verify_hash.py <hash>`) to confirm an item exists
without the item ever being published.

## Infrastructure

- **Redis** (two-user ACL): enforces the private/public keyspace split at the infra layer.
- **Chainguard** (container): minimal, CVE-hardened base image for the private zone.
- **Guild.ai** (orchestration): audit trail of boundary crossings + human review workflow.
- **Insforge** (hosting): serves this public artifact; never sees private context.
- **Akash** (decentralized compute): public research workers; designed for, deploy manifest in `deploy/`.

_Generated 2026-04-24 — day-granularity is intentional._