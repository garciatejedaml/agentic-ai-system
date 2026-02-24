# ─────────────────────────────────────────────────────────────────────────────
# AMPS Server – Linux x86_64 (runs on M1 Mac via Docker --platform linux/amd64)
#
# PREREQUISITE: Place the AMPS Linux tarball in this directory as AMPS.tar
#   1. Register at https://crankuptheamps.com/evaluate
#   2. Download the Linux x86_64 distribution
#   3. Copy it here: docker/amps/AMPS.tar
#
# Build & run:
#   docker compose -f docker-compose.amps.yml up -d
# ─────────────────────────────────────────────────────────────────────────────

# Stage 1: extract AMPS from tarball
# NOTE: Use COPY (not ADD) to prevent Docker from auto-extracting the tarball
FROM --platform=linux/amd64 ubuntu:22.04 AS builder
COPY AMPS.tar /binaries/AMPS.tar
RUN tar xvf /binaries/AMPS.tar -C / --transform='s,AMPS[^/]*/,AMPS/,'

# Stage 2: minimal runtime image
FROM --platform=linux/amd64 ubuntu:22.04

LABEL org.opencontainers.image.maintainer="60East Technologies <[email protected]>"
LABEL description="AMPS Server – POC development instance"

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy AMPS binaries and config
COPY --from=builder /AMPS /AMPS
COPY config.xml /config.xml

# Create SOW data directory
RUN mkdir -p /sow

EXPOSE 8085 9007

CMD ["/AMPS/bin/ampServer", "/config.xml"]
