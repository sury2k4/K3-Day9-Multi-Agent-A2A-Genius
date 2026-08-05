FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir ".[dev]"

CMD ["python", "-m", "src.batch_runner", "--help"]

