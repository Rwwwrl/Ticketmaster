FROM python:3.14-slim
WORKDIR /app

ENV POETRY_VERSION=1.8.3
RUN pip install poetry==$POETRY_VERSION

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main

COPY hello_world/ ./hello_world/
RUN poetry install --only main

EXPOSE 8080
CMD ["poetry", "run", "fastapi", "run", "hello_world/main.py", "--port", "8080", "--host", "0.0.0.0"]
