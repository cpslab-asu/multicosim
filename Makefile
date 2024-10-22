PX4_VERSION ?= 1.15.0
GZ_VERSION ?= harmonic

all:

.cache:
	mkdir -p .cache

.cache/base: .cache gazebo/base.Dockerfile
	docker build --file gazebo/base.Dockerfile --tag cpslabasu/gz-base:${GZ_VERSION} .
	touch $@

base: .cache/base

.cache/gazebo: base gazebo/gazebo.Dockerfile
	docker build --file gazebo/gazebo.Dockerfile --tag cpslabasu/gazebo:${GZ_VERSION} --build-arg GZ_VERSION=${GZ_VERSION} .
	touch $@

gazebo: .cache/gazebo

.cache/px4-firmware: base px4/firmware.Dockerfile
	docker build --file px4/firmware.Dockerfile --tag cpslabasu/px4-firmware:${PX4_VERSION} --build-arg PX4_VERSION=${PX4_VERSION} .
	touch $@

px4-firmware: .cache/px4-firmware

.cache/px4-gazebo: gazebo px4/gazebo.Dockerfile
	docker build --file px4/gazebo.Dockerfile --tag cpslabasu/px4-gazebo:${GZ_VERSION} --build-arg GZ_VERSION=${GZ_VERSION} .
	touch $@

px4-gazebo: .cache/px4-gazebo

.PHONY: base gazebo px4-firmware px4-gazebo
