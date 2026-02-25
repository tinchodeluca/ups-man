import hid
import time
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/ups.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Config desde variables de entorno
VID = int(os.getenv('UPS_VID', '0x0665'), 16)
PID = int(os.getenv('UPS_PID', '0x5161'), 16)
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '10'))
SHUTDOWN_VOLTAGE = float(os.getenv('SHUTDOWN_VOLTAGE', '11.0'))
SHUTDOWN_DELAY = int(os.getenv('SHUTDOWN_DELAY', '300'))  # 5 minutos

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
        self.data: Optional[Dict] = None
        self.timestamp: Optional[datetime] = None
        self._corte_actual: Optional[EventoCorte] = None
        self._eventos: List[EventoCorte] = []
        self._historial_bat: List[float] = []
        
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
            self.device = hid.device()
            self.device.open(VID, PID)
            self.device.set_nonblocking(True)
            logger.info(f"UPS conectado VID:{VID:04X} PID:{PID:04X}")
            return True
        except Exception as e:
            logger.error(f"Error conectando: {e}")
            return False
    
    def disconnect(self):
        if self.device:
            self.device.close()
            self.device = None
    
    def read_data(self) -> bool:
        """Lee datos del UPS"""
        if not self.device:
            return False
        
        try:
            # Enviar QS
            buf = bytes([0x00]) + b'QS\r' + bytes(64 - 4)
            self.device.write(buf)
            time.sleep(0.1)
            
            # Acumular respuesta
            start = time.time()
            fragments = []
            while time.time() - start < 1.2:
                data = self.device.read(64)
                if data:
                    clean = bytes(b for b in data if b != 0)
                    if clean:
                        fragments.append(clean.decode('ascii', errors='ignore'))
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
            input_v = float(parts[0])
            
            self.data = {
                'input_voltage': input_v,
                'output_voltage': float(parts[2]),
                'load_percent': int(parts[3]),
                'frequency': float(parts[4]),
                'battery_voltage': float(parts[5]),
                'temperature': float(temp_str) if temp_str != '--.-' else None,
                'status_bits': parts[7],
                'on_battery': input_v < 100.0,
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
        
        # Fin corte
        elif not en_bateria and self._corte_actual:
            corte = self._corte_actual
            corte.fin = ahora
            corte.voltaje_final_bateria = self.BatVoltage
            
            inicio = datetime.fromisoformat(corte.inicio)
            fin = datetime.fromisoformat(corte.fin)
            corte.duracion_segundos = (fin - inicio).total_seconds()
            
            self._eventos.append(corte)
            self._corte_actual = None
            
            logger.info(f"✅ Retornó energía - Duración: {corte.duracion_segundos:.0f}s")
            self.save_events()
    
    def check_shutdown(self):
        """Verifica si debe apagar el sistema"""
        if not self.OnBattery or not self._corte_actual:
            return
        
        # Calcular duración
        inicio = datetime.fromisoformat(self._corte_actual.inicio)
        duracion = (datetime.now() - inicio).total_seconds()
        
        # Condiciones de apagado
        if self.BatVoltage and self.BatVoltage < SHUTDOWN_VOLTAGE:
            logger.critical(f"🔋 BATERÍA CRÍTICA ({self.BatVoltage}V) - APAGANDO SISTEMA")
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
        
        with open(self.status_file, 'w') as f:
            json.dump(output, f, indent=2)
    
    def save_events(self):
        """Guarda eventos en JSON"""
        eventos = [asdict(e) for e in self._eventos]
        if self._corte_actual:
            eventos.append(asdict(self._corte_actual))
        
        with open(self.events_file, 'w') as f:
            json.dump(eventos, f, indent=2)
    
    def run(self):
        """Loop principal"""
        logger.info("Iniciando monitor UPS...")
        
        if not self.connect():
            logger.error("No se pudo conectar. Reintentando en 30s...")
            time.sleep(30)
            return self.run()
        
        try:
            while True:
                if self.read_data():
                    self.check_events()
                    self.check_shutdown()
                    self.save_status()
                    
                    # Log resumen
                    status = "BAT" if self.OnBattery else "LINE"
                    logger.info(f"{status} | {self.InVoltage:.1f}V | "
                              f"Bat:{self.BatVoltage:.1f}V | Load:{self.LoadPercent}%")
                else:
                    logger.warning("Fallo lectura")
                    # Reconectar si es necesario
                    if not self.device:
                        self.connect()
                
                time.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            logger.info("Detenido por usuario")
        finally:
            self.disconnect()

if __name__ == "__main__":
    monitor = UPSMonitor()
    monitor.run()