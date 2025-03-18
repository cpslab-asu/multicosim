export PX4_VERSION ?= 1.15.0
export GZ_VERSION ?= harmonic
export MULTICOSIM_VERSION ?= $(shell hatch version)
export REGISTRY ?= ghcr.io/cpslab-asu/multicosim
export PLATFORMS ?= linux/amd64,linux/arm64

all: wheel images

wheel:
	hatch build

.cache/base: Dockerfile
	docker buildx build \
		--file Dockerfile \
		--platform $(PLATFORMS) \
		--tag $(REGISTRY)/base:22.04 \
		--load \
		.
	@mkdir -p .cache
	@touch $@

base: .cache/base

gazebo: base
	make -C gazebo image

px4: gazebo
	make -C px4 images

rover: gazebo
	make -C examples/rover images

images: base gazebo px4

.PHONY: all wheel base gazebo px4 images
