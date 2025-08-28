variable "REGISTRY" {
  default = "ghcr.io"
}

variable "NAMESPACE" {
  default = "cpslab-asu/multicosim"
}

variable "UBUNTU_VERSION" {
  default = "22.04"
}

variable "UBUNTU_TAG" {
  default = ":${UBUNTU_VERSION}"
}

variable "ROCKY_VERSION" {
  default = "9"
}

target "ubuntu" {
  dockerfile = "ubuntu.Dockerfile"
  args = {
    UBUNTU_VERSION = UBUNTU_VERSION
  }
  tags = [
    "${REGISTRY}/${NAMESPACE}/ubuntu${UBUNTU_TAG}"
  ]
}

target "rocky-base" {
  dockerfile = "rocky.Dockerfile"
  target = "base"
  args = {
    ROCKY_VERSION = ROCKY_VERSION
  }
  tags = [
    "ghcr.io/cpslab-asu/multicosim/rocky:${ROCKY_VERSION}"
  ]
}

target "rocky-build" {
  inherits = ["rocky-base"]
  target = "build"
  tags = [
    "ghcr.io/cpslab-asu/multicosim/rocky/build:${ROCKY_VERSION}"
  ]
}

group "rocky" {
  targets = ["rocky-base", "rocky-build"]
}

group "base" {
  targets = ["ubuntu", "rocky"]
}

variable "MULTICOSIM_VERSION" {
  default = "latest"
}

variable "MULTICOSIM_TAG" {
  default = ":${MULTICOSIM_VERSION}"
}

target "multicosim" {
  dockerfile = "multicosim.Dockerfile"
  contexts = {
    ubuntu = "target:ubuntu"
  }
  tags = [
    "${REGISTRY}/${NAMESPACE}${MULTICOSIM_TAG}"
  ]
}

variable "GAZEBO_VERSION" {
  default = "harmonic"
}

variable "GAZEBO_TAG" {
  default = ":${GAZEBO_VERSION}"
}

target "gazebo-ubuntu" {
  context = "./gazebo"
  dockerfile = "ubuntu.Dockerfile"
  contexts = {
    ubuntu = "target:ubuntu",  # depends on ubuntu base image
  }
  args = {
    GAZEBO_VERSION = GAZEBO_VERSION
  }
  tags = [
    "${REGISTRY}/${NAMESPACE}/gazebo${GAZEBO_TAG}"
  ]
}

target "gazebo-rocky" {
  context = "./gazebo"
  contexts = {
    rocky = "target:rocky-build",  # depends on rocky build image
  }
  dockerfile = "rocky.Dockerfile"
  args = {
    GAZEBO_VERSION = GAZEBO_VERSION
    ROCKY_VERSION = ROCKY_VERSION
  }
  tags = [
    "ghcr.io/cpslab-asu/multicosim/rocky/gazebo:${GAZEBO_VERSION}"
  ]
}

group "gazebo" {
  targets = ["gazebo-ubuntu"]
}

target "px4-gazebo" {
  context = "./px4"
  contexts = {
    gazebo = "target:gazebo-ubuntu",
  }
  dockerfile = "gazebo.Dockerfile"
  tags = [
    "${REGISTRY}/${NAMESPACE}/px4/gazebo${GAZEBO_TAG}"
  ]
}

variable "PX4_VERSION" {
  default = "1.15.0"
}

target "px4-firmware" {
  context = "./px4"
  contexts = {
    ubuntu = "target:ubuntu"
    multicosim = "target:multicosim"
  }
  args = {
    PX4_VERSION = PX4_VERSION
  }
  dockerfile = "firmware.Dockerfile"
  tags = [
    "${REGISTRY}/${NAMESPACE}/px4/firmware${MULTICOSIM_TAG}"
  ]
}

group "px4" {
  targets = ["px4-gazebo", "px4-firmware"]
}

variable "ARDUPILOT_VERSION" {
  default = "4.5.7"
}

target "ardupilot-gazebo" {
  context = "./ardupilot"
  contexts = {
    gazebo = "target:gazebo-ubuntu"
  }
  dockerfile = "gazebo.Dockerfile"
  tags = [
    "${REGISTRY}/${NAMESPACE}/ardupilot/gazebo${GAZEBO_TAG}"
  ]
}

target "ardupilot-firmware" {
  context = "./ardupilot"
  contexts = {
    ubuntu = "target:ubuntu"
    multicosim = "target:multicosim"
  }
  args = {
    ARDUPILOT_VERSION = ARDUPILOT_VERSION
  }
  dockerfile = "firmware.Dockerfile"
  tags = [
    "${REGISTRY}/${NAMESPACE}/ardupilot/firmware${MULTICOSIM_TAG}"
  ]
}

group "ardupilot" {
  targets = ["ardupilot-firmware", "ardupilot-gazebo"]
}
