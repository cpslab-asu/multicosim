ARG GZ_VERSION=harmonic
FROM ghcr.io/cpslab-asu/multicosim/gazebo:${GZ_VERSION}

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/multicosim
LABEL org.opencontainers.image.description="MultiCoSim gazebo image with PX4 models and worlds"
LABEL org.opencontainers.image.license=BSD-3-Clause

ADD https://github.com/px4/px4-gazebo-models/archive/refs/heads/main.zip ./
RUN unzip main.zip
RUN mv PX4-gazebo-models-main/models resources/
RUN mv PX4-gazebo-models-main/worlds/* resources/worlds/
RUN rm main.zip

ENV GZ_SIM_RESOURCE_PATH=${GZ_ROOT}/resources/worlds:${GZ_ROOT}/resources/models
