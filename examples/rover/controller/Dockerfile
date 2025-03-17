FROM ubuntu:22.04 AS build

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y python3

COPY --from=ghcr.io/astral-sh/uv:0.6.6 /uv /usr/bin/

RUN mkdir /opt/multicosim
COPY --from=multicosim ./pyproject.toml ./README.md /opt/multicosim
COPY --from=multicosim ./src /opt/multicosim/src

RUN mkdir /app
WORKDIR /app

COPY ./pyproject.toml ./uv.lock ./
RUN uv venv \
    --system-site-packages \
    --python 3.10 \
    --python-preference only-system \
    --relocatable
RUN uv sync --frozen --group container --no-install-project
RUN uv pip install /opt/multicosim

FROM ghcr.io/cpslab-asu/multicosim/base:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y \
        python3 \
        python3-gz-math7 \
        python3-gz-msgs10 \
        python3-gz-transport13 \
        && \
    rm -rf /var/lib/apt/lists/*
ENV DEBIAN_FRONTEND=

COPY --from=build /app /app
COPY ./src /app/src

COPY <<EOF /usr/local/bin/controller
#!/usr/bin/bash

/app/.venv/bin/python3 /app/src/main.py \$@
EOF

RUN chmod +x /usr/local/bin/controller
CMD ["/usr/local/bin/controller"]
