export PX4_VERSION ?= 1.15.0
export GZ_VERSION ?= harmonic
export MULTICOSIM_VERSION ?= $(shell hatch version)
export OS_NAME ?= ubuntu
export OS_VERSION ?= 22.04
ifeq ($(OS_NAME),rocky)
export REGISTRY ?= ghcr.io/cpslab-asu/multicosim/$(OS_NAME)
else
export REGISTRY ?= ghcr.io/cpslab-asu/multicosim
endif

export PLATFORMS ?= linux/amd64,linux/arm64

all: wheel images

wheel:
	hatch build

.cache/base: $(OS_NAME).Dockerfile
	docker buildx build \
		--file $(OS_NAME).Dockerfile \
		--platform $(PLATFORMS) \
		--tag $(REGISTRY)/base:$(OS_VERSION) \
		--load \
		.
	@mkdir -p .cache
	@touch $@

.cache/build: rocky_build.Dockerfile
	docker buildx build \
		--file rocky_build.Dockerfile \
		--platform $(PLATFORMS) \
		--tag $(REGISTRY)/build:$(OS_VERSION) \
		--load \
		.
	@mkdir -p .cache
	@touch $@

ifeq ($(OS_NAME),rocky)
base: .cache/base .cache/build
else
base: .cache/base
endif

gazebo: base
	make -C gazebo image

px4: gazebo
	make -C px4 images

ardupilot: gazebo
	make -C ardupilot images

images: base gazebo px4

.PHONY: all wheel base gazebo px4 images
