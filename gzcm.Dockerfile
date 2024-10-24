FROM ghcr.io/cpslab-asu/gzcm/base:22.04

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/gzcm
LABEL org.opencontainers.image.description="Image with GZCM package installed for derived GZCM firmware images"
LABEL org.opencontainers.image.license=BSD-3-Clause

RUN mkdir /opt/gzcm
COPY ./pyproject.toml ./README.md /opt/gzcm
COPY ./src /opt/gzcm/src
