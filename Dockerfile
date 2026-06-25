FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create the data dir so SQLite has a place to write even without a volume.
RUN mkdir -p data

EXPOSE 8010

# Default env values for the container; overridden by docker-compose.
ENV DB_BACKEND=postgres \
    ENABLE_METRICS=true \
    ENABLE_TRACING=true \
    OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
