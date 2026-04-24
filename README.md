# Proof-of-Action

> **Self-hostable OpenHuman** — a personal AI agent that acts on your private
> context, then publishes a redacted, externally-verifiable public record of
> what it did. Private reasoning stays local. Only typed, redacted projections
> cross to the hosted public plane.

Most hackathon agents dump raw outputs. We built the firewall between
**private reasoning** and **public proof**, enforced at three layers:
infrastructure (Redis ACL), type system (`boundary.py` projections), and
independent audit (Guild).

---

## Scope of the privacy claim

We are careful about what we claim. Two honest boundaries:

**Defended (by our code, demonstrable):**

- Private data never crosses from the local/private plane into the hosted
  /public plane except through typed projections defined in `boundary.py`.
- Redis ACL rejects cross-zone writes at the infra layer — the public
  client gets `NOPERM` from Redis itself if it tries to touch `private:*`.
- The public artifact (`cited.md`) contains zero substrings of private
  fields — enforced by a leak test scanning names, emails, phone numbers,
  URLs, and multi-word body phrases.
- Public artifact hashes are peppered per deployment, so the sha256 refs
  in `cited.md` resist dictionary / rainbow attacks.

**Accepted as trusted (inside the private TCB, not outside):**

- **Anthropic API** — prompts carrying private context reach Claude. We
  accept the LLM provider as a reasoning-trust-computing-base and document
  it here. Zero-retention would be added in a production deployment.
- **Local ingest server** — the FastAPI inbox server on localhost:9849
  that reads iMessage/Gmail is part of the private TCB.
- **Your operator machine** — if your laptop is physically compromised,
  so is the private zone. We defend the network boundary, not physical.

**Explicitly out of scope (would be overclaim):**

- Cryptographic privacy / formal proof — we claim *boundary discipline*,
  not *information-theoretic secrecy*.
- Oblivious execution / side-channel defense — batching and day-granularity
  reduce correlation risk, but don't eliminate it.

---

## Architecture

```
YOUR MAC (trust root)                 HOSTED PUBLIC FACE               PUBLIC WEB
─────────────────────                 ─────────────────                ──────────

 ~/Library/Messages/chat.db
            │
            ▼
 ┌───────────────────────┐
 │  Local daemon         │
 │  (reads iMessage,     │         ┌─────────────────────────┐
 │   Gmail, fixtures)    │         │ Chainguard container     │
 │                       │         │                         │
 │  agent.py             │         │ Accepts typed views      │        ┌────────────┐
 │  Redis private zone   │         │ from local daemons       │───────▶│  Insforge  │
 │  boundary.py ─────────┼────────▶│                         │         │  Postgres  │
 │  (typed projection)   │         │ Redis public zone        │         │  Storage   │
 │                       │ HTTPS   │ (ACL: agent_public only) │         │  (live URL)│
 │                       │ typed   │                         │         └────────────┘
 └───────────────────────┘ view    │                         │         ┌────────────┐
                                   │                         │────────▶│   Guild    │
                                   └─────────────────────────┘         │ independent│
                                                                       │   audit    │
                                                                       └────────────┘
       RAW PRIVATE NEVER LEAVES         ONLY TYPED VIEWS                JUDGES HIT THESE
```

---

## Sponsor fit (principled, not logo-stapled)

| Sponsor | Role in the system | Why it's load-bearing |
|---|---|---|
| **Redis** | Two-user ACL firewall: `agent_private` owns `private:*`, `agent_public` owns `public:*`, cross-zone writes get `NOPERM` from Redis itself | The boundary is enforced at infra, not application logic. Live-demoable. |
| **Chainguard** | Minimal, CVE-hardened container for the hosted public face | Smallest possible surface for the public zone code to be compromised |
| **Insforge** | Hosts the public `cited.md` (Storage) and the structured PublicArtifactView rows (Postgres) | The "scoped-out public proof" layer. Live CDN URL judges can hit. Never sees private context. |
| **Guild.ai** | Independent audit of every boundary crossing | The "don't trust our app logic, trust Guild" layer. External verifiability. |
| **Akash** | SDL manifest for the hosted public face. Design-for, not-deployed-live — by design, to demonstrate architectural intent without burning 45 min of demo risk. | "One-click deploy to your own Akash instance" = self-host story |

Guild, Insforge, and Akash are **all** downstream of the boundary — they only
ever receive typed views, never raw private data.

---

## Quickstart

```bash
# 1. Redis (once)
brew install redis
redis-server /tmp/redis-poa.conf

# 2. Install
uv venv && source .venv/bin/activate
uv pip install -e '.[dev]'

# 3. Configure Insforge (trial is self-provisionable)
#    Creates a 24h trial; the claim URL in .env.local keeps it permanently.
cp .env.local.example .env.local    # then fill in ANTHROPIC_API_KEY

# 4. Run the full demo
python scripts/demo.py
```

The demo prints every boundary crossing, writes `artifacts/cited.md`,
uploads to Insforge, and ends with the leak test — which scans 100+
PII fingerprints from the fixture against the generated artifact.

---

## Layout

```
src/proof_of_action/
  boundary.py          ← typed projections, peppered hashing, shared by both planes
  agent.py             ← observe → classify → draft → project → publish
  redaction.py         ← leak-scan: emails, phones, names ≥3 chars, 3-grams
  stores/
    private_store.py   ← Redis agent_private client — ~private:* only
    public_store.py    ← Redis agent_public client  — ~public:* only
  actions/
    draft.py           ← Claude-backed draft (inside private TCB)
    human_review.py    ← Guild workflow trigger (OpenhumanView only)

scripts/
  setup_redis.sh       ← ACL SETUSER for the two keyspace-restricted users
  ingest_json.py       ← load any JSON inbox dump into private Redis
  demo.py              ← one-command judge demo
  publish.py           ← cited.md + Insforge storage upload

deploy/
  akash-public-workers.yaml  ← SDL for the hosted public face

tests/
  test_boundary.py     ← leak test + ACL enforcement test

Dockerfile             ← Chainguard Python base, for the hosted public face
artifacts/cited.md     ← generated public proof (committed after each run)
private/               ← gitignored; never committed
```

---

## The leak test (the "money shot")

```python
fps = private_fingerprints(fixture_contexts, generated_drafts)
# 131 fingerprints captured: names, first-names, email handles, phones,
#   URLs, subject lines, and all 3-grams from bodies
leaks = scan_for_leaks(open("artifacts/cited.md").read(), fps)
assert not leaks, f"BOUNDARY BROKEN: {leaks}"
```

If this ever fails, the boundary broke. It's the continuous-integration
complement to the infra-layer Redis ACL check.

---

## What would harden this further (honest roadmap)

- **Split the agent into two processes** — so the private-Redis client
  and the public-Redis client are never held in the same memory space.
  Eliminates the "prompt injection reorders control flow" risk.
- **Local LLM** (Ollama / llama.cpp) so Anthropic leaves the TCB.
- **Zero-retention agreement** with the LLM provider if staying hosted.
- **Signed attestations** of the Chainguard container (TPM/enclave).
- **Differential privacy** on the public counts so aggregate queries
  don't enable per-user inference.

---

Built at **Ship to Prod — Agentic Engineering Hackathon**, AWS Builder Loft, Apr 24 2026.
