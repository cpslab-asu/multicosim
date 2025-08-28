ARG UBUNTU_VERSION=22.04
FROM ghcr.io/cpslab-asu/multicosim/base:ubuntu${UBUNTU_VERSION}

ENV MULTICOSIM_ROOT=/opt/multicosim

COPY ./pyproject.toml ./README.md ${MULTICOSIM_ROOT}/
COPY ./src/ ${MULTICOSIM_ROOT}/src/

RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
    uv pip install --system ${MULTICOSIM_ROOT}
