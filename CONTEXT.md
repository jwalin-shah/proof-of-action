# Proof-of-Action Context

Proof-of-Action is a local-first action agent. It can read private inbox
context, draft or classify an action, and publish a public proof that an action
happened without publishing the private material that motivated it.

## Domain Model

- The operator machine is the trust root. iMessage, Gmail, local fixtures,
  private Redis keys, drafts, refresh tokens, and private LLM prompts belong
  here.
- The public plane is everything downstream of a typed projection: cited
  artifacts, Insforge rows and storage, Guild audit handoffs, Vapi voice
  payloads, public dashboards, and deployable public workers.
- `boundary.py` is the type boundary between those planes. It owns private
  models, public view models, peppered hash references, topic minimization, and
  the projection registry.
- The projection registry is not a router. It is an auditable contract that says
  which public views exist, where they may go, which fields are allowed, and
  what verification policy applies.

## Current Public Views

- `PublicArtifactView`: public cited-artifact proof. It may include action
  metadata, day-granularity dates, public URLs, status, and peppered private
  hashes.
- `OpenhumanView`: external agent-platform result view. It reports action kind,
  status, and public evidence references, not raw source content.
- `VapiView`: voice-agent payload. It contains an action id, a uniform topic
  label, and a scripted message that must not reveal private content.

## Test Boundaries

Use local, non-mutating tests for type contracts and crypto primitives:

```bash
PYTHONPATH=src python3 -m pytest tests/test_projection_registry.py tests/test_crypto.py -q
```

Use service-backed tests only when the change affects live boundary behavior:

- `tests/test_boundary.py` exercises leak scanning and Redis ACL behavior.
- `scripts/doctor.sh` checks local Redis ACL, optional TLS, Keychain, and local
  LLM readiness.
- `scripts/onboard.sh` and `scripts/demo.sh` can touch local Redis and hosted
  Insforge/Guild-facing paths.

When reporting validation, name whether the command was local/non-mutating or
service-backed so future agents do not overclaim coverage.
