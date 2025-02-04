FROM ubuntu:22.04 AS fetcher

# Install dependencies for adding OSRF Apt repository
RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        curl \
        lsb-release \
        gnupg \
        ;

# Add OSRF Apt repository to Apt sources list
RUN curl https://packages.osrfoundation.org/gazebo.gpg --output /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
RUN echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" > /etc/apt/sources.list.d/gazebo-stable.list

FROM ubuntu:22.04 AS base

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/gzcm
LABEL org.opencontainers.image.description="Base image for other GZCM images"
LABEL org.opencontainers.image.license=BSD-3-Clause

COPY --from=fetcher /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg /usr/share/keyrings/
COPY --from=fetcher /etc/apt/sources.list.d/gazebo-stable.list /etc/apt/sources.list.d/
