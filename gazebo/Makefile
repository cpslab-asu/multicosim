REGISTRY = ghcr.io/cpslab-asu/gzcm
GZ_VERSION = harmonic
PLATFORMS = linux/amd64,linux/arm64
SOURCES := $(wildcard src/*.py) $(wildcard resources/worlds/*.sdf)

image: .cache/gazebo

.cache/gazebo: Dockerfile $(SOURCES)
	docker build \
		--platform $(PLATFORMS) \
		--tag $(REGISTRY)/gazebo:$(GZ_VERSION) \
		.
	@mkdir -p .cache
	@touch $@

.PHONY: image
