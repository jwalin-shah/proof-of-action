# Agent Notes

This repo's central promise is a privacy boundary: private context stays on the
operator machine, and only typed, redacted public views cross into hosted or
external systems.

## Boundary Vocabulary

- `PrivateContext` and `PrivateDraft` are private-plane data. Do not expose raw
  bodies, names, emails, participants, draft text, or precise timestamps outside
  the private plane.
- Public views are the only boundary-crossing shapes:
  `PublicArtifactView`, `OpenhumanView`, and `VapiView`.
- `PROJECTION_REGISTRY` in `src/proof_of_action/boundary.py` is the local
  contract for every public view. It records each view's target plane, allowed
  fields, and verifier policy.
- `hash_refs_only` means the public view may refer to private data only through
  peppered content hashes. `tts_safe_script` means the voice payload must stay
  scripted and non-disclosing.
- Downstream services such as Insforge, Guild, Akash-hosted public workers, and
  public dashboards are public-plane consumers. Treat them as able to receive
  typed projections only.

## Work Rules

- Keep privacy-boundary changes close to `boundary.py`, `redaction.py`,
  `stores/`, and their tests unless the task explicitly widens scope.
- When adding a new public view, register it in `PROJECTION_REGISTRY` and add a
  registry test that checks target plane, allowed fields, and verifier policy.
- Do not make service-backed tests the default proof for a docs or type-contract
  change. Prefer local, non-mutating tests first.
- Do not commit secrets, `.env.local`, private Redis data, Gmail tokens,
  Keychain material, TLS private keys, or generated private artifacts.
- If a test talks to Redis, Insforge, Guild, Gmail, Akash, or a live LLM, call it
  out as service-backed in the PR or workpad.

## Validation

Fast local, non-mutating validation for projection and crypto work:

```bash
PYTHONPATH=src python3 -m pytest tests/test_projection_registry.py tests/test_crypto.py -q
```

Broader boundary validation that may require local Redis ACL setup:

```bash
POA_LLM=template POA_MASTER_KEY=1111111111111111111111111111111111111111111111111111111111111111 REDIS_PORT=6390 \
  uv run --python 3.11 --extra dev pytest tests/test_boundary.py tests/test_crypto.py -q
```

Full PR validation also includes Ruff and the hosted dashboard build; see
`README.md` for the current CI command block.
