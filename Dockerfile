FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install .

COPY authority ./authority

EXPOSE 8000

CMD ["python", "-m", "global_hybrid_v2.adapters.mcp_server"]
