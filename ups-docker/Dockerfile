FROM python:3.11-alpine

# Instalar dependencias de sistema para USB/HID
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libusb-dev \
    hidapi-dev \
    eudev-dev

# Crear usuario no-root (seguridad)
RUN adduser -D -u 1000 upsuser

WORKDIR /app

# Instalar Python deps
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY app/ .

# Crear directorios para datos
RUN mkdir -p /app/data /app/logs && chown -R upsuser:upsuser /app

USER upsuser

CMD ["python", "-u", "ups_monitor.py"]