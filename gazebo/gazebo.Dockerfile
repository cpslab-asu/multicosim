ARG GZ_VERSION=harmonic

FROM cpslabasu/gz-base:${GZ_VERSION}

RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y gz-harmonic

ENV GZ_ROOT=/opt/gazebo

RUN mkdir ${GZ_ROOT}
WORKDIR ${GZ_ROOT}
COPY ./gazebo/Pipfile ./gazebo/Pipfile.lock ./

RUN mkdir .venv
RUN pipenv sync

COPY ./gazebo/src/ ./src/
COPY ./gazebo/bin/ ./bin/
RUN ln -s ${GZ_ROOT}/bin/gazebo /usr/local/bin/gazebo
