FROM base

LABEL org.opencontainers.image.source=https://github.com/cpslab-asu/multicosim
LABEL org.opencontainers.image.description="Controller image for MultiCoSim rover example"
LABEL org.opencontainers.image.license=BSD-3-Clause

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        python3-gz-math7 \
        python3-gz-msgs10 \
        python3-gz-transport13 \
        && \
    rm -rf /var/lib/apt/lists/*

RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
    --mount=target=/src \
    UV_WORKING_DIR=/src uv pip install --no-editable --system examples/rover-controller

CMD ["python3", "-m", "roverctl", "serve"]
