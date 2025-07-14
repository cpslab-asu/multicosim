GZ_VERSION ?= harmonic
REGISTRY ?= ghcr.io/cpslab-asu/multicosim
PLATFORMS ?= linux/amd64,linux/arm64
MULTICOSIM_VERSION ?= $(shell cd .. && hatch version)
SOURCES := $(wildcard src/*.py) $(wildcard ../src/multicosim/*.py)

all: images

images: gazebo firmware

gazebo: .cache/gazebo

.cache/gazebo: gazebo.Dockerfile
	docker buildx build \
		--file gazebo.Dockerfile \
		--platform $(PLATFORMS) \
		--tag $(REGISTRY)/ardupilot/gazebo:$(GZ_VERSION) \
		.
	@mkdir -p $(shell dirname $@)
	@touch $@

firmware: .cache/firmware

.cache/firmware: firmware.Dockerfile pyproject.toml uv.lock $(SOURCES)
	docker buildx build \
		--file firmware.Dockerfile \
		--platform $(PLATFORMS) \
		--build-context multicosim=.. \
		--tag $(REGISTRY)/ardupilot/firmware:$(MULTICOSIM_VERSION) \
		--load \
		.
	@mkdir -p $(shell dirname $@)
	@touch $@


.PHONY: images gazebo firmware
