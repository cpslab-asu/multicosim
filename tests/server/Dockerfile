FROM python:3.14

RUN --mount=type=bind,from=multicosim,target=/src/multicosim pip install /src/multicosim

WORKDIR /app

COPY ./server.py ./server.py

CMD ["python3", "server.py"]
