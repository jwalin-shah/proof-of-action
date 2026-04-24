# Submission Drafts

Copy-paste ready. Nothing here gets shipped automatically — you control the send.

---

## Devpost submission

### Project name
**Proof-of-Action — self-hostable OpenHuman**

### Tagline (50 chars max)
`Personal AI agent with a provable privacy boundary`

### Elevator pitch (200 chars)
A personal AI agent that acts on private context (inbox, calendar, messages) and publishes a redacted, externally-verifiable public record of what it did. Private reasoning stays local.

### Description

Most hackathon agents dump raw outputs. We built the firewall.

**What it does.** Reads private context from your inbox (iMessage, Gmail via local FastAPI, JSON dumps). Drafts actions using Claude. Projects the action into a typed public view that cannot, by type, contain private fields. Publishes a redacted `cited.md` with peppered sha256 commitments. Opens a Guild audit session per run for external verification.

**How it enforces the privacy boundary — at four layers:**

1. **Infrastructure (Redis)** — two-user ACL. `agent_private` owns `private:*`, `agent_public` owns `public:*`. The public client attempting a private write gets `NOPERM` from Redis itself. `scripts/doctor.sh` actually *tries* the cross-zone write and asserts the rejection — live proof, not a static claim.
2. **Infrastructure (Postgres)** — Insforge RLS. Every `proof_actions` row is owned by `auth.uid()`. Cross-tenant reads impossible at the database layer.
3. **Type system** — `boundary.py` defines `PrivateContext`, `PrivateDraft` (private side) and `PublicArtifactView`, `OpenhumanView`, `VapiView` (public side). Only typed views cross the boundary.
4. **External audit** — every boundary crossing is logged to an independent Guild session *and* a `boundary_crossings` row in Postgres. You don't have to trust our app logic; you can inspect both immutable records.

**Tested with a leak detector** that scans 131 PII fingerprints (names ≥3 chars, email local-parts, phones, URLs, 3-grams from bodies) against the public artifact. Fails loud if anything slips through.

### How to verify it works (three layers for judges)

1. **Zero setup** — visit https://q7haa32f.insforge.site → sign up → click "run demo". A synthetic agent run lands in *your* RLS-scoped row, with real boundary-crossing audit attached. No local install.
2. **Clone + fixtures** — `bash scripts/onboard.sh` runs the full end-to-end flow against sample threads. `scripts/doctor.sh` actively proves the Redis NOPERM boundary. Works on any Mac with Homebrew.
3. **Full Gmail run** — gated by Google's test-user allowlist for the `gmail.readonly` restricted scope. See demo video for the full real-inbox flow; the refresh token never leaves the operator's Mac.

### How we built it

- **Redis** — three layers of defense on the private keyspace: (1) two-user ACL firewall (NOPERM verified live by `doctor.sh`), (2) mTLS with a pinned local CA and client certs (`deploy/redis-tls.conf`, tls-auth-clients on), (3) AES-GCM envelope encryption on every value with the Redis key bound as AAD — a `.rdb` dump yields only ciphertext. An attacker needs the password *and* the client cert *and* the master key.
- **Chainguard** — minimal CVE-hardened Python base, **pinned by sha256 digest** (`.chainguard-digest`), scanned in CI with grype (High/Critical fails the build), and signed with cosign keyless via Sigstore / GitHub OIDC. The exact digest and `cosign verify` command land in `cited.md`'s Provenance block so any reader can verify supply-chain integrity externally. `scripts/pin-chainguard.sh` refreshes pins via registry API (no docker/crane needed).
- **Insforge** — the full public plane: Postgres with RLS for `proof_actions` / `boundary_crossings` / `guild_sessions`, `finalize-action` and `run-demo` edge functions, Storage bucket, hosted React dashboard with **live Realtime subscriptions** on `boundary:user:<uid>` (per-user channel, not global), **`insforge.emails.send` notifications** on human-review handoff (topic label only — no private content crosses), and Auth. One backend doing six jobs.
- **Guild** — per-run audit sessions that carry the actual boundary metrics (topic label, field counts, leak-check flag, content-commit hashes) — not just a URL. The session is an independent, externally-inspectable record of what crossed the boundary, with zero private content in the payload. Session URLs embedded in `cited.md`.
- **Akash** — **live Ollama GPU deployment** (`deploy/akash-ollama-gpu.yaml`), operator-controlled LLM inference that removes Anthropic from the TCB. The agent sends already-redacted prompts to the Akash endpoint; no big AI company sees content. Per-run TCB label (`remote_ollama_operator_hosted` / `local_ollama` / `anthropic_tcb`) lands in the action log so the privacy boundary is machine-readable. We do *not* deploy the private worker to Akash — that would collapse the "private stays on your laptop" thesis. The `/api/chat` protocol is standard, so the same code path plugs into **Venice.ai**, **Near AI**, **vLLM**, or **LM Studio** with one env var change — Akash is our default, not a lock-in.
- **Anthropic Claude** — backup drafting backend, pluggable via `POA_LLM={anthropic,ollama,template}`. Documented as inside the reasoning TCB when used; fully optional.
- **Google OAuth** — installed-app flow for Gmail read; `gmail.readonly` restricted scope, refresh token local-only.

### Challenges

- External LLM review (Gemini) caught that our initial leak test had `min_len=20`, silently skipping names and short emails. Fixed before submission.
- Codex flagged overclaim: "provable privacy" is not defensible without narrowing. We rewrote the README to claim *boundary discipline to the public plane* — what we can actually prove.
- Navigating sponsor integrations while keeping the pitch focused. Chose 4 deep (Redis, Insforge, Chainguard, Guild) + Akash as design spec rather than 8 shallow.

### Accomplishments

- Redis ACL boundary is enforced at the infra layer — `NOPERM` from Redis itself rejects cross-zone writes. That's *provable*, not app-layer trust.
- Live public dashboard served via Insforge CDN, updates with each demo run.
- Guild audit session URL embedded in every `cited.md` — anyone can verify our claims externally.
- Second-opinion review loop (Codex + Gemini) → real bug fixes pre-submission.

### What we learned

- "Provable privacy" is a phrase you earn, not claim. Narrow the boundary to what you can actually defend.
- Infrastructure-level enforcement (Redis ACL) beats application-level enforcement (type checks). Do both.
- External audit (Guild) is what turns "trust us" into "trust the auditor."
- Static-render > client-fetch when API keys would be exposed.

### What's next

- Split the agent into two OS processes so private and public Redis credentials never coexist in one memory space.
- Local LLM (Ollama) so Anthropic leaves the TCB entirely.
- Signed attestations of the Chainguard container.
- Full OpenHuman-cloud: one-click deploy from the GitHub repo via Akash VCS.

### Built With

`python` `redis` `fastapi` `chainguard` `insforge` `guild.ai` `akash` `anthropic-claude` `pydantic` `pytest` `typescript`

### Try it yourself

- **Live dashboard:** https://q7haa32f.us-east.insforge.app/api/storage/buckets/proof-artifacts/objects/index.html
- **Public `cited.md`:** https://q7haa32f.us-east.insforge.app/api/storage/buckets/proof-artifacts/objects/cited.md
- **Source:** https://github.com/jwalin-shah/proof-of-action
- **One-command demo:** `python scripts/demo.py`

---

## X post (for the #TokensAnd $500 live-build bonus)

Choose one:

### Option A — technical angle (279 chars)

```
Built proof-of-action at #TokensAnd: a personal AI agent where the privacy
boundary is enforced by @Redisinc ACLs (NOPERM from Redis itself), the
public artifact is served by @insforgeai, and every boundary crossing is
audited by @guild_ai.

github.com/jwalin-shah/proof-of-action

@tokensandai
```

### Option B — pitch angle (278 chars)

```
Self-hostable @OpenHumanAgent at #TokensAnd.

Local daemon reads your inbox. Public face hosts a redacted cited.md.
Private stays on your laptop. @Redisinc enforces the boundary, @insforgeai
serves the proof, @guild_ai audits, @akashnet_ will deploy.

github.com/jwalin-shah/proof-of-action

@tokensandai
```

### Option C — screenshot bait (264 chars)

```
My favorite hackathon moment so far: watching @Redisinc reject a cross-zone
write with NOPERM — the privacy boundary enforced at the infra layer, not
app logic.

Self-hostable agent with provable boundary discipline.
#TokensAnd

github.com/jwalin-shah/proof-of-action

@tokensandai
```

**To submit:** post on X → paste link/screenshot → tag sponsors → deadline EOD per the Luma blast.
