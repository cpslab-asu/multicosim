ARG GZ_VERSION=harmonic
FROM ghcr.io/cpslab-asu/multicosim/gazebo:${GZ_VERSION}

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/multicosim
LABEL org.opencontainers.image.description="Gazebo image for MultiCoSim rover example"
LABEL org.opencontainers.image.license=BSD-3-Clause

COPY ./resources/models/ /app/resources/models/
