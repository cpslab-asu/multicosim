FROM ghcr.io/cpslab-asu/gzcm/base:22.04 AS venv

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv

RUN python3 -m venv /opt/pipenv
RUN /opt/pipenv/bin/pip3 install pipenv

RUN mkdir /app
WORKDIR /app

COPY ./Pipfile ./Pipfile.lock ./
RUN python3 -m venv .venv
RUN /opt/pipenv/bin/pipenv sync

FROM ghcr.io/cpslab-asu/gzcm/base:22.04 AS gazebo

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/gzcm
LABEL org.opencontainers.image.description="Base gazebo for derived GZCM gazebo images"
LABEL org.opencontainers.image.license=BSD-3-Clause

ARG GZ_VERSION=harmonic
RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y gz-${GZ_VERSION} python3 && \
    rm -rf /var/lib/apt/lists/*

ENV GZ_ROOT=/app
COPY --from=venv /app ${GZ_ROOT}
COPY ./src ${GZ_ROOT}/src

COPY <<EOF /usr/local/bin/gazebo
#!/usr/bin/bash
${GZ_ROOT}/.venv/bin/python3 ${GZ_ROOT}/src/gazebo.py \$@
EOF

RUN chmod +x-w /usr/local/bin/gazebo
CMD ["/usr/local/bin/gazebo"]
