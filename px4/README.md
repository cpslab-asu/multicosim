# PX4 Containers

This project defines two containers that are meant to be used to run simulated
missions using the [`PX4`][px4] flight control software. The first container
executes the PX4 firmware, and the second container executes a Gazebo simulation
using the models provided by the PX4 team.

[px4]: https://px4.io

## Firmware Container

The firmware container is responsible for executing the PX4 firmware and
recording the positions of the drone using the [Gazebo transport
library][gz-transport]. Command of the drone is accomplished using the
[MAVSDK][mavsdk] python library, which uploads the mission waypoints to the
drone and is responsible for detecting when the mission has completed.

This program is available in the container at the path
`/usr/local/bin/firmware`. Upon execution, the program will start a
[ZeroMQ][zmq] server that will listen for the start message. Once the start
message is received, the program will start the firmware, upload and execute the
mission, and then send back the recorded drone positions before shutting down.

The program accepts the following options:

| Name | Short | Long     | Description                     |
|------|-------|----------|---------------------------------|
| Port | `-p`  | `--port` | The port to bind the server to. |

## Gazebo Container

The gazebo container is constructed using the base Gazebo image in the `gazebo`
directory. The only modification is the addition of the models and worlds 
defined in the [`px4-gazebo-models`](https://github.com/px4/px4-gazebo-models)
repository.

## Building

The firmware container can be build using the command `make firmware` and the
gazebo container can be build using the command `make gazebo`. Both images can
be built using the `make images` command.

<!-- vim: set colorcolumn=80 textwidth=80: -->
