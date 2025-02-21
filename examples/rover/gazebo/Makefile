PLATFORMS ?= linux/amd64,linux/arm64
GZ_VERSION = harmonic

all: image

image:
	docker buildx build \
		--tag ghcr.io/cpslab-asu/ngc-rover-ha/gazebo:$(GZ_VERSION) \
		--build-arg GZ_VERSION=$(GZ_VERSION) \
		--platform $(PLATFORMS) \
		.
