all: image

image:
	docker buildx build \
		--tag ghcr.io/cpslab-asu/multicosim/rover/controller:latest \
		--build-context multicosim=../../.. \
		.
