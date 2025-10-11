FROM python:3.11-slim

# Evita preguntas en apt
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Paquetes de compilación (por si bcrypt requiere build)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libffi-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/

# AÑADIR websockets a requirements.txt o instalarlo aquí
RUN pip install --no-cache-dir -r requirements.txt websockets

# Copia todo el código
COPY . /app

# Puertos múltiples
EXPOSE 8501 8765 8000

# Ajustes recomendados para contenedor
ENV STREAMLIT_SERVER_ENABLECORS=false \
    STREAMLIT_SERVER_ENABLEXsSRFProtection=false \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Asegura carpeta para la DB
RUN mkdir -p /data
ENV DB_PATH=/data/agenda.db

# Script de inicio que ejecuta tanto Streamlit como WebSocket
COPY start_services.sh /app/
RUN chmod +x /app/start_services.sh

CMD ["/app/start_services.sh"]