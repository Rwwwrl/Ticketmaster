FROM python:3.14-slim
WORKDIR /app

ENV POETRY_VERSION=2.4.1
RUN pip install poetry==$POETRY_VERSION

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main

COPY hello_world/ ./hello_world/
RUN poetry install --only main

EXPOSE 8080
