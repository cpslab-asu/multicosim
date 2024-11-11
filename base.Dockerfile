FROM ubuntu:22.04

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/gzcm
LABEL org.opencontainers.image.description="Base image for other GZCM images"
LABEL org.opencontainers.image.license=BSD-3-Clause

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

# Install python3
RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
        ;

# Create isolated environment and install pipenv
RUN python3 -m venv /opt/pipenv
RUN /opt/pipenv/bin/pip install pipenv
RUN ln -s /opt/pipenv/bin/pipenv /usr/local/bin/pipenv
