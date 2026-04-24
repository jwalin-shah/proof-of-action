# Chainguard: minimal, CVE-hardened Python base.
# The private zone runs here — smallest possible attack surface.
#
# Phase G1: multi-stage (builder venv copied into runtime stage).
# Phase G2: bases pinned by digest. Mirrored in .chainguard-digest so CI and
# cited.md can cite the exact image hash. Refresh with scripts/pin-chainguard.sh.
ARG BUILDER_BASE=cgr.dev/chainguard/python:latest-dev@sha256:2c0fbbac86b72ebb4bfee15b64d8cd5fd6b49dfe7bb279b5c9f193198a84c1c9
ARG RUNTIME_BASE=cgr.dev/chainguard/python:latest@sha256:18a4fbda8c280978b6aa5329f7acd4dbb106876e76fdc87913855ebf4876f2ff

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
