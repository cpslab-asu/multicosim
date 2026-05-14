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
    "ghcr.io/cpslab-asu/multicosim/px4/firmware:latest",
  ]
}
