import nox
import nox_uv


@nox_uv.session(
    venv_backend="uv",
    uv_groups=["test"],
    python=["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"],
)
def test(session: nox.Session):
    session.run("python", "-m", "pytest", "./tests")  # pyright: ignore[reportUnusedCallResult]
