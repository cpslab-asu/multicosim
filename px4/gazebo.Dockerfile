ARG GZ_VERSION=harmonic

FROM cpslabasu/gazebo:${GZ_VERSION}

ADD https://github.com/px4/px4-gazebo-models/archive/refs/heads/main.zip ./
RUN unzip main.zip
RUN mv PX4-gazebo-models-main/ resources/
RUN rm main.zip

ENV GZ_SIM_RESOURCE_PATH=${GZ_ROOT}/resources/worlds:${GZ_ROOT}/resources/models
