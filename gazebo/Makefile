REGISTRY = ghcr.io/cpslab-asu/gzcm
GZ_VERSION = harmonic
PLATFORMS = linux/amd64,linux/arm64

image:
	docker build \
		--platform $(PLATFORMS) \
		--tag $(REGISTRY)/gazebo:$(GZ_VERSION) \
		.

.PHONY: image
