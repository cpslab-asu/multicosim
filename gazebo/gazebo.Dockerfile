ARG GZ_VERSION=harmonic

FROM cpslabasu/gz-base:${GZ_VERSION}

RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y gz-harmonic

ENV GZ_ROOT=/opt/gazebo

RUN mkdir ${GZ_ROOT}
COPY ./gazebo/requirements.txt ${GZ_ROOT}
COPY ./gazebo/src/ ${GZ_ROOT}/src/
COPY ./gazebo/bin/ ${GZ_ROOT}/bin/

WORKDIR ${GZ_ROOT}
RUN mkdir .venv
RUN pipenv install
RUN ln -s ${GZ_ROOT}/bin/gazebo /usr/local/bin/gazebo
