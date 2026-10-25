FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/diligence/src

WORKDIR /opt/diligence

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir ".[dagster,postgres]"

COPY deploy/dagster ./deploy/dagster
