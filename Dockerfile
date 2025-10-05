# Dockerfile
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
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo el código
COPY . /app

# Puerto de Streamlit
EXPOSE 8501

# Ajustes recomendados para contenedor
ENV STREAMLIT_SERVER_ENABLECORS=false \
    STREAMLIT_SERVER_ENABLEXsSRFProtection=false \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Asegura carpeta para la DB
RUN mkdir -p /data
ENV DB_PATH=/data/agenda.db

# Si tu app usa app.py como entrada:
# (Streamlit buscará app.py en /app)
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
