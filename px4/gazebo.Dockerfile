FROM gazebo

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/multicosim
LABEL org.opencontainers.image.description="MultiCoSim gazebo image with PX4 models and worlds"
LABEL org.opencontainers.image.license=BSD-3-Clause

ADD https://github.com/px4/px4-gazebo-models.git#23170a91255d99aea8960d1101541afce0f209d9 px4-gazebo-models/
RUN mv px4-gazebo-models/models resources/models
RUN mv px4-gazebo-models/worlds/* resources/worlds/
RUN rm -r px4-gazebo-models

ENV GZ_SIM_RESOURCE_PATH=${GZ_ROOT}/resources/worlds:${GZ_ROOT}/resources/models
