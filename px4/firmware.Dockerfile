ARG GZCM_VERSION=0.1.0
FROM ghcr.io/cpslab-asu/gzcm/gzcm:$GZCM_VERSION

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/gzcm
LABEL org.opencontainers.image.description="GZCM image with PX4 firmware"
LABEL org.opencontainers.image.license=BSD-3-Clause

ENV PX4_ROOT=/opt/px4-autopilot

RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y git

RUN git clone https://github.com/px4/px4-autopilot ${PX4_ROOT}

WORKDIR $PX4_ROOT

ARG PX4_VERSION=1.15.0
RUN git checkout v${PX4_VERSION}

RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y \
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
RUN python3 -m pip install -r ./Tools/setup/requirements.txt
RUN python3 -m pip install empy==3.3.4
RUN make px4_sitl

ENV APP_ROOT=/app
WORKDIR $APP_ROOT

# Copy px4 program source files
COPY ./Pipfile ./Pipfile.lock mavsdk.patch ./

RUN mkdir .venv
RUN pipenv sync --site-packages
RUN .venv/bin/pip install /opt/gzcm
RUN patch .venv/lib/python3.10/site-packages/mavsdk/system.py mavsdk.patch

COPY ./src/ ./src/
COPY ./bin/ ./bin/
RUN ln -s ${APP_ROOT}/bin/firmware /usr/local/bin/firmware
