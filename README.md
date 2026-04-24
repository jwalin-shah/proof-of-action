# Proof-of-Action

> **Self-hostable OpenHuman** — a personal AI agent that acts on your private
> context, then publishes a redacted, externally-verifiable public record of
> what it did. Private reasoning stays local. Only typed, redacted projections
> cross to the hosted public plane.

Most hackathon agents dump raw outputs. We built the firewall between
**private reasoning** and **public proof**, enforced at four layers:
infrastructure (Redis ACL + Postgres RLS), type system (`boundary.py`
projections), and independent audit (Guild).

---

## Three ways to verify this works

Live dashboard: **https://q7haa32f.insforge.site**

### 1. Zero setup (30 seconds)

Sign up on the dashboard (email or Google). Click the green **"run demo"** button.
A synthetic agent run lands in *your* row (owned by your `auth.uid()`). The
stats counter increments. A `boundary_crossing` appears: `68 private → 3 public,
leak-check ✓`. A Guild audit URL is attached.

This proves: multi-tenancy via Postgres RLS, boundary audit logging, and
`leak_check_passed` enforcement — all without a single line of local setup.

### 2. Clone and run against fixtures (3 minutes)

```bash
git clone https://github.com/<you>/proof-of-action
cd proof-of-action
bash scripts/onboard.sh      # deps + Redis ACL + InsForge link + smoke test
bash scripts/doctor.sh       # health check (proves the NOPERM boundary is live)
```

`onboard.sh` is interactive and idempotent. It:

1. Installs Python deps via `uv` into `.venv`.
2. Starts a local Redis on port 6390 with two-user ACL (`agent_private`,
   `agent_public`) — this is the infra-layer privacy boundary.
3. Walks you through signing up on the hosted InsForge dashboard (RLS
   isolates your rows from every other user).
4. Writes `.env.local` (gitignored).
5. Runs a smoke test end-to-end: Python → boundary projection → Redis
   public → InsForge `finalize-action` edge function → Postgres row
   visible on the dashboard.

`doctor.sh` actually **attempts a cross-zone Redis write** and asserts the
`NOPERM` rejection — the infra-layer boundary is live, not a static claim.
It also checks that the master key lives in Keychain (not `.env.local`), the
mTLS certs are in place if enabled, and that your private LLM endpoint is
reachable with the model loaded.

### 3. Swap in your own private LLM (any Ollama-compatible endpoint)

The draft step works with any `/api/chat`-speaking server. Default is
**Ollama on Akash GPU** (deploy SDL in `deploy/akash-ollama-gpu.yaml`).
Other drop-ins: Venice.ai, Near AI, vLLM, or local Ollama on your laptop.

```bash
# Example: llama3.1:8b on Akash, pulled once after lease is live
curl -X POST https://<your-akash-url>/api/pull -d '{"name":"llama3.1:8b"}'

# Point the agent at it
cat >> .env.local <<EOF
POA_LLM=ollama
POA_OLLAMA_URL=https://<your-akash-url>
POA_OLLAMA_MODEL=llama3.1:8b
EOF

./scripts/demo.sh
```

The action log records the exact TCB label per run
(`remote_ollama_operator_hosted`, `local_ollama`, `anthropic_tcb`, or
`no_llm`) so the privacy boundary is machine-readable, not a marketing
claim. We deliberately do **not** ship the private worker itself to
Akash — moving it off your laptop would collapse the thesis.

### 4. Full Gmail run (only if pre-allowlisted)

Gmail OAuth uses the `gmail.readonly` restricted scope. Google blocks this
for anyone not on our GCP OAuth consent screen's test-user allowlist. If
you're a judge we've pre-added, run:

```bash
.venv/bin/python scripts/onboard.py          # Gmail OAuth consent flow
POA_SOURCE=gmail .venv/bin/python -m proof_of_action.agent
```

Your refresh token lands at `~/.config/proof-of-action/gmail-token.json`
(mode 0600, local only) — it never leaves your Mac.

Everyone else: see the demo video below for the full Gmail run on the
operator's own inbox.

**What stays on your Mac**: iMessage/Gmail content, Redis `private:*` zone,
LLM drafts, Gmail refresh token. **What crosses to the public plane**: only
typed `PublicArtifactView` rows — no raw bodies, no emails, no phone numbers.

---

## Scope of the privacy claim

We are careful about what we claim. Two honest boundaries:

**Defended (by our code, demonstrable):**

- Private data never crosses from the local/private plane into the hosted
  /public plane except through typed projections defined in `boundary.py`.
- Redis ACL rejects cross-zone writes at the infra layer — the public
  client gets `NOPERM` from Redis itself if it tries to touch `private:*`.
- Redis connections are mTLS (G6): the private worker presents a client
  cert pinned to a local CA. A leaked password alone can't open a
  socket — the attacker also needs `private/tls/agent.key` off the
  operator's disk. Bootstrap with `./scripts/tls-bootstrap.sh`, start
  with `redis-server deploy/redis-tls.conf`, enable via `POA_REDIS_TLS=on`.
- Every `private:*` value is AES-GCM wrapped (G7) with the Redis key
  bound as AAD; a `.rdb` dump yields only ciphertext.
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

The agent runs against any OpenAI-compatible endpoint, so self-hosters can swap
Anthropic out for an open-weights model without touching agent code. The
`deploy/akash-public-workers.yaml` SDL is a recipe template for hosting your
chosen model on Akash — current target models (Kimi-K2 preferred, Qwen 2.5 32B
pragmatic, Llama 3.1 70B alternative) and GPU tiers are documented inline. This
session ships the recipe, not a live lease.

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
