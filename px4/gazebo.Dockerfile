ARG GZ_VERSION=harmonic
FROM ghcr.io/cpslab-asu/gzcm/gazebo:${GZ_VERSION}

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/gzcm
LABEL org.opencontainers.image.description="GZCM gazebo image with PX4 models and worlds"
LABEL org.opencontainers.image.license=BSD-3-Clause

ADD https://github.com/px4/px4-gazebo-models/archive/refs/heads/main.zip ./
RUN unzip main.zip
RUN mv PX4-gazebo-models-main/ resources/
RUN rm main.zip

ENV GZ_SIM_RESOURCE_PATH=${GZ_ROOT}/resources/worlds:${GZ_ROOT}/resources/models
