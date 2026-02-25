# UPS Monitor - Windows

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![Protocol](https://img.shields.io/badge/protocol-Voltronic--QS-orange)
![License](https://img.shields.io/badge/license-MIT-green)

Script Python para monitorear UPS Vertiv PSL650 en Windows vía USB HID.

---

# 🐍 Clase `VertivUPS`

## 📦 Instalación

```bash
pip install hidapi
python ups_monitor.py
```

---

# 🚀 Uso básico

```python
import time
from ups_monitor import VertivUPS

ups = VertivUPS()

if ups.connect():
    print("UPS conectado")

while True:
    if ups.refresh():
        print(f"Entrada: {ups.InVoltage}V")
        print(f"Batería: {ups.BatVoltage}V")
        print(f"En batería: {ups.OnBattery}")
        print(f"Carga: {ups.LoadPercent}%")
    
    time.sleep(5)
```

---

# 🏗 Arquitectura Interna

La clase está diseñada en capas:

```
USB HID → Parser Protocolo → Estado Interno → Motor de Eventos → Exportadores (JSON/API)
```

## 1️⃣ Capa de Comunicación
- Conexión USB HID directa
- Timeout configurable
- Reintento automático
- Manejo de desconexión física

## 2️⃣ Parser del Protocolo
- Decodificación Voltronic-QS
- Validación de payload
- Conversión segura a tipos numéricos
- Protección ante respuestas corruptas

## 3️⃣ Estado Interno
Mantiene snapshot consistente de:
- Tensiones
- Frecuencia
- Carga
- Temperatura
- Bits de estado

## 4️⃣ Motor de Eventos
Detecta transiciones:
- Red → Batería
- Batería → Red
- Genera objetos `EventoCorte`
- Calcula duración automáticamente

## 5️⃣ Exportadores
- JSON plano
- Diccionario Python
- Integración API-ready

---

# 📚 API Reference

## 🔎 Propiedades en Tiempo Real

| Propiedad | Tipo | Descripción |
|------------|------|-------------|
| `InVoltage` | float \| None | Tensión de entrada |
| `OutVoltage` | float \| None | Tensión de salida |
| `BatVoltage` | float \| None | Tensión batería |
| `LoadPercent` | int \| None | Porcentaje carga |
| `Frequency` | float \| None | Frecuencia Hz |
| `Temperature` | float \| None | Temperatura interna |
| `OnBattery` | bool | True si está en batería |
| `StatusBits` | str \| None | Bits crudos protocolo |
| `LastUpdate` | datetime \| None | Timestamp última lectura |
| `IsConnected` | bool | Estado USB |

---

## 📊 Estadísticas y Eventos

| Propiedad | Tipo | Descripción |
|------------|------|-------------|
| `PromedioTensionLinea` | float \| None | Promedio histórico línea |
| `PromedioTensionBateria` | float \| None | Promedio histórico batería |
| `EventosCorte` | list[EventoCorte] | Historial de cortes |
| `CorteEnCurso` | EventoCorte \| None | Corte actual |
| `DuracionCorteActual` | float \| None | Segundos transcurridos |

---

# 🧱 Modelo `EventoCorte`

```python
class EventoCorte:
    inicio: datetime
    fin: datetime | None
    duracion_segundos: float | None
    voltaje_inicial_bateria: float | None
    voltaje_final_bateria: float | None
```

### Ciclo de vida

1. Se crea cuando `OnBattery` pasa a `True`
2. Se completa cuando vuelve la energía
3. Calcula duración automáticamente
4. Se agrega a `EventosCorte`

---

# 🧠 Métodos

### `connect() -> bool`
Conecta al UPS vía USB HID.

### `disconnect()`
Cierra conexión USB.

### `refresh() -> bool`
Lee nuevos datos y actualiza estado.

### `monitor(interval: int = 5)`
Loop bloqueante continuo.

### `to_dict() -> dict`
Exporta snapshot completo listo para JSON.

---

# ⚠ Manejo de Errores

La clase maneja internamente:

- Desconexión USB inesperada
- Timeout de lectura
- Respuestas corruptas
- Reconexión automática

`refresh()` retorna `False` si falla lectura, pero no lanza excepción salvo error crítico.

---

# 🌐 Ejemplo de Integración con FastAPI

```python
from fastapi import FastAPI
from ups_monitor import VertivUPS

app = FastAPI()
ups = VertivUPS()
ups.connect()

@app.get("/ups")
def get_ups_status():
    ups.refresh()
    return ups.to_dict()
```

Permite exponer el UPS como microservicio REST.

---

# 📊 Formato JSON

## ups_status.json

```json
{
  "timestamp": "2026-02-24T23:51:04",
  "input_voltage": 214.1,
  "output_voltage": 214.1,
  "battery_voltage": 12.6,
  "load_percent": 4,
  "frequency": 50.0,
  "temperature": null,
  "on_battery": false,
  "status_bits": "00000001"
}
```

## ups_events.json

```json
[
  {
    "inicio": "2026-02-24T23:51:04",
    "fin": "2026-02-24T23:51:41",
    "duracion_segundos": 37.0,
    "voltaje_inicial_bateria": 12.6,
    "voltaje_final_bateria": 12.8
  }
]
```

---

# 🧩 Decisiones de Diseño

- No se usa NUT para evitar dependencias externas pesadas.
- Comunicación directa HID para mayor control.
- Diseño stateful para detección precisa de eventos.
- API-ready desde origen.
- Sin dependencias innecesarias (solo `hidapi`).

---

# 🔧 Requisitos

- Python 3.8+
- `hidapi`
- UPS conectado por USB

---

# 📄 Licencia

MIT License