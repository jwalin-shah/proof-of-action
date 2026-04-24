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

**How it enforces the privacy boundary — at three layers:**

1. **Infrastructure** — Redis two-user ACL. `agent_private` owns `private:*`, `agent_public` owns `public:*`. The public client attempting a private write gets `NOPERM` from Redis itself.
2. **Type system** — `boundary.py` defines `PrivateContext`, `PrivateDraft` (private side) and `PublicArtifactView`, `OpenhumanView`, `VapiView` (public side). Only typed views cross the boundary.
3. **External audit** — every boundary crossing is logged to an independent Guild session. You don't have to trust our app logic; you can inspect Guild's immutable record.

**Tested with a leak detector** that scans 131 PII fingerprints (names ≥3 chars, email local-parts, phones, URLs, 3-grams from bodies) against the public artifact. Fails loud if anything slips through.

### How we built it

- **Redis** (two-user ACL firewall, verified with NOPERM)
- **Chainguard** (minimal CVE-hardened Python base for the hosted public face)
- **Insforge** (Postgres for structured action records + Storage bucket serving `cited.md` and the live dashboard — trial auto-provisioned via agent API in seconds)
- **Guild** (per-run audit sessions, boundary crossings recorded via `guild session send`)
- **Akash** (SDL manifest for self-host deploy; design artifact so anyone can spin up their own instance)
- **Anthropic Claude** (drafting, documented as inside the reasoning TCB)

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
