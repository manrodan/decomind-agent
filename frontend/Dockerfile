FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencias del sistema (mínimas — sin imágenes en el frontend, pero el
# agent importa el módulo dossier_pdf que pull reportlab/pillow).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

# Código de la app + agente + servidores MCP (copiados por deploy_frontend.ps1
# desde el repo root). El agente HTTP toolset llamará a los MCPs en Cloud Run.
COPY app.py ./
COPY static ./static
COPY agent ./agent
COPY mcp_servers ./mcp_servers

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
