FROM python:3.14-slim
WORKDIR /app

RUN pip install --no-cache-dir "fastapi[standard]==0.136.*"

COPY hello/ ./hello/

EXPOSE 8080
CMD ["fastapi", "run", "hello/main.py", "--port", "8080", "--host", "0.0.0.0"]
