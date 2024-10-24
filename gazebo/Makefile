GZ_VERSION = harmonic

all: base gazebo

base:
	docker build --file base.Dockerfile --tag ghcr.io/cpslab-asu/gzcm/base:22.04 .

gazebo: base
	docker build --file gazebo.Dockerfile --tag ghcr.io/cpslab-asu/gzcm/gazebo:${GZ_VERSION} .

.PHONY: all base gazebo
