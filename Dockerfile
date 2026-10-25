FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8765 \
    DB_PATH=/data/sop.db \
    SEED_DEMO=1

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown -R app:app /data

COPY --chown=app:app app.py ./
COPY --chown=app:app static ./static
COPY --chown=app:app docs ./docs
COPY --chown=app:app README.md LICENSE ./

USER app

EXPOSE 8765
VOLUME ["/data"]

CMD ["python", "app.py"]
