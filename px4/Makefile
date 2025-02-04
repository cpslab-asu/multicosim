REGISTRY ?= ghcr.io/cpslab-asu/gzcm
PLATFORMS ?= linux/amd64,linux/arm64
GZ_VERSION ?= harmonic
GZCM_VERSION := $(shell hatch version)
PX4_VERSION ?= 1.15.0

images: gazebo firmware

gazebo: gazebo.Dockerfile
	docker build \
		--file gazebo.Dockerfile \
		--platform $(PLATFORMS) \
		--build-arg GZ_VERSION=$(GZ_VERSION) \
		--tag $(REGISTRY)/px4/gazebo:$(GZ_VERSION) \
		.

firmware: firmware.Dockerfile
	docker build \
		--file firmware.Dockerfile \
		--platform $(PLATFORMS) \
		--build-arg PX4_VERSION=$(PX4_VERSION) \
		--build-context gzcm=.. \
		--tag $(REGISTRY)/px4/firmware:$(GZCM_VERSION) \
		.

.PHONY: images gazebo firmware
