# MultiCoSim

Library for managing multi-fidelity co-simulations of cyber-physical systems.

## Installation

This library can be installed either from PyPI using the command `pip install multicosim` or from github
by using the command `pip install https://github.com/cpslab-asu/multicosim#egg=multicosim`.

This library requires multiple docker containers to be available on the system. In general, these
containers will be downloaded if they do not exist, but they can also be built from source if
necessary. Instructions for building these containers are in the
[Building From Source](#building-from-source) section.

## Usage

In order to execute a simulation, import the system you are interested in simulating and
provide the appropriate configuration objects to customize the simulation. The following is a
simple example to demonstrate some of the configuration options available.

```python
import multicosim as mcs
import multicosim.gazebo as gz

px4 = mcs.PX4(model=mcs.PX4.Model.X500)
gazebo = mcs.Gazebo(backend=gz.ODE(), step_size=0.001)
poses = px4.simulate(gazebo)
```

You can also use this library to define your own systems for execution. In order to execute a
system there are two components that must be provided. The first the firmware execution program
that will run in the docker container and communicate with the Gazebo simulator. This can be
quickly implemented using the provided `multicosim.serve` decorator like so:

```python
# controller.py

import multicosim as mcs


class Config: ...


class Result: ...


@mcs.serve()
def server(msg: Config) -> Result:
    # Execute firmware
    ...


if __name__ == "__main__":
    server()
```

For this component, the msg parameter will be the datastructure that is sent to the firmware to
start the simulation, and the return value from the decorated function will be the datastructure
that is sent back when the simulation is complete and should contain the result data of the
simulation. This program needs to be loaded into a container image that is accessible by the docker
context the library is executed using.

The second required component is the configuration of an executor for the newly defined system
container. This can be implemented using the `multicosim.manage` decorator like so:

```python
# executor.py

import multicosim as mcs

import controller

@mcs.manage(
    firmware_image=...,
    gazebo_image=...,
    command=...,
    port=...,
    rtype=controller.Result,
)
def system(world: str, x: int, y: str) -> controller.Start:
    ...

if __name__ == "__main__":
    gz = mcs.Gazebo()
    result = system.run(gz, 10, "foo")
```

In this example, the `firmware_image` argument contains the name of the container image for
executing the firmware defined in the previous example, and the `gazebo_image` argument defines the
gazebo container image to use for simulation, which might contain additional models or plugins
depending on the simulation requirements. The `command` argument specifies what command to execute
for the system, and the `rtype` paramter defines the type that should be sent back from the
firmware when the simulation is terminated. The return value of the wrapped function is the message
that will be sent to the firmware to start the simulation. The wrapped function must accept at
minimum a `world` argument which is the name of the currently executing Gazebo world that can be
used to communicate with the simulator using the transport libraries. To execute a simulation, the
`run` method can be called, which accepts a `multicosim.Gazebo` instance representing the simulator
configuration and all the arguments of the wrapped function following the `world` argument.

## Building From Source

This project is the built using [Hatch](https://hatch.pypa.io) which is a packaging and library
management tool similar to [Poetry](https://python-poetry.org). To build this project, ensure that
you have the `hatch` binary available somewhere on your path ([Pipx](https://github.com/pypa/pipx)
is a good way to install python programs) and then run the command `hatch build wheel` to generate
an installable python wheel.

Building the library containers is accomplished using the provided `Makefile`. In particular, for
a specific system there will be a system container and possibly a specialized gazebo container. As
an example, to run PX4 simulations you will need to build the `px4-firmware` and `px4-gazebo` make
targets if you cannot download the images.

## Runing The Examples

Since this library is built using **Hatch**, we can utilize the environment management
functionality to help simply running the examples. Each example has a hatch
[`script`](https://hatch.pypa.io/latest/config/environment/overview/#scripts) that can be executed
by running the command `hatch run examples:<script>`. For example, the *px4* example is run using
the command `hatch run examples:px4`.

<!-- vim: set colorcolumn=100: -->
