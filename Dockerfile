FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY src ./src
RUN pip install --no-cache-dir .
COPY migrations ./migrations
CMD ["python", "-m", "olist_disputes.cli", "run-batch"]
