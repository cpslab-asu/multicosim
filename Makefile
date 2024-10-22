PX4_VERSION ?= 1.15.0
GZ_VERSION ?= harmonic

all:

base:
	docker build --file gazebo/base.Dockerfile --tag cpslabasu/gz-base:${GZ_VERSION} .

gazebo: base
	docker build --file gazebo/gazebo.Dockerfile --tag cpslabasu/gazebo:${GZ_VERSION} --build-arg GZ_VERSION=${GZ_VERSION} .

px4-firmware: base
	docker build --file px4/firmware.Dockerfile --tag cpslabasu/px4-firmware:${PX4_VERSION} --build-arg PX4_VERSION=${PX4_VERSION} .

px4-gazebo: gazebo
	docker build --file px4/gazebo.Dockerfile --tag cpslabasu/px4-gazebo:${GZ_VERSION} --build-arg GZ_VERSION=${GZ_VERSION} .

.PHONY: base gazebo px4-firmware px4-gazebo
