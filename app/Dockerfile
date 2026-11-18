# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
WORKDIR /opt/app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 300 --retries 10 -r requirements.txt
COPY src ./src
COPY data ./data
ENV PYTHONPATH=/opt/app PYTHONUNBUFFERED=1
