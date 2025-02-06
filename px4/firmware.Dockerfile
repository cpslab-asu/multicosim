FROM ghcr.io/cpslab-asu/gzcm/base:22.04 AS build

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y git

ENV PX4_ROOT=/opt/px4-autopilot
RUN git clone https://github.com/px4/px4-autopilot ${PX4_ROOT}
WORKDIR ${PX4_ROOT}

ARG PX4_VERSION=1.15.0
RUN git checkout v${PX4_VERSION}

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
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
        python3-dev \
        python3-pip \
        python3-venv \
        python3-gz-transport13 \
        python3-gz-msgs10 \
        unzip \
        zip \
        bc \
        libgz-transport13-dev \
        libgz-msgs10-dev \
        ;


# Install build dependencies and build PX4 firmware
RUN python3 -m venv .venv
RUN .venv/bin/pip install -r ./Tools/setup/requirements.txt
RUN .venv/bin/pip install empy==3.3.4
RUN . .venv/bin/activate && make px4_sitl

FROM ubuntu:22.04 AS venv

RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y python3 python3-pip
RUN pip3 install pipenv

RUN mkdir /app
WORKDIR /app

# Copy px4 program source files
COPY ./Pipfile ./Pipfile.lock mavsdk.patch ./
RUN PIPENV_VENV_IN_PROJECT=1 pipenv sync --site-packages
RUN patch .venv/lib/python3.10/site-packages/mavsdk/system.py mavsdk.patch

ENV GZCM_ROOT=/opt/gzcm
COPY --from=gzcm ./pyproject.toml ./README.md ${GZCM_ROOT}/
COPY --from=gzcm ./src/ ${GZCM_ROOT}/src/
RUN .venv/bin/pip3 install --ignore-installed ${GZCM_ROOT}

FROM ghcr.io/cpslab-asu/gzcm/base:22.04 AS firmware

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/gzcm
LABEL org.opencontainers.image.description="GZCM image with PX4 firmware"
LABEL org.opencontainers.image.license=BSD-3-Clause

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        python3 \
        python3-gz-transport13 \
        python3-gz-msgs10 \
        libgz-transport13-dev \
        libgz-msgs10-dev \
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
