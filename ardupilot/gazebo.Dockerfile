FROM ghcr.io/cpslab-asu/multicosim/gazebo:harmonic AS base
     
RUN apt-get update \
    &&  DEBIAN_FRONTEND=noninteractive apt-get install -y \
        libgz-sim8-dev \
        rapidjson-dev \
        libopencv-dev \
        libgstreamer1.0-dev \
        libgstreamer-plugins-base1.0-dev \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-libav \
        gstreamer1.0-gl \
        libdebuginfod-dev \
    &&  rm -rf /var/lib/lists/* 

FROM base AS build

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        git \
        build-essential \
        cmake \
        ninja-build \
        ;

RUN git clone https://github.com/ardupilot/ardupilot_gazebo /src/ardupilot_gazebo
COPY mods/gazebo/ArduPilotPlugin.cc /src/ardupilot_gazebo/src/
RUN cmake -S /src/ardupilot_gazebo -B /src/ardupilot_gazebo/build -D CMAKE_BUILD_TYPE=RelWithDebInfo -G Ninja
RUN cmake --build /src/ardupilot_gazebo/build

FROM base AS gazebo

COPY --from=build /src/ardupilot_gazebo/worlds ./resources/worlds/
COPY --from=build /src/ardupilot_gazebo/models ./resources/models/
COPY --from=build /src/ardupilot_gazebo/build/*.so ./plugins/

ENV GZ_SIM_SYSTEM_PLUGIN_PATH=${GZ_ROOT}/plugins
ENV GZ_SIM_RESOURCE_PATH=${GZ_ROOT}/resources/models:${GZ_ROOT}/resources/worlds