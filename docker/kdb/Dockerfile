# ─────────────────────────────────────────────────────────────────────────────
# KDB+ Server – Bond RFQ historical data store
#
# PREREQUISITE: KDB+ personal license (free for dev use)
#   1. Register at https://kx.com/kdb-personal-edition-download/
#   2. Download the license file: kc.lic
#   3. Place it here: docker/kdb/kc.lic
#
# Build & run:
#   docker compose -f docker-compose.kdb.yml up -d
#
# After startup:
#   KDB+ IPC port → localhost:5000  (PyKX / qpython client)
#   Load data    → python scripts/load_kdb_from_parquet.py
# ─────────────────────────────────────────────────────────────────────────────

FROM ubuntu:22.04

LABEL description="KDB+ Bond RFQ historical data server – POC"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget unzip \
    && rm -rf /var/lib/apt/lists/*

# KDB+ personal edition (linux x86_64)
# Download manually from https://kx.com/kdb-personal-edition-download/
# and place in docker/kdb/linuxx86.zip
COPY linuxx86.zip /tmp/linuxx86.zip
RUN unzip /tmp/linuxx86.zip -d /opt/kx && rm /tmp/linuxx86.zip

# License file
COPY kc.lic /opt/kx/kc.lic

# Q initialization script
COPY init.q /opt/kx/q/init.q

ENV QHOME=/opt/kx/q
ENV QLIC=/opt/kx

EXPOSE 5000

HEALTHCHECK --interval=10s --timeout=5s --retries=10 --start-period=15s \
    CMD /opt/kx/q/l64/q -q -e "exit 0" || exit 1

CMD ["/opt/kx/q/l64/q", "/opt/kx/q/init.q", "-p", "5000"]
