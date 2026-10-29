FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirement.txt .
RUN pip install -r requirement.txt

COPY . .
RUN sed -i 's/\r$//' deploy/entrypoint.sh && chmod +x deploy/entrypoint.sh \
    && useradd --system --uid 1000 --home /app app \
    && mkdir -p /app/staticfiles /app/media && chown -R app:app /app

USER app

ENTRYPOINT ["deploy/entrypoint.sh"]
