FROM ghcr.io/cpslab-asu/gzcm/base:22.04

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/gzcm
LABEL org.opencontainers.image.description="Base gazebo for derived GZCM gazebo images"
LABEL org.opencontainers.image.license=BSD-3-Clause

ARG GZ_VERSION=harmonic
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y gz-${GZ_VERSION}

ENV GZ_ROOT=/opt/gazebo

RUN mkdir ${GZ_ROOT}
WORKDIR ${GZ_ROOT}
COPY ./Pipfile ./Pipfile.lock ./

RUN mkdir .venv
RUN pipenv sync

COPY ./src/ ./src/
COPY ./bin/ ./bin/
RUN ln -s ${GZ_ROOT}/bin/gazebo /usr/local/bin/gazebo
