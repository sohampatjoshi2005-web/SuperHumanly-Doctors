# Stage 1: Build dependencies
FROM python:3.14-slim as builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PATH=/home/appuser/.local/bin:$PATH

# Install runtime dependencies (ffmpeg for transcription, libpq for database)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r appgroup && useradd -r -g appgroup -d /home/appuser -m appuser
USER appuser

WORKDIR /app

# Copy installed packages from builder to runtime stage
COPY --from=builder /root/.local /home/appuser/.local
COPY . .

# Ensure appuser has permissions for the application and shared storage directory
USER root
RUN mkdir -p /tmp/superhumanly && chown -R appuser:appgroup /tmp/superhumanly /app
USER appuser

EXPOSE 8000

# AWS ECS/Target Group compatible health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Production server configuration: Gunicorn with Uvicorn workers
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "--timeout", "120", "--max-requests", "1000", "--max-requests-jitter", "50"]
