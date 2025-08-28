variable "UBUNTU_VERSION" {
  default = "22.04"
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
    "ghcr.io/cpslab-asu/multicosim/ubuntu:${UBUNTU_VERSION}"
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

target "multicosim" {
  dockerfile = "multicosim.Dockerfile"
  contexts = {
    ubuntu = "target:ubuntu"
  }
  args = {
    UBUNTU_VERSION = UBUNTU_VERSION
  }
  tags = [
    "ghcr.io/cpslab-asu/multicosim:${MULTICOSIM_VERSION}"
  ]
}

target "gazebo-ubuntu" {
  context = "./gazebo"
  dockerfile = "ubuntu.Dockerfile"
  contexts = {
    ubuntu = "target:ubuntu",  # depends on ubuntu base image
  }
  args = {
    GAZEBO_VERSION = GAZEBO_VERSION
    UBUNTU_VERSION = UBUNTU_VERSION
  }
  tags = [
    "ghcr.io/cpslab-asu/multicosim/gazebo:${GAZEBO_VERSION}"
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
  targets = ["gazebo-ubuntu", "gazebo-rocky"]
}

target "px4-gazebo" {
  context = "./px4"
  contexts = {
    ubuntu = "target:gazebo-ubuntu",
  }
  args = {
    UBUNTU_VERSION = UBUNTU_VERSION
    GAZEBO_VERSION = GAZEBO_VERSION
  }
  dockerfile = "gazebo.Dockerfile"
  tags = [
    "ghcr.io/cpslab-asu/multicosim/px4/gazebo:${GAZEBO_VERSION}"
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
    UBUNTU_VERSION = UBUNTU_VERSION
    PX4_VERSION = PX4_VERSION
    MULTICOSIM_VERSION = MULTICOSIM_VERSION
  }
  dockerfile = "firmware.Dockerfile"
  tags = [
    "ghcr.io/cpslab-asu/multicosim/px4/firmware:${MULTICOSIM_VERSION}"
  ]
}

group "px4" {
  targets = ["px4-gazebo", "px4-firmware"]
}

variable "ARDUPILOT_VERSION" {
  default = "4.5.7"
}

target "ardupilot-firmware" {
  context = "./ardupilot"
  contexts = {
    ubuntu = "target:ubuntu"
    multicosim = "target:multicosim"
  }
  args = {
    UBUNTU_VERSION = UBUNTU_VERSION
    ARDUPILOT_VERSION = ARDUPILOT_VERSION
    MULTICOSIM_VERSION = MULTICOSIM_VERSION
  }
  dockerfile = "firmware.Dockerfile"
  tags = [
    "ghcr.io/cpslab-asu/multicosim/ardupilot/firmware:${MULTICOSIM_VERSION}"
  ]
}

target "ardupilot-gazebo" {
  context = "./ardupilot"
  contexts = {
    gazebo = "target:gazebo-ubuntu"
  }
  args = {
    GAZEBO_VERSION = GAZEBO_VERSION
  }
  dockerfile = "gazebo.Dockerfile"
  tags = [
    "ghcr.io/cpslab-asu/multicosim/ardupilot/gazebo:${GAZEBO_VERSION}"
  ]
}

group "ardupilot" {
  targets = ["ardupilot-firmware", "ardupilot-gazebo"]
}
