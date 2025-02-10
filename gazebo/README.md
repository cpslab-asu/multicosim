# Gazebo Container

This container is used to generate simulation configuration files and execute
them using the Gazebo simulator. Configuration files are generated using the
[`sdformat`][sdformat] specification. *Currently, only the physics backends can
be specified using the tool but additional configuration options are intended.*

In general, this container is meant to be used as a base for other containers
that contain system-specific models and worlds. Therefore, this container only
contains a single, empty world to use as a default template.

[sdformat]: https://sdformat.org

## Usage

This program is available in the container at the path `/usr/local/bin/gazebo`.
The base command accepts the following options:

| Name      | Short | Long          | Description                                                                                                                       |
|-----------|-------|---------------|-----------------------------------------------------------------------------------------------------------------------------------|
| Step Size | `-S`  | `--step-size` | The maximum time step of the physics solver                                                                                       |
| Base      | `-b`  | `--base`      | Path to the world file to use as the template for the generated configuration file.                                               |
| World     | `-w`  | `--world`     | The path to save the updated configuration file. The name of the file name without the extension is used as the name of the world |

The 4 different physics backends supported by Gazebo are `ode`, `dart`,
`bullet`, and `simbody`. Each one of these is represented as as sub-command with
its own set of options, documented in the following sections.

### ODE

| Name       | Short | Long           | Description                                                                                                       |
|------------|-------|----------------|-------------------------------------------------------------------------------------------------------------------|
| Solver     | `-s`  | `--solver`     | The differential equation solver to use. Different solvers can have different performance and accuracy.           |
| Iterations | `-i`  | `--iterations` | The number of solver iterations to use. More iterations can have a higher computation cost, but improve accuracy. |

**Example**: `/usr/local/bin/gazebo ode --iterations 50 --solver quick`

### Dart

| Name       | Short | Long           | Description                                                                                                       |
|------------|-------|----------------|-------------------------------------------------------------------------------------------------------------------|
| Solver     | `-s`  | `--solver`     | The differential equation solver to use. Different solvers can have different performance and accuracy.           |

**Example**: `/usr/local/bin/gazebo dart --solver quick`

### Bullet

| Name       | Short | Long           | Description                                                                                                       |
|------------|-------|----------------|-------------------------------------------------------------------------------------------------------------------|
| Iterations | `-i`  | `--iterations` | The number of solver iterations to use. More iterations can have a higher computation cost, but improve accuracy. |

**Example**: `/usr/local/bin/gazebo bullet --iterations 50`

### Simbody

The simbody backend does not currently have any configuration options.

**Example**: `/usr/local/bin/gazebo simbody`

## Building

This container can be build by running the `make image` command.

<!-- vim: set colorcolumn=80 textwidth=80: -->
