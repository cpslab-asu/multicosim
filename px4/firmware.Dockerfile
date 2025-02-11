FROM ghcr.io/cpslab-asu/gzcm/base:22.04 AS build

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        git \
        build-essential \
        cmake \
        file \
        g++ \
        gcc \
        pkg-config \
        libxml2-dev \
        libxml2-utils \
        make \
        ninja-build \
        python3 \
        python3-venv \
        python3-gz-transport13 \
        python3-gz-msgs10 \
        unzip \
        zip \
        bc \
        libgz-transport13-dev \
        libgz-msgs10-dev \
        ;

ARG PX4_VERSION=1.15.0
ENV PX4_ROOT=/opt/px4-autopilot
RUN git clone --depth 1 --branch v${PX4_VERSION} https://github.com/px4/px4-autopilot ${PX4_ROOT}
WORKDIR ${PX4_ROOT}


# Install build dependencies and build PX4 firmware
RUN python3 -m venv .venv
RUN .venv/bin/pip install -r ./Tools/setup/requirements.txt
RUN . .venv/bin/activate && make px4_sitl

FROM ghcr.io/cpslab-asu/gzcm/base:22.04 AS venv

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y patch

RUN mkdir /app
WORKDIR /app

# Copy px4 program source files
COPY ./pyproject.toml ./uv.lock mavsdk.patch ./

COPY --from=ghcr.io/astral-sh/uv:0.5.29 /uv /usr/bin/
RUN uv venv --system-site-packages --python-preference only-system
RUN uv sync --frozen --no-dev
RUN patch .venv/lib/python3.10/site-packages/mavsdk/system.py mavsdk.patch

ENV GZCM_ROOT=/opt/gzcm
RUN mkdir ${GZCM_ROOT}
COPY --from=gzcm ./pyproject.toml ./README.md ${GZCM_ROOT}/
COPY --from=gzcm ./src/ ${GZCM_ROOT}/src/
RUN uv pip install --reinstall ${GZCM_ROOT}

FROM ghcr.io/cpslab-asu/gzcm/base:22.04 AS firmware

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/gzcm
LABEL org.opencontainers.image.description="GZCM image with PX4 firmware"
LABEL org.opencontainers.image.license=BSD-3-Clause

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        python3-gz-transport13 \
        python3-gz-msgs10 \
        && \
    rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/px4-autopilot /opt/px4-autopilot

ENV APP_ROOT=/app
COPY <<EOF /usr/local/bin/firmware
#!/usr/bin/bash
${APP_ROOT}/.venv/bin/python3 ${APP_ROOT}/src/firmware.py \$@
EOF
RUN chmod +x-w /usr/local/bin/firmware

COPY --from=venv /app ${APP_ROOT}
WORKDIR ${APP_ROOT}
COPY ./src/ ./src/

CMD ["/usr/local/bin/firmware"]
