# Single image, 4 services — selección por env var MCP_SERVICE.
# Convención Cloud Run: el contenedor escucha en $PORT (lo inyecta Cloud Run).
FROM python:3.11-slim

# Evita bytecodes y buffering — mejor en logs Cloud Run.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencias del sistema: reportlab + pillow necesitan algunas libs gráficas.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

# Copiamos solo los manifests primero para cachear capa de pip install.
COPY pyproject.toml ./
COPY mcp_servers ./mcp_servers
COPY agent ./agent

RUN pip install -e .

# Defaults Cloud Run.
ENV MCP_TRANSPORT=http \
    PORT=8080 \
    MCP_SERVICE=geocoding

EXPOSE 8080

# Entrypoint: lee MCP_SERVICE y lanza el server correspondiente.
CMD ["sh", "-c", "python -m mcp_servers.${MCP_SERVICE}.server"]
