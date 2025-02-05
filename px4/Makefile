REGISTRY ?= ghcr.io/cpslab-asu/gzcm
PLATFORMS ?= linux/amd64,linux/arm64
GZ_VERSION ?= harmonic
PX4_VERSION ?= 1.15.0
GZCM_VERSION := $(shell hatch version)
SOURCES := $(wildcard src/*.py)

images: gazebo firmware

gazebo: .cache/gazebo

.cache/gazebo: gazebo.Dockerfile
	docker buildx build \
		--file gazebo.Dockerfile \
		--platform $(PLATFORMS) \
		--build-arg GZ_VERSION=$(GZ_VERSION) \
		--tag $(REGISTRY)/px4/gazebo:$(GZ_VERSION) \
		--load \
		.
	@mkdir -p .cache
	@touch $@

firmware: .cache/firmware

.cache/firmware: firmware.Dockerfile $(SOURCES)
	docker buildx build \
		--file firmware.Dockerfile \
		--platform $(PLATFORMS) \
		--build-arg PX4_VERSION=$(PX4_VERSION) \
		--build-context gzcm=.. \
		--tag $(REGISTRY)/px4/firmware:$(GZCM_VERSION) \
		--load \
		.
	@mkdir -p .cache
	@touch $@

.PHONY: images gazebo firmware
