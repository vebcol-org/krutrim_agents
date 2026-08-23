# Minimal, locked-down image used for every agent code/shell execution.
# No network access at runtime (the container is started with
# network_disabled=True), so any package the agent might need must already
# be here at build time.
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends coreutils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin sandbox \
    && pip install --no-cache-dir pandas numpy \
    && mkdir -p /workspace \
    && chown sandbox:sandbox /workspace

USER sandbox
WORKDIR /workspace
