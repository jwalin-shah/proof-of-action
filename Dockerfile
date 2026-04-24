# Chainguard: minimal, CVE-hardened Python base.
# The private zone runs here — smallest possible leak surface.
FROM cgr.dev/chainguard/python:latest-dev AS builder
WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

FROM cgr.dev/chainguard/python:latest
WORKDIR /app
COPY --from=builder /app /app
COPY --from=builder /home/nonroot/.local /home/nonroot/.local
ENV PATH=/home/nonroot/.local/bin:$PATH
USER nonroot
ENTRYPOINT ["python", "-m", "proof_of_action.agent"]
