FROM ubuntu:22.04

RUN mkdir -p /src/multicosim

RUN apt-get update && apt-get install -y python3 python3-pip
RUN pip install hatch

COPY --from=multicosim ./pyproject.toml ./README.md /src/multicosim
COPY --from=multicosim ./src /src/multicosim/src
COPY --from=multicosim ./examples /src/multicosim/examples

WORKDIR /src/multicosim
RUN HATCH_ENV_TYPE_VIRTUAL_PATH=/src/multicosim/.venv hatch env create examples

COPY <<EOF /usr/local/bin/rover
#!/usr/bin/bash
/src/multicosim/.venv/bin/python3 /src/multicosim/examples/rover/test.py
EOF

RUN chmod +x /usr/local/bin/rover
