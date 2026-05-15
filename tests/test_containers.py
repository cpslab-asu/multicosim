import asyncio
import logging

import pytest
import typing_extensions

from multicosim import __version__, containers

Component: typing_extensions.TypeAlias = containers.Component


@pytest.fixture
def wait5() -> Component:
    return containers.Component(image="alpine:latest", command="sleep 5")


@pytest.fixture
def wait10() -> Component:
    return containers.Component(image="alpine:latest", command="sleep 10")


@pytest.mark.integration
def test_wait(caplog: pytest.LogCaptureFixture, wait5: Component, wait10: Component):
    caplog.set_level(logging.ERROR, "urllib3")
    caplog.set_level(logging.ERROR, "docker")

    sim = containers.Simulator()
    sim.add_component(wait10)
    sim.add_component(wait5, depends=[wait10])

    # wait5 depends on wait10, which will exit second so no error should be thrown
    with sim.run() as sys:
        asyncio.run(sys.wait_for(wait5))

    sim = containers.Simulator()
    sim.add_component(wait5)
    sim.add_component(wait10, depends=[wait5])

    # wait10 depends on wait5 which will exit first, so an error should be thrown
    with pytest.raises(containers.MonitoredContainerError):
        with sim.run() as sys:
            asyncio.run(sys.wait_for(wait10))


@pytest.mark.integration
def test_send(caplog: pytest.LogCaptureFixture, wait5: Component):
    caplog.set_level(logging.ERROR, "urllib3")
    caplog.set_level(logging.ERROR, "docker")

    server = containers.ConnectedComponent(
        image=f"multicosim/tests/server:{__version__}",
        command="python3 /app/server.py",
        msg_type=int,
        data_type=type(None),
        port=5556,
    )

    sim = containers.Simulator()
    sim.add_component(wait5)
    sim.add_component(server, depends=[wait5])

    with sim.run() as sys:
        _ = asyncio.run(sys.send(server, 3))

    with pytest.raises(containers.MonitoredContainerError):
        with sim.run() as sys:
            _ = asyncio.run(sys.send(server, 6))
