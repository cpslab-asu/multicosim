ARG GZ_VERSION=harmonic

FROM cpslabasu/gz-base:${GZ_VERSION}

RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y \
    gz-harmonic \
    python3 \
    python3-pip \
    python3-venv \
    ;

ENV GZ_ROOT=/opt/gazebo
RUN mkdir ${GZ_ROOT}
WORKDIR ${GZ_ROOT}

COPY ./gazebo/requirements.txt ./
COPY ./gazebo/src/ ./src/
COPY ./gazebo/bin/ ./bin/

RUN python3 -m venv .venv

RUN .venv/bin/python3 -m pip install -r requirements.txt

ENV PATH=${GZ_ROOT}/bin:${PATH}
