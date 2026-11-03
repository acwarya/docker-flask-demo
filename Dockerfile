# ---- build stage: install dependencies ----
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- runtime stage: small final image ----
FROM python:3.12-slim
ARG APP_VERSION=dev
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION}

WORKDIR /code
COPY --from=builder /install /usr/local
COPY app ./app

# Numeric non-root user (required for Kubernetes runAsNonRoot)
RUN useradd --no-create-home --uid 10001 appuser
USER 10001

EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=2)" || exit 1

# One worker + threads keeps in-process Prometheus counters accurate.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "app.main:create_app()"]
