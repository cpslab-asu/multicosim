export GZ_VERSION ?= harmonic
export GZCM_VERSION ?= $(shell hatch version)
export REGISTRY ?= ghcr.io/cpslab-asu/multicosim
export PLATFORMS ?= linux/amd64,linux/arm64

all: images

images: gazebo

gazebo: .cache/gazebo

.cache/gazebo: gazebo.Dockerfile
	docker buildx build \
		--file gazebo.Dockerfile \
		--platform $(PLATFORMS) \
		--tag $(REGISTRY)/ardupilot/gazebo:$(GZ_VERSION) \
		.
	@mkdir -p $(shell dirname $@)
	@touch $@
