# UPS Vertiv PSL650 Monitor

Monitoreo del UPS Vertiv PSL650-230VA por USB HID. Compatible con Windows y QNAP (Docker).

## 📁 Estructura
├── windows/          # Script Python para Windows
│   └── README.md     # Documentación de la clase
├── ups-docker/      # Contenedor Docker para QNAP NAS
│   └── README.md     # Instrucciones Docker
└── README.md         # Este archivo
plain
Copy

## 🚀 Uso rápido

### Windows (PC)
```bash
cd windows
python ups_monitor.py
QNAP (NAS)
bash
Copy
cd ups-docker
# Ver instrucciones completas en ups-docker/README.md
⚡ Características
Lectura en tiempo real: tensión de red, batería, carga, frecuencia
Detección automática de cortes de energía
Logs con rotación automática (5MB)
Apagado automático del NAS por batería baja o corte prolongado
Salida JSON para integraciones
🔌 Compatibilidad
Testeado con:
UPS Vertiv PSL650-230VA
QNAP TS-xxx (QTS 5.x)
Windows 10/11
Otros modelos Vertiv/Liebert con protocolo Voltronic-QS pueden funcionar.
📄 Licencia
MIT License - Ver LICENSE
👤 Autor
@tinchodeluca
🤝 Contribuciones
PRs bienvenidos. Para cambios grandes, abrir issue primero.
⚠️ Disclaimer
Este proyecto no está afiliado con Vertiv. Úsalo bajo tu propia responsabilidad.

## `LICENSE` 

```text
MIT License

Copyright (c) 2026 [Martín A. De Luca]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---