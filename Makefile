PX4_VERSION := 1.15.0
GZ_VERSION := harmonic
GZCM_VERSION := $(shell hatch version)
REGISTRY := ghcr.io/cpslab-asu/gzcm

.PHONY: all wheel images base gazebo gzcm px4-firmware px4-gazebo

all: wheel images

wheel:
	hatch build

base:
	docker build --file base.Dockerfile --tag $(REGISTRY)/base:22.04 .

gazebo: base
	docker build --file gazebo/gazebo.Dockerfile --tag $(REGISTRY)/gazebo:$(GZ_VERSION) gazebo

gzcm: base
	docker build --file gzcm.Dockerfile --tag $(REGISTRY)/gzcm:$(GZCM_VERSION) .

px4-firmware: gzcm
	docker build \
		--file px4/firmware.Dockerfile \
		--build-arg GZCM_VERSION=$(GZCM_VERSION) \
		--build-arg PX4_VERSION=$(PX4_VERSION) \
		--tag $(REGISTRY)/px4/firmware:$(PX4_VERSION) \
		px4

px4-gazebo: gazebo
	docker build \
		--file px4/firmware.Dockerfile \
		--build-arg GZ_VERSION=$(GZ_VERSION) \
		--tag $(REGISTRY)/px4/gazebo:$(GZ_VERSION) \
		px4

images: base gazebo gzcm px4-firmware px4-gazebo

