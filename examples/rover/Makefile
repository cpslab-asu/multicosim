PLATFORMS ?= linux/amd64,linux/arm64

all: images

images: controller gazebo image

controller:
	make -C controller PLATFORMS=$(PLATFORMS) image

gazebo:
	make -C gazebo PLATFORMS=$(PLATFORMS) image

image:
	docker buildx build \
		--tag ghcr.io/cpslab-asu/multicosim/rover:0.2.0 \
		--build-context multicosim=../.. \
		.

.PHONY: all images controller gazebo
