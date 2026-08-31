FROM mcr.microsoft.com/devcontainers/base:bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends cmake file make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
