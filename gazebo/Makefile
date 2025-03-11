REGISTRY ?= ghcr.io/cpslab-asu/multicosim
GZ_VERSION ?= harmonic
PLATFORMS ?= linux/amd64,linux/arm64
SOURCES := $(wildcard src/*.py) $(wildcard resources/worlds/*.sdf)

image: .cache/gazebo

.cache/gazebo: Dockerfile pyproject.toml uv.lock $(SOURCES)
	docker buildx build \
		--platform $(PLATFORMS) \
		--tag $(REGISTRY)/gazebo:$(GZ_VERSION) \
		--load \
		.
	@mkdir -p .cache
	@touch $@

.PHONY: image
