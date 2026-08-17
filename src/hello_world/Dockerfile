FROM python:3.14-slim
WORKDIR /app

ENV POETRY_VERSION=2.4.1
RUN pip install poetry==$POETRY_VERSION

ARG CODEARTIFACT_INDEX_URL
COPY pyproject.toml ./

RUN --mount=type=secret,id=codeartifact_token \
    poetry source add --priority=supplemental codeartifact "$CODEARTIFACT_INDEX_URL" && \
    POETRY_HTTP_BASIC_CODEARTIFACT_USERNAME=aws \
    POETRY_HTTP_BASIC_CODEARTIFACT_PASSWORD="$(cat /run/secrets/codeartifact_token)" \
    poetry install --no-root --only main

COPY hello_world/ ./hello_world/
RUN poetry install --only main

EXPOSE 8080
