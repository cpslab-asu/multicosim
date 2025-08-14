OS_NAME ?= ubuntu
ifeq ($(OS_NAME),rocky)
REGISTRY ?= ghcr.io/cpslab-asu/multicosim/${OS_NAME}
else
REGISTRY ?= ghcr.io/cpslab-asu/multicosim
endif
GZ_VERSION ?= harmonic
PLATFORMS ?= linux/amd64,linux/arm64
SOURCES := $(wildcard src/*.py) $(wildcard resources/worlds/*.sdf)

image: .cache/gazebo

.cache/gazebo: $(OS_NAME).Dockerfile pyproject.toml uv.lock $(SOURCES)
	docker buildx build \
		--file $(OS_NAME).Dockerfile \
		--platform $(PLATFORMS) \
		--tag $(REGISTRY)/gazebo:$(GZ_VERSION) \
		--load \
		.
	@mkdir -p .cache
	@touch $@

.PHONY: image
