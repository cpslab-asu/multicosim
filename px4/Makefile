REGISTRY ?= ghcr.io/cpslab-asu/multicosim
PLATFORMS ?= linux/amd64,linux/arm64
GZ_VERSION ?= harmonic
PX4_VERSION ?= 1.15.0
MULTICOSIM_VERSION ?= $(shell cd .. && hatch version)
SOURCES := $(wildcard src/*.py) $(wildcard ../src/multicosim/*.py)

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

.cache/firmware: firmware.Dockerfile pyproject.toml uv.lock $(SOURCES)
	docker buildx build \
		--file firmware.Dockerfile \
		--platform $(PLATFORMS) \
		--build-arg PX4_VERSION=$(PX4_VERSION) \
		--build-context multicosim=.. \
		--tag $(REGISTRY)/px4/firmware:$(MULTICOSIM_VERSION) \
		--load \
		.
	@mkdir -p .cache
	@touch $@


.PHONY: images gazebo firmware
