```markdown
# UPS Monitor - Windows

Script Python para monitorear UPS Vertiv PSL650 en Windows.

## 🐍 Clase `VertivUPS`

### Instalación

```bash
pip install hidapi
python ups_monitor.py
Uso básico
Python
Copy
from ups_monitor import VertivUPS

ups = VertivUPS()
ups.connect()

while True:
    ups.refresh()
    
    print(f"Entrada: {ups.InVoltage}V")
    print(f"Batería: {ups.BatVoltage}V")
    print(f"En batería: {ups.OnBattery}")
    print(f"Carga: {ups.LoadPercent}%")
    
    time.sleep(5)
📚 API Reference
Propiedades (lectura en tiempo real)
Table
Copy
Propiedad	Tipo	Descripción
InVoltage	float|None	Tensión de entrada (red) en volts
OutVoltage	float|None	Tensión de salida en volts
BatVoltage	float|None	Tensión de batería en volts
LoadPercent	int|None	Porcentaje de carga conectada
Frequency	float|None	Frecuencia en Hz
Temperature	float|None	Temperatura interna (None si no disponible)
OnBattery	bool	True si funciona con batería
StatusBits	str|None	Bits de estado crudos del protocolo
LastUpdate	datetime|None	Timestamp última lectura
IsConnected	bool	Estado de conexión USB
Estadísticas y eventos
Table
Copy
Propiedad	Tipo	Descripción
PromedioTensionLinea	float|None	Promedio histórico de tensión de red
PromedioTensionBateria	float|None	Promedio histórico de tensión de batería
EventosCorte	list[EventoCorte]	Lista de cortes de energía registrados
CorteEnCurso	EventoCorte|None	Evento actual si está en batería
DuracionCorteActual	float|None	Segundos desde inicio del corte actual
Métodos
connect() -> bool
Conecta al UPS vía USB HID. Retorna True si exitoso.
disconnect()
Cierra conexión USB.
refresh() -> bool
Lee nuevos datos del UPS. Actualiza todas las propiedades. Retorna True si pudo leer.
monitor(interval: int = 5)
Loop de monitoreo continuo. Bloqueante hasta Ctrl+C.
to_dict() -> dict
Exporta todos los datos actuales como diccionario (para JSON/API).
Eventos
La clase detecta automáticamente:
Inicio de corte: Cuando OnBattery pasa a True
Fin de corte: Cuando vuelve la energía
Duración: Calculada automáticamente
Voltaje inicial/final: Registrado por evento
📊 Formato de datos
ups_status.json
JSON
Copy
{
  "timestamp": "2026-02-24T23:51:04",
  "input_voltage": 8.4,
  "output_voltage": 214.1,
  "battery_voltage": 12.6,
  "load_percent": 4,
  "frequency": 50.0,
  "temperature": null,
  "on_battery": true,
  "status_bits": "00001001"
}
ups_events.json
JSON
Copy
[
  {
    "inicio": "2026-02-24T23:51:04",
    "fin": "2026-02-24T23:51:41",
    "duracion_segundos": 37.0,
    "voltaje_inicial_bateria": 12.6,
    "voltaje_final_bateria": 12.8
  }
]
🔧 Requisitos
Python 3.8+
hidapi (pip install hidapi)
UPS conectado por USB
📄 Licencia
MIT License
plain
Copy

---