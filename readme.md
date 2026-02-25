<p align="center">
  <img src="assets/logo.png" alt="UPS-MAN Logo" width="600">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.8%2B-blue">
  <img src="https://img.shields.io/badge/license-MIT-green">
  <img src="https://img.shields.io/badge/docker-supported-blue">
</p>

# UPS Vertiv PSL650 Monitor

Monitoreo del **UPS Vertiv PSL650-230VA** por USB HID.  
Compatible con Windows y QNAP (Docker).

---

## 📁 Estructura del proyecto

```
.
├── windows/          # Script Python para Windows
│   └── ups_monitor.py
├── ups-docker/       # Contenedor Docker para QNAP NAS
│   └── README.md
└── README.md
```

---

## 🚀 Uso rápido

### 🖥 Windows (PC)

```bash
cd windows
python ups_monitor.py
```

### 📦 QNAP (NAS)

```bash
cd ups-docker
```

Ver instrucciones completas en:

```
ups-docker/README.md
```

---

## ⚡ Características

- Lectura en tiempo real:
  - Tensión de red
  - Nivel de batería
  - Carga
  - Frecuencia
- Detección automática de cortes de energía
- Logs con rotación automática (5MB)
- Apagado automático del NAS por batería baja o corte prolongado
- Salida JSON para integraciones
- Arquitectura portable (Windows / Linux / Docker)

---

## 🏗 Arquitectura Técnica

El sistema se compone de tres capas principales:

### 1️⃣ Capa de comunicación USB HID
- Comunicación directa con el UPS vía USB.
- Implementación del protocolo **Voltronic-QS**.
- Polling periódico con timeout controlado.
- Manejo robusto de reconexión.

### 2️⃣ Capa de procesamiento
- Parseo de respuestas del UPS.
- Normalización de métricas.
- Detección de eventos:
  - Corte de red
  - Retorno de energía
  - Batería baja
  - Sobrecarga

### 3️⃣ Capa de acciones
- Logger con rotación automática.
- Salida JSON estructurada.
- Trigger configurable de apagado seguro del sistema.
- Integración simple con sistemas externos (REST, scripts, monitoreo).

### 🔁 Flujo simplificado

```
UPS → USB HID → Parser → Motor de eventos → Logger / Shutdown / JSON
```

---

## 🔌 Compatibilidad

Testeado con:

- UPS Vertiv PSL650-230VA
- QNAP TS series (QTS 5.x)
- Windows 10 / 11

Otros modelos Vertiv/Liebert compatibles con protocolo **Voltronic-QS** podrían funcionar.

---

## 📄 Licencia

MIT License – Ver `LICENSE`

---

## 👤 Autor

**Martín A. De Luca**  
[@tinchodeluca](https://github.com/tinchodeluca)

---

## 🤝 Contribuciones

PRs bienvenidos.  
Para cambios grandes, abrir un issue primero.

---

## ⚠️ Disclaimer

Este proyecto no está afiliado con Vertiv ni con Qnap.  
Úsalo bajo tu propia responsabilidad.