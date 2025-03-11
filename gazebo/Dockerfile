FROM ghcr.io/cpslab-asu/multicosim/base:22.04 AS venv

RUN mkdir /app
COPY ./pyproject.toml ./uv.lock /app
RUN --mount=from=ghcr.io/astral-sh/uv:0.5.29,source=/uv,target=/bin/uv \
    uv sync --project /app --python-preference only-system --frozen --no-dev

FROM ghcr.io/cpslab-asu/multicosim/base:22.04 AS gazebo

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/multicosim
LABEL org.opencontainers.image.description="Base gazebo for derived MultiCoSim gazebo images"
LABEL org.opencontainers.image.license=BSD-3-Clause

ARG GZ_VERSION=harmonic
RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y gz-${GZ_VERSION} && \
    rm -rf /var/lib/apt/lists/*

ENV GZ_ROOT=/app
COPY <<EOF /usr/local/bin/gazebo
#!/usr/bin/bash
${GZ_ROOT}/.venv/bin/python3 ${GZ_ROOT}/src/gazebo.py \$@
EOF

COPY --from=venv /app ${GZ_ROOT}
COPY ./src ${GZ_ROOT}/src
COPY ./resources ${GZ_ROOT}/resources
WORKDIR /app

RUN chmod +x-w /usr/local/bin/gazebo
CMD ["/usr/local/bin/gazebo"]
