variable "UBUNTU_VERSION" {
  default = "24.04"
}

variable "ROCKY_VERSION" {
  default = "9"
}

variable "GAZEBO_VERSION" {
  default = "harmonic"
}

target "ubuntu" {
  dockerfile = "ubuntu.Dockerfile"
  args = {
    UBUNTU_VERSION = UBUNTU_VERSION
  }
  tags = [
    "ghcr.io/cpslab-asu/multicosim/base:ubuntu${UBUNTU_VERSION}"
  ]
}

target "rocky-base" {
  dockerfile = "rocky.Dockerfile"
  target = "base"
  args = {
    ROCKY_VERSION = ROCKY_VERSION
  }
  tags = [
    "ghcr.io/cpslab-asu/multicosim/base:rocky${ROCKY_VERSION}"
  ]
}

target "rocky-build" {
  inherits = ["rocky-base"]
  target = "build"
  tags = [
    "ghcr.io/cpslab-asu/multicosim/build:rocky${ROCKY_VERSION}"
  ]
}

group "rocky" {
  targets = ["rocky-base", "rocky-build"]
}

group "base" {
  targets = ["ubuntu", "rocky"]
}

target "gazebo-ubuntu" {
  context = "./gazebo"
  dockerfile = "ubuntu.Dockerfile"
  args = {
    GAZEBO_VERSION = GAZEBO_VERSION
    UBUNTU_VERSION = UBUNTU_VERSION
  }
  tags = [
    "ghcr.io/cpslab-asu/multicosim/gazebo:${GAZEBO_VERSION}-ubuntu${UBUNTU_VERSION}"
  ]
}

target "gazebo-rocky" {
  context = "./gazebo"
  dockerfile = "rocky.Dockerfile"
  args = {
    GAZEBO_VERSION = GAZEBO_VERSION
    ROCKY_VERSION = ROCKY_VERSION
  }
  tags = [
    "ghcr.io/cpslab-asu/multicosim/gazebo:${GAZEBO_VERSION}-rocky${ROCKY_VERSION}"
  ]
}

group "gazebo" {
  targets = ["gazebo-ubuntu", "gazebo-rocky"]
}
