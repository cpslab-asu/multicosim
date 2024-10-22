FROM cpslabasu/gazebo-base:harmonic

ARG PX4_VERSION=1.15.0

ENV PX4_ROOT=/opt/px4-autopilot

RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y git

RUN git clone https://github.com/px4/px4-autopilot $PX4_ROOT

WORKDIR $PX4_ROOT

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

# Install Pipenv
RUN python3 -m venv /opt/pipenv
RUN /opt/pipenv/bin/pip install pipenv
RUN ln -s /opt/pipenv/bin/pipenv /usr/local/bin/pipenv

# Copy GZCM library source files
COPY ./pyproject.toml ./README.md /opt/gzcm/
COPY ./src/ /opt/gzcm/src/

ENV APP_ROOT=/app

# Copy px4 program source files
COPY ./px4/Pipfile ./px4/Pipfile.lock $APP_ROOT/
WORKDIR $APP_ROOT

RUN mkdir .venv
RUN pipenv sync --site-packages
RUN .venv/bin/pip install /opt/gzcm

COPY ./px4/src/ $APP_ROOT/src/
COPY ./px4/bin/ $APP_ROOT/bin/
RUN ln -s /app/bin/firmware /usr/local/bin/firmware
