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
COPY semcode_settings.toml.sample ./semcode_settings.toml.sample
COPY src ./src
COPY docs ./docs

RUN pip install --upgrade pip setuptools wheel \
    && pip install .[ui]

ENV SEMCODE_CONFIG_PATH=/etc/semcode/semcode_settings.toml
COPY semcode_settings.toml.sample /etc/semcode/semcode_settings.toml

EXPOSE 8000
EXPOSE 8501

CMD ["semcode-api"]
