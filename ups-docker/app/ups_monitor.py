import usb.core
import usb.util
import usb.backend.libusb1

_backend = usb.backend.libusb1.get_backend(find_library=lambda x: "/usr/lib/libusb-1.0.so.0")
import time
import json
import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List

from logging.handlers import RotatingFileHandler

# Configurar logging
handler = RotatingFileHandler(
    '/app/logs/ups.log', 
    maxBytes=5*1024*1024,  # 5 MB máximo
    backupCount=3          # Mantener 3 backups
)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[handler, logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Config desde variables de entorno
VID = int(os.getenv('UPS_VID', '0x0665'), 16)
PID = int(os.getenv('UPS_PID', '0x5161'), 16)
CHECK_INTERVAL   = int(os.getenv('CHECK_INTERVAL', '10'))
SHUTDOWN_VOLTAGE = float(os.getenv('SHUTDOWN_VOLTAGE', '11.0'))
SHUTDOWN_DELAY   = int(os.getenv('SHUTDOWN_DELAY', '300'))  # 5 minutos

# Validar rangos de config
if not (0 < VID <= 0xFFFF):
    raise ValueError(f"UPS_VID inválido: {VID:#06x}")
if not (0 < PID <= 0xFFFF):
    raise ValueError(f"UPS_PID inválido: {PID:#06x}")
if CHECK_INTERVAL < 1:
    raise ValueError(f"CHECK_INTERVAL debe ser >= 1, valor: {CHECK_INTERVAL}")
if not (5.0 <= SHUTDOWN_VOLTAGE <= 20.0):
    raise ValueError(f"SHUTDOWN_VOLTAGE fuera de rango (5-20V): {SHUTDOWN_VOLTAGE}")
if SHUTDOWN_DELAY < 0:
    raise ValueError(f"SHUTDOWN_DELAY no puede ser negativo: {SHUTDOWN_DELAY}")

@dataclass
class EventoCorte:
    inicio: str
    fin: Optional[str] = None
    duracion_segundos: Optional[float] = None
    voltaje_inicial_bateria: float = 0.0
    voltaje_final_bateria: Optional[float] = None

class UPSMonitor:
    def __init__(self):
        self.device = None
        self._ep_in = None
        self.data: Optional[Dict] = None
        self.timestamp: Optional[datetime] = None
        self._corte_actual: Optional[EventoCorte] = None
        self._eventos: List[EventoCorte] = []
        self._historial_bat: List[float] = []

        # Buzzer: estado trackeado por software (Q no da ACK)
        self._buzzer_on: bool = False
        self._bat_critica_avisada: bool = False

        # Archivos de salida
        self.status_file = Path('/app/data/ups_status.json')
        self.events_file = Path('/app/data/ups_events.json')
        
        # Asegurar que existan directorios
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
    
    @property
    def InVoltage(self) -> Optional[float]:
        return self.data.get('input_voltage') if self.data else None
    
    @property
    def BatVoltage(self) -> Optional[float]:
        return self.data.get('battery_voltage') if self.data else None
    
    @property
    def OnBattery(self) -> bool:
        return self.data.get('on_battery', False) if self.data else False
    
    @property
    def LoadPercent(self) -> Optional[int]:
        return self.data.get('load_percent') if self.data else None
    
    def connect(self) -> bool:
        try:
            dev = usb.core.find(idVendor=VID, idProduct=PID, backend=_backend)
            if dev is None:
                raise Exception("Dispositivo no encontrado")
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
            dev.set_configuration()
            cfg = dev.get_active_configuration()
            intf = cfg[(0, 0)]
            self._ep_in = usb.util.find_descriptor(
                intf, custom_match=lambda e:
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
            )
            if self._ep_in is None:
                raise Exception("Endpoint IN no encontrado")
            self.device = dev
            logger.info(f"UPS conectado VID:{VID:04X} PID:{PID:04X}")
            return True
        except Exception as e:
            logger.error(f"Error conectando: {e}")
            self.device = None
            self._ep_in = None
            return False

    def disconnect(self):
        if self.device:
            try:
                usb.util.dispose_resources(self.device)
            except Exception:
                pass
            self.device = None
            self._ep_in = None
    
    def read_data(self) -> bool:
        """Lee datos del UPS"""
        if not self.device:
            return False
        
        try:
            # Enviar QS via HID Set_Report (control transfer, no hay EP OUT)
            payload = b'QS\r'
            buf = payload + bytes(8 - len(payload))
            self.device.ctrl_transfer(0x21, 9, 0x0200, 0, buf)
            time.sleep(0.1)

            # Acumular respuesta
            start = time.time()
            fragments = []
            while time.time() - start < 1.2:
                try:
                    data = self._ep_in.read(self._ep_in.wMaxPacketSize, timeout=100)
                    if data:
                        clean = bytes(b for b in data if b != 0)
                        if clean:
                            fragments.append(clean.decode('ascii', errors='ignore'))
                except usb.core.USBTimeoutError:
                    pass
                time.sleep(0.05)
            
            text = ''.join(fragments)
            if text.startswith('QS'):
                text = text[2:].strip()
            
            # Parsear
            if '(' not in text:
                return False
            
            parts = text[text.find('(')+1:].strip().split()
            if len(parts) < 8:
                return False
            
            temp_str = parts[6]
            input_v      = float(parts[0])
            output_v     = float(parts[2])
            load_pct     = int(parts[3])
            frequency    = float(parts[4])
            battery_v    = float(parts[5])
            temperature  = float(temp_str) if temp_str not in ('--.-', '---.-', 'N/A') else None

            # Validar rangos antes de usar los datos
            if not (0.0 <= input_v <= 300.0):
                logger.warning(f"input_voltage fuera de rango: {input_v}V — descartando lectura")
                return False
            if not (0.0 <= output_v <= 300.0):
                logger.warning(f"output_voltage fuera de rango: {output_v}V — descartando lectura")
                return False
            if not (0 <= load_pct <= 100):
                logger.warning(f"load_percent fuera de rango: {load_pct}% — descartando lectura")
                return False
            if not (40.0 <= frequency <= 70.0):
                logger.warning(f"frequency fuera de rango: {frequency}Hz — descartando lectura")
                return False
            if not (0.0 <= battery_v <= 30.0):
                logger.warning(f"battery_voltage fuera de rango: {battery_v}V — descartando lectura")
                return False

            self.data = {
                'input_voltage'   : input_v,
                'output_voltage'  : output_v,
                'load_percent'    : load_pct,
                'frequency'       : frequency,
                'battery_voltage' : battery_v,
                'temperature'     : temperature,
                'status_bits'     : parts[7],
                'on_battery'      : input_v < 100.0,
            }
            self.timestamp = datetime.now()
            
            # Guardar historial
            self._historial_bat.append(self.data['battery_voltage'])
            if len(self._historial_bat) > 100:
                self._historial_bat = self._historial_bat[-100:]
            
            return True
            
        except Exception as e:
            logger.error(f"Error leyendo: {e}")
            return False
    
    def check_events(self):
        """Gestiona eventos de corte"""
        if not self.data:
            return
        
        ahora = datetime.now().isoformat()
        en_bateria = self.OnBattery
        
        # Inicio corte
        if en_bateria and not self._corte_actual:
            self._corte_actual = EventoCorte(
                inicio=ahora,
                voltaje_inicial_bateria=self.BatVoltage
            )
            logger.warning(f"⚡ CORTE DE ENERGÍA - Bat: {self.BatVoltage}V")
            self.save_events()
            # 2 beeps cortos para avisar el corte
            self.buzzer_beep(1.0)
            time.sleep(0.3)
            self.buzzer_beep(1.0)

        # Fin corte
        elif not en_bateria and self._corte_actual:
            corte     = self._corte_actual
            corte.fin = ahora
            corte.voltaje_final_bateria = self.BatVoltage

            inicio = datetime.fromisoformat(corte.inicio)
            fin    = datetime.fromisoformat(corte.fin)
            corte.duracion_segundos = (fin - inicio).total_seconds()

            self._eventos.append(corte)
            self._corte_actual = None
            self._bat_critica_avisada = False

            logger.info(f"✅ Retornó energía - Duración: {corte.duracion_segundos:.0f}s")
            self.save_events()
            # 1 beep corto de confirmación
            self.buzzer_beep(0.5)
    
    def check_shutdown(self):
        """Verifica si debe apagar el sistema"""
        if not self.OnBattery or not self._corte_actual:
            return
        
        # Calcular duración
        inicio   = datetime.fromisoformat(self._corte_actual.inicio)
        duracion = (datetime.now() - inicio).total_seconds()
        
        # Condiciones de apagado
        if self.BatVoltage and self.BatVoltage < SHUTDOWN_VOLTAGE:
            logger.critical(f"🔋 BATERÍA CRÍTICA ({self.BatVoltage}V) - APAGANDO SISTEMA")
            if not self._bat_critica_avisada:
                self.buzzer_beep(4.0)
                self._bat_critica_avisada = True
            self.shutdown()

        elif duracion > SHUTDOWN_DELAY:
            logger.critical(f"⏱️ CORTE PROLONGADO ({duracion:.0f}s) - APAGANDO SISTEMA")
            self.shutdown()
    
    def shutdown(self):
        """Ejecuta apagado del host (el NAS)"""
        # En Docker, esto requiere privilegios especiales
        # Opción 1: Si el contenedor tiene acceso al host
        try:
            os.system("poweroff")
        except:
            logger.error("No se pudo ejecutar poweroff")
        
        # Opción 2: Crear archivo flag para que el host lo lea
        flag_file = Path('/app/data/SHUTDOWN_REQUESTED')
        flag_file.write_text(f"Shutdown requested at {datetime.now().isoformat()}")
        logger.info("Creado flag de apagado")
    
    def send_command(self, cmd: str) -> str:
        """Envía un comando raw al UPS y devuelve la respuesta como string."""
        if not self.device:
            return ""
        try:
            payload = cmd.encode('ascii') + b'\r'
            buf = payload + bytes(8 - len(payload))
            self.device.ctrl_transfer(0x21, 9, 0x0200, 0, buf)
            time.sleep(0.3)

            start = time.time()
            fragments = []
            while time.time() - start < 1.2:
                try:
                    data = self._ep_in.read(self._ep_in.wMaxPacketSize, timeout=100)
                    if data:
                        clean = bytes(b for b in data if b != 0)
                        if clean:
                            fragments.append(clean.decode('ascii', errors='ignore'))
                except usb.core.USBTimeoutError:
                    pass
                time.sleep(0.05)
            return ''.join(fragments).strip()
        except Exception as e:
            logger.error(f"Error enviando comando: {e}")
            return ""

    def _buzzer_toggle(self):
        self.send_command('Q')
        self._buzzer_on = not self._buzzer_on

    def buzzer_off(self):
        if self._buzzer_on:
            self._buzzer_toggle()

    def buzzer_on(self):
        if not self._buzzer_on:
            self._buzzer_toggle()

    def buzzer_beep(self, seconds: float = 2.0):
        self.buzzer_on()
        time.sleep(seconds)
        self.buzzer_off()

    def sync_buzzer_state(self):
        """Lee bit 7 del status_bits para sincronizar estado del buzzer."""
        if not self.data:
            return
        bits = self.data.get('status_bits', '')
        if len(bits) == 8:
            self._buzzer_on = (bits[7] == '1')

    def _atomic_write(self, path: Path, data: object):
        """Escribe JSON de forma atómica: escribe a .tmp y luego renombra."""
        dir_ = path.parent
        with tempfile.NamedTemporaryFile('w', dir=dir_, delete=False, suffix='.tmp') as tmp:
            json.dump(data, tmp, indent=2)
            tmp_path = tmp.name
        os.replace(tmp_path, path)

    def save_status(self):
        """Guarda estado actual en JSON"""
        if not self.data:
            return

        output = {
            **self.data,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'corte_en_curso': self._corte_actual is not None,
        }

        if self._corte_actual:
            inicio = datetime.fromisoformat(self._corte_actual.inicio)
            output['duracion_corte_seg'] = (datetime.now() - inicio).total_seconds()

        self._atomic_write(self.status_file, output)

    def save_events(self):
        """Guarda eventos en JSON"""
        eventos = [asdict(e) for e in self._eventos]
        if self._corte_actual:
            eventos.append(asdict(self._corte_actual))

        self._atomic_write(self.events_file, eventos)
    
    def _connect_with_backoff(self) -> bool:
        """Intenta conectar con backoff exponencial. Retorna False si se interrumpe."""
        delay = 10
        max_delay = 300  # tope de 5 minutos entre intentos
        attempt = 0
        while True:
            attempt += 1
            logger.info(f"Intento de conexión #{attempt}...")
            if self.connect():
                return True
            logger.error(f"Conexión fallida. Reintentando en {delay}s...")
            try:
                time.sleep(delay)
            except KeyboardInterrupt:
                return False
            delay = min(delay * 2, max_delay)

    def run(self):
        """Loop principal"""
        logger.info("Iniciando monitor UPS...")

        if not self._connect_with_backoff():
            logger.info("Detenido durante reconexión inicial.")
            return

        # Primera lectura: sincronizar y silenciar buzzer
        if self.read_data():
            self.sync_buzzer_state()
            self.buzzer_off()
            logger.info("Buzzer silenciado al arranque.")

        try:
            while True:
                if self.read_data():
                    self.check_events()
                    self.check_shutdown()
                    self.save_status()

                    status = "BAT" if self.OnBattery else "LINE"
                    logger.info(f"{status} | {self.InVoltage:.1f}V | "
                                f"Bat:{self.BatVoltage:.1f}V | Load:{self.LoadPercent}%")
                else:
                    logger.warning("Fallo lectura")
                    if not self.device:
                        logger.warning("Dispositivo desconectado — intentando reconectar...")
                        self.disconnect()
                        if not self._connect_with_backoff():
                            break

                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Detenido por usuario")
        finally:
            self.disconnect()

if __name__ == "__main__":
    monitor = UPSMonitor()
    monitor.run()