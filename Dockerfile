# Chainguard: minimal, CVE-hardened Python base.
# The private zone runs here — smallest possible attack surface.
#
# Phase G1: multi-stage fixed (builder installs into a venv that the final
# stage copies). Phase G2 will pin these to @sha256:... digests via
# .chainguard-digest.
ARG BUILDER_BASE=cgr.dev/chainguard/python:latest-dev
ARG RUNTIME_BASE=cgr.dev/chainguard/python:latest

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
