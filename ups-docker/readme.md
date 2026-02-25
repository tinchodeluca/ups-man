UPS Vertiv PSL650 - Monitor para QNAP
Monitor de UPS Vertiv PSL650 vía USB usando Docker en QNAP.
📁 Estructura
plain
Copy
/share/UPS/ups-docker/
├── app/
│   ├── ups_monitor.py      # Script principal
│   └── requirements.txt    # Dependencias
├── data/
│   ├── ups_status.json     # Estado actual del UPS
│   ├── ups_events.json     # Historial de cortes
│   └── SHUTDOWN_REQUESTED  # Flag de apagado (si aplica)
└── logs/
    └── ups.log             # Logs con rotación (5MB x 3 archivos)
🚀 Comandos útiles
Ver estado
bash
Copy
# Logs en vivo
docker -H unix:///var/run/system-docker.sock logs -f vertiv-ups

# Últimas 50 líneas
docker -H unix:///var/run/system-docker.sock logs --tail 50 vertiv-ups

# Estado del contenedor
docker -H unix:///var/run/system-docker.sock ps
Datos del UPS
bash
Copy
# Estado actual (JSON)
cat /share/UPS/ups-docker/data/ups_status.json

# Eventos de corte
cat /share/UPS/ups-docker/data/ups_events.json
Control
bash
Copy
# Parar
docker -H unix:///var/run/system-docker.sock stop vertiv-ups

# Iniciar
docker -H unix:///var/run/system-docker.sock start vertiv-ups

# Reiniciar
docker -H unix:///var/run/system-docker.sock restart vertiz-ups

# Eliminar (conserva datos en /data y /logs)
docker -H unix:///var/run/system-docker.sock rm vertiv-ups
⚡ Configuración
Variables en el comando docker run:
Table
Copy
Variable	Default	Descripción
CHECK_INTERVAL	10	Segundos entre lecturas
SHUTDOWN_VOLTAGE	11.0	Voltaje crítico de batería
SHUTDOWN_DELAY	300	Segundos antes de apagar en corte
📊 Datos disponibles
En ups_status.json:
input_voltage - Tensión de red (V)
battery_voltage - Tensión de batería (V)
load_percent - Carga conectada (%)
on_battery - true/false
timestamp - Última actualización
🔋 Apagado automático
El contenedor puede apagar el NAS cuando:
Batería < 11.0V, o
Corte dura > 5 minutos
Para que funcione, crear script en el NAS que lea el flag:
bash
Copy
# /share/UPS/check_shutdown.sh
if [ -f /share/UPS/ups-docker/data/SHUTDOWN_REQUESTED ]; then
    /sbin/poweroff
fi