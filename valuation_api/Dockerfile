FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build context = valuation_api/ (deploy script pre-copies mcp_servers/ here).
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY mcp_servers ./mcp_servers
COPY app.py engine.py __init__.py ./

ENV PORT=8080
EXPOSE 8080

# app.py imports `from engine import run_valuation` (flat layout in container).
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
