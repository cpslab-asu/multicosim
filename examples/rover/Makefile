PLATFORMS ?= linux/amd64,linux/arm64

all: images

images: controller gazebo

controller:
	make -C controller PLATFORMS=$(PLATFORMS) image

gazebo:
	make -C gazebo PLATFORMS=$(PLATFORMS) image

.PHONY: all images controller gazebo
