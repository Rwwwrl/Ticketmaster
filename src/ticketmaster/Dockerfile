FROM python:3.14-slim
WORKDIR /app

ENV POETRY_VERSION=1.8.3
RUN pip install poetry==$POETRY_VERSION

ARG CODEARTIFACT_INDEX_URL
COPY pyproject.toml ./

RUN --mount=type=secret,id=codeartifact_token \
    poetry source add --priority=supplemental codeartifact "$CODEARTIFACT_INDEX_URL" && \
    poetry config http-basic.codeartifact aws "$(cat /run/secrets/codeartifact_token)" && \
    poetry install --no-root --only main

COPY ticketmaster/ ./ticketmaster/
COPY alembic.ini ./
COPY migrations/ ./migrations/
RUN poetry install --only main

EXPOSE 8080
CMD ["poetry", "run", "fastapi", "run", "ticketmaster/http/main.py", "--port", "8080", "--host", "0.0.0.0"]
