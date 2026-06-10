variable "MULTICOSIM_VERSION" {
  default = "latest"
}

group "default" {
  targets = ["gazebo", "ardupilot", "px4"]
}

target "base" {
  dockerfile = "ubuntu.Dockerfile"
}

target "gazebo" {
  context = "./gazebo"
  contexts = {
    base = "target:base"
    multicosim = "."
  }
  dockerfile = "ubuntu.Dockerfile"
  tags = [
    "ghcr.io/cpslab-asu/multicosim/gazebo:harmonic"
  ]
}

group "ardupilot" {
  targets = ["ardupilot-gazebo", "ardupilot-firmware"]
}

target "ardupilot-gazebo" {
  context = "./ardupilot"
  contexts = {
    gazebo = "target:gazebo"
  }
  dockerfile = "gazebo.Dockerfile"
  tags = [
    "ghcr.io/cpslab-asu/multicosim/ardupilot/gazebo:harmonic",
  ]
}

target "ardupilot-firmware" {
  context = "./ardupilot"
  contexts = {
    base = "target:base"
    multicosim = "."
  }
  dockerfile = "firmware.Dockerfile"
  tags = [
    "ghcr.io/cpslab-asu/multicosim/ardupilot/firmware:latest",
  ]
}

group "px4" {
  targets = ["px4-gazebo", "px4-firmware"]
}

target "px4-gazebo" {
  context = "./px4"
  contexts = {
    gazebo = "target:gazebo"
  }
  dockerfile = "gazebo.Dockerfile"
  tags = [
    "ghcr.io/cpslab-asu/multicosim/px4/gazebo:harmonic"
  ]
}

target "px4-firmware" {
  context = "./px4"
  contexts = {
    base = "target:base"
    multicosim = "."
  }
  dockerfile = "firmware.Dockerfile"
  tags = [
    "ghcr.io/cpslab-asu/multicosim/px4/firmware:${MULTICOSIM_VERSION}",
  ]
}

group "tests" {
  targets = ["tests-server"]
}

target "tests-server" {
  context = "./tests/server"
  contexts = {
    multicosim = "."
  }
  tags = [
    "multicosim/tests/server:${MULTICOSIM_VERSION}",
  ]
}

group "examples" {
  targets = ["rover"]
}

group "rover" {
  targets = ["rover-controller", "rover-gazebo"]
}

target "rover-controller" {
  context = "examples/rover-controller"
  contexts = {
    base = "target:base"
    multicosim = "."
  }
  tags = [
    "ghcr.io/cpslab-asu/multicosim/rover/controller:${MULTICOSIM_VERSION}"
  ]
}

target "rover-gazebo" {
  context = "examples/rover-gazebo"
  contexts = {
    gazebo = "target:gazebo"
  }
  tags = [
    "ghcr.io/cpslab-asu/multicosim/rover/gazebo:harmonic"
  ]
}
