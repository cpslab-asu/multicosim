PX4_VERSION ?= 1.15.0
GZ_VERSION ?= harmonic
GZCM_VERSION = $(shell hatch version)

all: base gazebo gzcm px4-firmware px4-gazebo

base:
	make -C gazebo base

gazebo:
	make -C gazebo gazebo

gzcm: base
	docker build --file gzcm.Dockerfile --tag ghcr.io/cpslab-asu/gzcm/gzcm:${GZCM_VERSION} .

px4-firmware:
	make -C px4 firmware

px4-gazebo:
	make -C px4 gazebo

.PHONY: all base gazebo gzcm px4-firmware px4-gazebo
