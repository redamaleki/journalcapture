FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt gunicorn

COPY . /app

ENV JOURNAL_HOST=0.0.0.0 \
    JOURNAL_PORT=5000 \
    JOURNAL_DEBUG=false \
    JOURNAL_DATA_DIR=/data \
    JOURNAL_JOURNALS_DIR=/data/journals \
    JOURNAL_THUMBS_DIR=/data/.thumbnails \
    JOURNAL_BACKUP_CONFIG_PATH=/data/config/backup_config.yml

EXPOSE 5000

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
