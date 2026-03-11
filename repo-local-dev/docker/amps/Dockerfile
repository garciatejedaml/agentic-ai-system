# ─────────────────────────────────────────────────────────────────────────────
# AMPS Server – Linux x86_64 (runs on M1 Mac via Docker --platform linux/amd64)
#
# PREREQUISITE: Place the AMPS Linux tarball in this directory.
#   Accepts any filename matching AMPS*.tar* (e.g. AMPS-5.3.5.60-Release-Linux.tar.gz)
#   1. Register at https://crankuptheamps.com/evaluate
#   2. Download the Linux x86_64 distribution
#   3. Copy it here: repo-local-dev/docker/amps/
#
# Build & run:
#   docker compose --profile amps build
# ─────────────────────────────────────────────────────────────────────────────

# Stage 1: extract AMPS from tarball
FROM --platform=linux/amd64 ubuntu:22.04 AS builder
COPY AMPS*.tar* /binaries/amps.tar
RUN tar xvf /binaries/amps.tar -C / --transform='s,AMPS[^/]*/,AMPS/,'

# Stage 2: minimal runtime image
FROM --platform=linux/amd64 ubuntu:22.04

LABEL org.opencontainers.image.maintainer="60East Technologies <[email protected]>"
LABEL description="AMPS Server – POC development instance"

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy AMPS binaries
COPY --from=builder /AMPS /AMPS

# Copy all configs into /configs/ — avoids bind-mounting individual files on Windows
RUN mkdir -p /configs
COPY config.xml          /configs/config-core.xml
COPY config-portfolio.xml /configs/config-portfolio.xml
COPY config-cds.xml      /configs/config-cds.xml
COPY config-etf.xml      /configs/config-etf.xml
COPY config-risk.xml     /configs/config-risk.xml

# Copy entrypoint that selects config via AMPS_CONFIG env var
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create SOW data directory
RUN mkdir -p /sow

EXPOSE 8085 9007

ENTRYPOINT ["/entrypoint.sh"]
