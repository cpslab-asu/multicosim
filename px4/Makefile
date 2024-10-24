PX4_VERSION = 1.15.0
GZ_VERSION = harmonic
GZCM_VERSION = $(shell hatch version)

all: firmware gazebo

firmware:
	make -C .. GZCM_VERSION=$(GZCM_VERSION) gzcm
	docker build \
		--file firmware.Dockerfile \
		--build-arg GZCM_VERSION=$(GZCM_VERSION) \
		--build-arg PX4_VERSION=$(PX4_VERSION) \
		--tag ghcr.io/cpslab-asu/gzcm/px4/firmware:$(PX4_VERSION) .

gazebo:
	make -C ../gazebo GZ_VERSION=$(GZ_VERSION) gazebo
	docker build \
		--file gazebo.Dockerfile \
		--build-arg GZ_VERSION=$(GZ_VERSION) \
		--tag ghcr.io/cpslab-asu/gzcm/px4/gazebo:$(GZ_VERSION) .

.PHONY: all firmware gazebo
