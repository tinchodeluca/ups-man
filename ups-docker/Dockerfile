FROM python:3.11-alpine

# Instalar dependencias de sistema para USB/HID
RUN apk add --no-cache \
    libusb-dev \
    eudev-dev

# Crear usuario no-root (seguridad)
RUN adduser -D -u 1000 upsuser

WORKDIR /app

# Instalar Python deps primero (capa cacheada)
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY app/ .

# Crear directorios para datos y logs
RUN mkdir -p /app/data /app/logs && chown -R upsuser:upsuser /app

USER upsuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import json,sys; d=json.load(open('/app/data/ups_status.json')); sys.exit(0)" || exit 1

ENTRYPOINT ["python", "-u", "ups_monitor.py"]