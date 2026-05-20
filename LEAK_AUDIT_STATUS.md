# Leak Audit Verifier Status

Date: 2026-05-19
Branch: `codex/SYM-272-leak-audit-verifier`

## What It Does

The leak-audit-verifier is implemented in `src/proof_of_action/boundary_verifier.py` as `SharedBoundaryVerifier`.

It verifies a public/private boundary crossing by:

- accepting the private contexts, private drafts, and projected public view for an action;
- computing audit facts: action id, projection type, topic label, private field count, public field count, whether private material appears in the public view, and `leak_check_passed`;
- generating private fingerprints with `private_fingerprints(...)`;
- serializing the `PublicArtifactView` and checking whether any private fingerprint appears in it;
- raising `BoundaryVerificationError` before publish if the public projection leaks private material;
- returning a `BoundaryVerification` object whose payload is reused for Guild audit messages and Insforge boundary-crossing metadata.

The agent loop now runs `observe -> classify -> draft -> project -> audit -> publish`. If verification fails, `agent.run()` returns `status="verify_failed"` at `step="audit"` and does not continue to publish.

## Done

- Added a shared verifier contract: `BoundaryVerifier`, `BoundaryVerification`, `BoundaryVerificationError`, and `SharedBoundaryVerifier`.
- Wired the verifier into `agent.run()` through `run_audit(...)`.
- Ensured publish receives verifier output for `private_field_count`, `leak_check_passed`, and Guild audit payloads.
- Added focused tests for:
  - rejecting a leaky public projection;
  - stable audit counts on a clean projection;
  - agent handling of verifier failure;
  - agent handling of draft and publish failures.
- Kept service-backed boundary tests skippable when Redis is unavailable.

## Validation Run

Command:

```bash
PYTHONPATH=src python3 -m pytest tests/test_agent.py -q
```

Result:

```text
5 passed in 3.52s
```

## Remaining

- Broaden verifier coverage beyond `PublicArtifactView` if `OpenhumanView` and `VapiView` are expected to use the same runtime verifier path. The current protocol names those projection types, but the method signature accepts `PublicArtifactView` specifically.
- Consider checking `PROJECTION_REGISTRY` inside `SharedBoundaryVerifier` so runtime verification enforces each projection's registered target plane, allowed fields, and verifier policy, rather than only using the provided `projection_type` label.
- Consider reusing `scan_for_leaks(...)` directly in the verifier for consistency with `tests/test_boundary.py`; the current verifier duplicates the core "fingerprint appears in serialized artifact" check inline.
- Add a non-service-backed test that verifies publish is not called after a verifier failure, not just that `agent.run()` returns `verify_failed`.

## Blockers

- No code blocker found for the focused verifier path.
- Full service-backed boundary validation was not run here. `tests/test_boundary.py` requires a Redis boundary service on the configured local port and may skip or require local service setup.
