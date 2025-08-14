FROM ghcr.io/cpslab-asu/multicosim/rocky/build:9.6 AS gts_build

RUN dnf install -y netpbm-devel gtk2-devel

WORKDIR workspace

RUN git clone https://github.com/lsaavedr/gts.git
WORKDIR gts
RUN ./autogen.sh && \
    make -j4
RUN make install

WORKDIR /workspace
RUN rm -fr /workspace/gts
RUN dnf group remove -y "Development Tools" && \
	dnf remove -y netpbm-devel gtk2-devel

FROM ghcr.io/cpslab-asu/multicosim/rocky/build:9.6 AS dart_build

WORKDIR workspace

RUN git clone https://github.com/coin-or/Ipopt.git
RUN dnf install -y lapack-devel
WORKDIR Ipopt
RUN ./configure && \
    make -j4
RUN make install

WORKDIR /workspace
RUN rm -fr /workspace/Ipopt

RUN git clone https://github.com/esa/pagmo2.git
RUN dnf install -y tbb-devel boost-devel
WORKDIR pagmo_build
RUN cmake ../pagmo2 && \
    make -j4
RUN make install

WORKDIR /workspace
RUN rm -fr /workspace/pagmo_build

RUN git clone https://bitbucket.org/odedevs/ode.git
RUN dnf install -y glew-devel
WORKDIR ode_build
RUN cmake ../ode && \
    make -j4
RUN make install

WORKDIR /workspace
RUN rm -fr /workspace/ode_build

RUN git clone https://github.com/dartsim/dart.git && \
	cd dart
ENV PKG_CONFIG_PATH=/usr/local/lib64/pkgconfig:/usr/local/lib/pkgconfig
#RUN dnf --nogpg install -y https://mirror.ghettoforge.net/distributions/gf/gf-release-latest.gf.el9.noarch.rpm

RUN dnf install -y \
    fcl-devel \
	fmt-devel \
	bullet-devel \
#	NLopt-devel \
	OpenSceneGraph-devel \
	assimp-devel \
	tinyxml2-devel \
	urdfdom-devel \
	freeglut-devel && \
	dnf clean all

WORKDIR dart_build
RUN cmake ../dart && \
    make -j4
RUN make install

WORKDIR /workspace
RUN rm -fr /workspace/dart_build

RUN dnf group remove -y "Development Tools" && \
	dnf remove -y \
	fcl-devel \
	fmt-devel \
	bullet-devel \
#	NLopt-devel \
	OpenSceneGraph-devel \
	assimp-devel \
	tinyxml2-devel \
	urdfdom-devel \
	freeglut-devel \
	glew-devel \
	tbb-devel \
	boost-devel \
	lapack-devel

FROM ghcr.io/cpslab-asu/multicosim/rocky/build:9.6 AS ogre_build

WORKDIR workspace

RUN dnf install -y \
    freetype-devel \
    freeimage-devel \
	zziplib-devel \
    libXrandr-devel \
	libXaw-devel \
    freeglut-devel \
	python3-clang \
    SDL2-devel \
	rapidjson-devel \
	ninja-build && \
	dnf clean all

RUN git clone https://github.com/OGRECave/ogre-next.git && \
	cd ogre-next && \
	git checkout v2-3
WORKDIR ogre_build

RUN cmake -DOGRE_GLSUPPORT_USE_EGL_HEADLESS=1 ../ogre-next && \
	make -j4 && \
	make install && \
	cd /workspace && \
	rm -fr /workspace/ogre_build && \
	dnf group remove -y "Development Tools" && \
	dnf remove -y \
    freetype-devel \
    freeimage-devel \
	zziplib-devel \
    libXrandr-devel \
	libXaw-devel \
    freeglut-devel \
	rapidjson-devel \
	doxygen \
	python3-clang \
    SDL2-devel \
	ninja-build

FROM ghcr.io/cpslab-asu/multicosim/rocky/build:9.6 AS gazebo_build

ARG GZ_VERSION=harmonic

RUN dnf install -y \
    python3.12-devel \
    python3-protobuf \
    python3-psutil \
    python3-pybind11 \
    python3-pytest \
    redhat-lsb \
    gnupg2 && \
	dnf clean all

RUN python3 -m venv vcs_colcon_installation && \
    . vcs_colcon_installation/bin/activate && \
    pip3 install vcstool colcon-common-extensions

WORKDIR workspace/src

RUN curl -O https://raw.githubusercontent.com/gazebo-tooling/gazebodistro/master/collection-${GZ_VERSION}.yaml
RUN /vcs_colcon_installation/bin/vcs import < collection-${GZ_VERSION}.yaml   

COPY --from=gts_build /usr/local/lib/. /usr/local/lib
COPY --from=gts_build /usr/local/include/. /usr/local/include

COPY --from=dart_build /usr/local/lib/. /usr/local/lib
COPY --from=dart_build /usr/local/lib64/. /usr/local/lib64
COPY --from=dart_build /usr/local/include/. /usr/local/include
COPY --from=dart_build /usr/local/share/dart /usr/local/share/dart

COPY --from=ogre_build /usr/local/lib/. /usr/local/lib
COPY --from=ogre_build /usr/local/include/. /usr/local/include
COPY --from=ogre_build /usr/local/share/OGRE /usr/local/share/OGRE

RUN dnf install -y \
    binutils-devel \
	freeglut-devel \
	assimp-devel \
	libavcodec-free-devel \
	libavdevice-free-devel \
	libavformat-free-devel \
	libavutil-free-devel \
	google-benchmark-devel \
	eigen3-devel \
	freeimage-devel \
	freetype-devel \
	gdal-devel \
	gflags-devel \
	glew-devel \
	glib2-devel \
	jsoncpp-devel \
	protobuf-devel \
	protobuf-c-devel \
	sqlite-devel \
	libswscale-free-devel \
	tinyxml2-devel \
	urdfdom-devel \
	vulkan-loader-devel \
	libwebsockets-devel \
	libxml2-devel \
	cppzmq-devel \
	zeromq-devel \
	glx-utils \
	qt5-qtbase-devel \
	qt5-qtdeclarative-devel \
	qt5-qtquickcontrols2-devel \
	qt5-qtcharts-devel \
	qt5-qtlocation-devel \
	qt5-qtquickcontrols \
	libXi-devel \
	libXmu-devel \
	libyaml-devel \
	libzip-devel \
	ruby \
	ruby-devel \
	swig \
	libuuid-devel \
	xorg-x11-utils \
	xorg-x11-server-Xvfb \
	mesa-libGL-devel \
	libcurl-devel \
	bullet-devel \
	libccd-devel \
	octomap-devel \
	fcl-devel \
	fmt-devel \
	OpenSceneGraph-devel \
	gem && \
	dnf clean all

RUN gem install rubocop

WORKDIR /workspace
ENV PKG_CONFIG_PATH=/usr/local/lib64/pkgconfig:/usr/local/lib/pkgconfig
RUN sed -i -e 's/GREATER_EQUAL "3" AND NOT APPLE/GREATER "3" AND NOT APPLE/g' src/gz-cmake/cmake/FindGzOGRE2.cmake
RUN /vcs_colcon_installation/bin/colcon graph && \
	/vcs_colcon_installation/bin/colcon build --cmake-args ' -DBUILD_TESTING=OFF' --merge-install && \
	dnf group remove -q -y "Development Tools" && \
	dnf remove -q -y \
    binutils-devel \
	freeglut-devel \
	assimp-devel \
	libavcodec-free-devel \
	libavdevice-free-devel \
	libavformat-free-devel \
	libavutil-free-devel \
	google-benchmark-devel \
	eigen3-devel \
	freeimage-devel \
	freetype-devel \
	gdal-devel \
	gflags-devel \
	glew-devel \
	glib2-devel \
	jsoncpp-devel \
	protobuf-devel \
	protobuf-c-devel \
	sqlite-devel \
	libswscale-free-devel \
	tinyxml2-devel \
	urdfdom-devel \
	vulkan-loader-devel \
	libwebsockets-devel \
	libxml2-devel \
	cppzmq-devel \
	zeromq-devel \
	glx-utils \
	qt5-qtbase-devel \
	qt5-qtdeclarative-devel \
	qt5-qtquickcontrols2-devel \
	qt5-qtcharts-devel \
	qt5-qtlocation-devel \
	qt5-qtquickcontrols \
	libXi-devel \
	libXmu-devel \
	libyaml-devel \
	libzip-devel \
	ruby \
	ruby-devel \
	swig \
	libuuid-devel \
	xorg-x11-utils \
	xorg-x11-server-Xvfb \
	mesa-libGL-devel \
	libcurl-devel \
	bullet-devel \
	libccd-devel \
	octomap-devel \
	fcl-devel \
	fmt-devel \
	OpenSceneGraph-devel \
	gem && \
	mkdir install/worlds && \
	cp -r src/gz-sim/examples/worlds/* install/worlds && \
	rm -fr build src

FROM ghcr.io/cpslab-asu/multicosim/rocky/base:9.6 AS venv

WORKDIR /app

COPY ./pyproject.toml ./uv.lock ./
RUN --mount=from=ghcr.io/astral-sh/uv:0.5.29,source=/uv,target=/bin/uv \
    uv venv --system-site-packages --relocatable && \
    uv sync --python-preference only-system --frozen --no-dev

FROM ghcr.io/cpslab-asu/multicosim/rocky/base:9.6 AS gazebo

# LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/multicosim
# LABEL org.opencontainers.image.description="Base gazebo for derived MultiCoSim gazebo images"
# LABEL org.opencontainers.image.license=BSD-3-Clause

RUN dnf config-manager --enable devel crb && \
	dnf install -y \
    epel-release \
    epel-next-release

RUN dnf install -y \
    python3-protobuf \
    python3-psutil \
    python3-pybind11 \
    python3-pytest \
	binutils \
	freeglut \
	assimp \
	libavcodec-free-devel \
	libavdevice-free-devel \
	libavformat-free-devel \
	libavutil-free-devel \
	eigen3-devel \
	freeimage-devel \
	gdal-devel \
	glew-devel \
	jsoncpp-devel \
	protobuf-devel \
	protobuf-c-devel \
	sqlite-devel \
	libswscale-free-devel \
	tinyxml2-devel \
	vulkan-loader-devel \
	libwebsockets-devel \
	libxml2-devel \
	cppzmq-devel \
	zeromq-devel \
	glx-utils \
	qt5-qtbase-devel \
	qt5-qtdeclarative-devel \
	qt5-qtquickcontrols2-devel \
	qt5-qtcharts-devel \
	qt5-qtlocation-devel \
	qt5-qtquickcontrols \
	libXi \
	libXmu \
	libyaml-devel \
	libzip-devel \
	libXaw \
	zziplib \
	ruby \
	gem \
	libuuid-devel \
	xorg-x11-utils \
	xorg-x11-server-Xvfb \
	mesa-libGL \
	libcurl-devel \
	gtk2 \
	lapack-devel \
	boost-devel \
	fcl \
	bullet-devel \
	urdfdom-devel \
	assimp-devel && \
	dnf clean all

COPY --from=gts_build /usr/local/lib/. /usr/local/lib
COPY --from=dart_build /usr/local/lib/. /usr/local/lib
COPY --from=dart_build /usr/local/lib64/. /usr/local/lib64
COPY --from=ogre_build /usr/local/lib/. /usr/local/lib

RUN mkdir -p /workspace/install/
COPY --from=gazebo_build /workspace/install/. /workspace/install/
COPY --from=gazebo_build /workspace/install/*.* /workspace/install/
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib:/usr/local/lib64


ENV GZ_ROOT=/app
COPY <<'EOF' /usr/local/bin/gazebo
#!/usr/bin/bash
export PYTHONPATH=/workspace/install/lib64/python
. /workspace/install/setup.bash
/app/.venv/bin/python3 /app/src/gazebo.py $@
EOF

COPY --from=venv /app ${GZ_ROOT}
COPY ./src ${GZ_ROOT}/src
COPY ./resources ${GZ_ROOT}/resources
WORKDIR /app

RUN chmod +x-w /usr/local/bin/gazebo
CMD ["/usr/local/bin/gazebo"]