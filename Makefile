PX4_VERSION := 1.15.0
GZ_VERSION := harmonic
GZCM_VERSION := $(shell hatch version)
REGISTRY := ghcr.io/cpslab-asu/gzcm
PLATFORMS := linux/amd64,linux/arm64

.PHONY: all wheel images base gazebo px4-firmware px4-gazebo

all: wheel images

wheel:
	hatch build

base:
	docker build --file base.Dockerfile --platform $(PLATFORMS) --tag $(REGISTRY)/base:22.04 .

gazebo: base
	docker build \
		--file gazebo/gazebo.Dockerfile \
		--platform $(PLATFORMS) \
		--tag $(REGISTRY)/gazebo:$(GZ_VERSION) \
		gazebo

px4-firmware: base
	docker build \
		--file px4/firmware.Dockerfile \
		--platform $(PLATFORMS) \
		--build-arg PX4_VERSION=$(PX4_VERSION) \
		--build-context gzcm=. \
		--tag $(REGISTRY)/px4/firmware:$(GZCM_VERSION) \
		px4

px4-gazebo: gazebo
	docker build \
		--file px4/gazebo.Dockerfile \
		--platform $(PLATFORMS) \
		--build-arg GZ_VERSION=$(GZ_VERSION) \
		--tag $(REGISTRY)/px4/gazebo:$(GZ_VERSION) \
		px4

images: base gazebo px4-firmware px4-gazebo

