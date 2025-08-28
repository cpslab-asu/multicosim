#######################
# INITIAL BUILD SECTION
#######################
FROM ubuntu AS build

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y git

# Create ardupilot directory
RUN mkdir /opt/ardupilot 
WORKDIR /opt/ardupilot

# Now grab ArduPilot from GitHub
RUN git clone https://github.com/ArduPilot/ardupilot .
 
# Now start build instructions from http://ardupilot.org/dev/docs/setting-up-sitl-on-linux.html
RUN git submodule update --init --recursive

COPY mods/ardupilot/SIM_JSON.cpp libraries/SITL/
COPY mods/ardupilot/SIM_JSON.h libraries/SITL/


####################
# VENV BUILD SECTION
####################
FROM multicosim AS venv

ENV DEBIAN_FRONTEND=noninteractive
ENV APP_ROOT=/app

# Set app directoies
RUN mkdir ${APP_ROOT}
WORKDIR ${APP_ROOT}

# Copy ardupilot image files
COPY ./pyproject.toml ./uv.lock ./
COPY --from=ghcr.io/astral-sh/uv:0.5.29  /uv /usr/bin/
RUN uv venv --system-site-packages --seed --python-preference only-system
RUN uv sync --frozen --no-dev

# Copy multicosim files
RUN uv pip install --reinstall ${MULTICOSIM_ROOT}


#######################
# FIRWARE BUILD SECTION
#######################
FROM ubuntu AS firmware

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/multicosim
LABEL org.opencontainers.image.description="MultiCoSim image with ArduPilot firmware"
LABEL org.opencontainers.image.license=BSD-3-Clause

ENV DEBIAN_FRONTEND=noninteractive

# Create the user and add to sudo group
ENV USER_NAME=ardupilot

RUN groupadd ${USER_NAME} --gid 1000\
    && useradd -l -m ${USER_NAME} -u 1000 -g 1000 -s /bin/bash

# Install prerequisites
RUN apt-get update && apt-get install --no-install-recommends -y \ 
    sudo \
    lsb-release \
    tzdata \
    default-jre \
    bash-completion

# Create non root user for pip
RUN echo "$USER_NAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${USER_NAME}
RUN chmod 0440 /etc/sudoers.d/${USER_NAME}

# Switch to ardupilot user
USER ${USER_NAME}

# Install python3, python gazebo transport libraries and python library requirements for mavproxy
RUN sudo apt-get update && \
    sudo apt-get install -y \
            python3 \
            python3-gz-math7 \
            python3-gz-msgs10 \
            python3-gz-transport13

# Copy ardupilot directory
COPY --from=build --chown=${USER_NAME}:${USER_NAME} /opt/ardupilot /opt/ardupilot
WORKDIR /opt/ardupilot

# Install all prerequisites now
RUN SKIP_AP_GRAPHIC_ENV=1 SKIP_AP_COV_ENV=1 SKIP_AP_GIT_CHECK=1 \
    DO_AP_STM_ENV=0 \
    AP_DOCKER_BUILD=1 \
    USER=${USER_NAME} \
    Tools/environment_install/install-prereqs-ubuntu.sh -y

# Continue build instructions from https://github.com/ArduPilot/ardupilot/blob/master/BUILD.md
RUN ./waf configure --board sitl
RUN ./waf copter
# RUN ./waf rover 
# RUN ./waf plane
# RUN ./waf sub

# install mavproxy
RUN sudo pip install mavproxy

# TCP 5760 is what the sim exposes by default
EXPOSE 5760/tcp

# Set logs directory
ENV BUILDLOGS=/tmp/buildlogs

# Cleanup
RUN sudo apt-get clean \
    && sudo rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set max cache size    
ENV CCACHE_MAXSIZE=1G

#######################
# FINAL BUILD SECTION
#######################
FROM firmware AS final

EXPOSE 9002/udp
EXPOSE 14551/tcp

# Copy /app director with virtual environment
ENV APP_ROOT=/app
COPY --from=venv --chown=${USER_NAME}:${USER_NAME} /app ${APP_ROOT}
WORKDIR ${APP_ROOT}
COPY --chown=${USER_NAME}:${USER_NAME} ./src/ ./src/

# Create run script 
COPY <<'EOF' /usr/local/bin/firmware
#!/usr/bin/bash
/app/.venv/bin/python3 /app/src/firmware.py $@
EOF
RUN sudo chmod +x-w /usr/local/bin/firmware

WORKDIR ${APP_ROOT}
CMD ["/usr/local/bin/firmware"]
