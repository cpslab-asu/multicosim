PX4_VERSION := 1.15.0
GZ_VERSION := harmonic
GZCM_VERSION := $(shell hatch version)
REGISTRY := ghcr.io/cpslab-asu/gzcm
PLATFORMS := linux/amd64,linux/arm64

all: wheel images

wheel:
	hatch build

.cache/base: base.Dockerfile
	docker build --file base.Dockerfile --platform $(PLATFORMS) --tag $(REGISTRY)/base:22.04 .
	@mkdir -p .cache
	@touch $@

base: .cache/base

gazebo: base
	make -C gazebo image

px4: gazebo
	make -C px4 images

images: base gazebo px4

.PHONY: all wheel base gazebo px4 images
