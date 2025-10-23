# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY semcod_settings.toml.sample ./semcod_settings.toml.sample
COPY src ./src
COPY docs ./docs

RUN pip install --upgrade pip setuptools wheel \
    && pip install .[ui]

ENV SEMCOD_CONFIG_PATH=/etc/semcod/semcod_settings.toml
COPY semcod_settings.toml.sample /etc/semcod/semcod_settings.toml

EXPOSE 8000
EXPOSE 8501

CMD ["semcod-api"]
