# Chainguard: minimal, CVE-hardened Python base.
# The private zone runs here — smallest possible attack surface.
#
# Phase G1: multi-stage (builder venv copied into runtime stage).
# Phase G2: bases pinned by digest. Mirrored in .chainguard-digest so CI and
# cited.md can cite the exact image hash. Refresh with scripts/pin-chainguard.sh.
ARG BUILDER_BASE=cgr.dev/chainguard/python:latest-dev@sha256:e2c6edb2eda713219a9a1ba5db7ca0b8bb3ac0a68068956edb85421026dfffdd
ARG RUNTIME_BASE=cgr.dev/chainguard/python:latest@sha256:e4838943e7ed886c221cdd1e9a6914e0d3c5f0b0c238a419db66e6b1b4b0f93e

# ─── builder ────────────────────────────────────────────────────────────
FROM ${BUILDER_BASE} AS builder
USER nonroot
WORKDIR /app

# Isolated venv so the final stage just needs to copy /home/nonroot/venv.
RUN python -m venv /home/nonroot/venv
ENV PATH=/home/nonroot/venv/bin:$PATH

COPY --chown=nonroot:nonroot pyproject.toml ./
COPY --chown=nonroot:nonroot src/ ./src/

RUN pip install --no-cache-dir .

# ─── runtime ────────────────────────────────────────────────────────────
FROM ${RUNTIME_BASE}
USER nonroot
WORKDIR /app

COPY --from=builder --chown=nonroot:nonroot /home/nonroot/venv /home/nonroot/venv
ENV PATH=/home/nonroot/venv/bin:$PATH

# Runtime assets the agent reads at execution time. Source is already in the
# installed wheel; these are the data / scripts / fixtures that live outside.
COPY --chown=nonroot:nonroot fixtures/ ./fixtures/
COPY --chown=nonroot:nonroot scripts/ ./scripts/
COPY --chown=nonroot:nonroot conftest.py ./

ENTRYPOINT ["python", "-m", "proof_of_action.agent"]
