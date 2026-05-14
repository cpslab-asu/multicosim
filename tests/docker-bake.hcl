group "default" {
  targets = ["wait-server"]
}

target "wait-server" {
  context = "./wait-server"
  contexts = {
    multicosim = ".."
  }
  tags = [
    "multicosim/tests/wait-server:latest"
  ]
}
