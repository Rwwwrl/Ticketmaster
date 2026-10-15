FROM python:3.14-slim
WORKDIR /app

ENV POETRY_VERSION=2.4.1
RUN pip install poetry==$POETRY_VERSION

COPY pyproject.toml ./
RUN poetry install --no-root --only main

COPY rabbitmq_topology/ ./rabbitmq_topology/
RUN poetry install --only main
