FROM python:3.12.14-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create the writable data directory, then drop root permanently.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p data \
    && chown -R app:app /app

USER 10001:10001

EXPOSE 8010

# Default env values for the container; overridden by docker-compose.
ENV DB_BACKEND=postgres \
    ENABLE_METRICS=true \
    ENABLE_TRACING=true \
    OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
