FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY . .

RUN python -m pip install --upgrade pip && python -m pip install -e .

EXPOSE 8000

CMD ["python", "-m", "mcp_clinical.server"]
