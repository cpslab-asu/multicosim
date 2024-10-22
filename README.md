# GZCM

Library for managing firmware and Gazebo simulation containers

## Installation

This library can be installed either from PyPI using the command `pip install gzcm` or from github
by using the command `pip install https://github.com/cpslab-asu/gzcm#egg=gzcm`.

This library requires multiple docker containers to be available on the system. In general, these
containers will be downloaded if they do not exist, but they can also be built from source if
necessary. Instructions for building these containers are in the
[Building From Source](#building-from-source) section.

## Usage

In order to execute a simulation, simply import the system you are interested in simulating and
provide the appropriate configuration objects to customize the simulation. The following is a
simple example to demonstrate some of the configuration options available.

```python

import gzcm.px4 as px4
import gzcm.gazebo as gz

px4_config = px4.Config(model=px4.Model.X500)
gz_config = gz.Config(backend=gz.ODE(), step_size=0.001)

poses = px4.simulate(px4_config, gz_config)

```

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
by running the command `hatch run <script>`. For example, the *px4* example is run using the
command `hatch run px4`.

<!-- vim: set colorcolumn=100: -->
