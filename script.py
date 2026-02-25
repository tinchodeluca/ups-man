import hid
import time
import json
import statistics
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class EventoCorte:
    """Registro de un corte de energía"""
    inicio: str
    fin: Optional[str] = None
    duracion_segundos: Optional[float] = None
    voltaje_inicial_bateria: float = 0.0
    voltaje_final_bateria: Optional[float] = None
    carga_promedio: float = 0.0

class VertivUPS:
    """
    Clase simple para leer UPS Vertiv.
    Solo expone propiedades, sin lógica de decisiones.
    """
    
    def __init__(self, vid: int = 0x0665, pid: int = 0x5161):
        self.vid = vid
        self.pid = pid
        self.device = None
        
        # Últimos valores leídos (accesibles como propiedades)
        self._data: Optional[Dict] = None
        self._timestamp: Optional[datetime] = None
        
        # Historial para estadísticas
        self._historial_tension_linea: List[float] = []
        self._historial_tension_bateria: List[float] = []
        self._max_historial = 1000  # Mantener últimos 1000 valores
        
        # Eventos de corte
        self._eventos_corte: List[EventoCorte] = []
        self._corte_actual: Optional[EventoCorte] = None
        
        # Archivo de persistencia
        self._json_file = Path("ups_status.json")
        self._eventos_file = Path("ups_eventos.json")
    
    # =========================================================================
    # PROPIEDADES PÚBLICAS (tu interfaz principal)
    # =========================================================================
    
    @property
    def InVoltage(self) -> Optional[float]:
        """Tensión de entrada (línea)"""
        return self._data.get('input_voltage') if self._data else None
    
    @property
    def OutVoltage(self) -> Optional[float]:
        """Tensión de salida"""
        return self._data.get('output_voltage') if self._data else None
    
    @property
    def BatVoltage(self) -> Optional[float]:
        """Tensión de batería"""
        return self._data.get('battery_voltage') if self._data else None
    
    @property
    def LoadPercent(self) -> Optional[int]:
        """Porcentaje de carga conectada"""
        return self._data.get('load_percent') if self._data else None
    
    @property
    def Frequency(self) -> Optional[float]:
        """Frecuencia en Hz"""
        return self._data.get('frequency') if self._data else None
    
    @property
    def Temperature(self) -> Optional[float]:
        """Temperatura interna (None si no disponible)"""
        return self._data.get('temperature') if self._data else None
    
    @property
    def OnBattery(self) -> bool:
        """True si está funcionando con batería"""
        if not self._data:
            return False
        return self._data.get('on_battery', False)
    
    @property
    def StatusBits(self) -> Optional[str]:
        """Bits de estado crudos"""
        return self._data.get('status_bits') if self._data else None
    
    @property
    def LastUpdate(self) -> Optional[datetime]:
        """Última vez que se actualizaron los datos"""
        return self._timestamp
    
    @property
    def IsConnected(self) -> bool:
        """True si hay conexión USB activa"""
        return self.device is not None
    
    # =========================================================================
    # ESTADÍSTICAS Y EVENTOS
    # =========================================================================
    
    @property
    def PromedioTensionLinea(self) -> Optional[float]:
        """Promedio de tensión de línea histórico"""
        if not self._historial_tension_linea:
            return None
        return statistics.mean(self._historial_tension_linea)
    
    @property
    def PromedioTensionBateria(self) -> Optional[float]:
        """Promedio de tensión de batería histórico"""
        if not self._historial_tension_bateria:
            return None
        return statistics.mean(self._historial_tension_bateria)
    
    @property
    def EventosCorte(self) -> List[EventoCorte]:
        """Lista de eventos de corte de energía"""
        return self._eventos_corte.copy()
    
    @property
    def CorteEnCurso(self) -> Optional[EventoCorte]:
        """Evento de corte actual si está en batería"""
        return self._corte_actual if self.OnBattery else None
    
    @property
    def DuracionCorteActual(self) -> Optional[float]:
        """Segundos desde que empezó el corte actual"""
        if not self._corte_actual or not self.OnBattery:
            return None
        inicio = datetime.fromisoformat(self._corte_actual.inicio)
        return (datetime.now() - inicio).total_seconds()
    
    # =========================================================================
    # MÉTODOS DE CONEXIÓN Y LECTURA
    # =========================================================================
    
    def connect(self) -> bool:
        """Conecta al UPS vía USB"""
        try:
            self.device = hid.device()
            self.device.open(self.vid, self.pid)
            self.device.set_nonblocking(True)
            return True
        except Exception as e:
            print(f"Error conectando: {e}")
            return False
    
    def disconnect(self):
        """Desconecta del UPS"""
        if self.device:
            self.device.close()
            self.device = None
    
    def refresh(self) -> bool:
        """
        Lee nuevos datos del UPS.
        Retorna True si pudo leer, False si falló.
        """
        if not self.device:
            return False
        
        try:
            # Enviar comando QS
            buf = bytes([0x00]) + b'QS\r' + bytes(64 - 4)
            self.device.write(buf)
            time.sleep(0.1)
            
            # Acumular respuesta
            response = self._accumulate_response(duration=1.2)
            data = self._parse_response(response)
            
            if not data:
                return False
            
            # Guardar datos
            self._data = data
            self._timestamp = datetime.now()
            
            # Actualizar historiales
            self._historial_tension_linea.append(data['input_voltage'])
            self._historial_tension_bateria.append(data['battery_voltage'])
            
            # Limitar tamaño de historial
            if len(self._historial_tension_linea) > self._max_historial:
                self._historial_tension_linea = self._historial_tension_linea[-self._max_historial:]
                self._historial_tension_bateria = self._historial_tension_bateria[-self._max_historial:]
            
            # Detectar eventos de corte
            self._gestionar_eventos_corte(data)
            
            # Guardar JSON
            self._guardar_json()
            
            return True
            
        except Exception as e:
            print(f"Error en refresh: {e}")
            return False
    
    def _accumulate_response(self, duration: float = 1.0) -> str:
        """Acumula fragmentos de respuesta USB"""
        start = time.time()
        fragments = []
        
        while time.time() - start < duration:
            data = self.device.read(64)
            if data:
                clean = bytes(b for b in data if b != 0)
                if clean:
                    fragments.append(clean.decode('ascii', errors='ignore'))
            time.sleep(0.05)
        
        text = ''.join(fragments)
        if text.startswith('QS'):
            text = text[2:].strip()
        return text
    
    def _parse_response(self, text: str) -> Optional[Dict]:
        """Parsea respuesta QS"""
        if not text or '(' not in text:
            return None
        
        try:
            start = text.find('(')
            parts = text[start+1:].strip().split()
            
            if len(parts) < 8:
                return None
            
            temp_str = parts[6]
            temperature = float(temp_str) if temp_str != '--.-' else None
            input_v = float(parts[0])
            
            return {
                'input_voltage': input_v,
                'fault_voltage': float(parts[1]),
                'output_voltage': float(parts[2]),
                'load_percent': int(parts[3]),
                'frequency': float(parts[4]),
                'battery_voltage': float(parts[5]),
                'temperature': temperature,
                'status_bits': parts[7],
                'on_battery': input_v < 100.0,
                'raw': text[:100]
            }
            
        except (ValueError, IndexError):
            return None
    
    def _gestionar_eventos_corte(self, data: Dict):
        """Gestiona el registro de eventos de corte de energía"""
        ahora = datetime.now().isoformat()
        en_bateria = data['on_battery']
        
        # Inicio de corte
        if en_bateria and not self._corte_actual:
            self._corte_actual = EventoCorte(
                inicio=ahora,
                voltaje_inicial_bateria=data['battery_voltage']
            )
            print(f"[EVENTO] Corte de energía detectado - Bat: {data['battery_voltage']}V")
        
        # Fin de corte
        elif not en_bateria and self._corte_actual:
            corte = self._corte_actual
            corte.fin = ahora
            corte.voltaje_final_bateria = data['battery_voltage']
            
            inicio = datetime.fromisoformat(corte.inicio)
            fin = datetime.fromisoformat(corte.fin)
            corte.duracion_segundos = (fin - inicio).total_seconds()
            
            # Calcular carga promedio durante el corte (aproximado)
            # Aquí podrías mejorar con historial detallado
            corte.carga_promedio = data['load_percent']
            
            self._eventos_corte.append(corte)
            self._corte_actual = None
            
            print(f"[EVENTO] Fin de corte - Duración: {corte.duracion_segundos:.1f}s")
            self._guardar_eventos()
    
    def _guardar_json(self):
        """Guarda estado actual en JSON"""
        if not self._data:
            return
        
        output = {
            **self._data,
            'timestamp': self._timestamp.isoformat() if self._timestamp else None,
            'promedio_tension_linea': self.PromedioTensionLinea,
            'promedio_tension_bateria': self.PromedioTensionBateria,
            'corte_en_curso': asdict(self._corte_actual) if self._corte_actual else None,
            'duracion_corte_actual_seg': self.DuracionCorteActual
        }
        
        with open(self._json_file, 'w') as f:
            json.dump(output, f, indent=2)
    
    def _guardar_eventos(self):
        """Guarda historial de eventos en JSON"""
        eventos_dict = [asdict(e) for e in self._eventos_corte]
        with open(self._eventos_file, 'w') as f:
            json.dump(eventos_dict, f, indent=2)
    
    # =========================================================================
    # UTILIDADES
    # =========================================================================
    
    def to_dict(self) -> Dict:
        """Retorna todos los datos actuales como diccionario"""
        return {
            'timestamp': self._timestamp.isoformat() if self._timestamp else None,
            'in_voltage': self.InVoltage,
            'out_voltage': self.OutVoltage,
            'bat_voltage': self.BatVoltage,
            'load_percent': self.LoadPercent,
            'frequency': self.Frequency,
            'temperature': self.Temperature,
            'on_battery': self.OnBattery,
            'status_bits': self.StatusBits,
            'promedio_linea': self.PromedioTensionLinea,
            'promedio_bateria': self.PromedioTensionBateria,
            'corte_en_curso': self.CorteEnCurso is not None,
            'duracion_corte_seg': self.DuracionCorteActual
        }
    
    def __str__(self) -> str:
        """Representación string simple"""
        if not self._data:
            return "UPS (sin datos)"
        
        icon = "🔋" if self.OnBattery else "⚡"
        return (f"{icon} {self.InVoltage:.1f}V | Bat:{self.BatVoltage:.1f}V | "
                f"Load:{self.LoadPercent}% | {'BATERÍA' if self.OnBattery else 'RED'}")


# =============================================================================
# EJEMPLO DE USO EN TU NAS (lógica de decisiones)
# =============================================================================

def main():
    ups = VertivUPS()
    
    if not ups.connect():
        print("No se pudo conectar al UPS")
        return
    
    print("UPS conectado. Propiedades disponibles:")
    print(f"  ups.InVoltage, ups.BatVoltage, ups.OnBattery, etc.\n")
    
    try:
        while True:
            # 1. Refrescar datos (lectura USB)
            if ups.refresh():
                
                # 2. TU LÓGICA DE DECISIONES (ejemplo)
                print(f"\n{ups}")  # Usa __str__
                
                # Ejemplo: detectar corte y enviar mail
                if ups.OnBattery:
                    if ups.DuracionCorteActual and ups.DuracionCorteActual > 60:
                        print(f"  [ALERTA] Corte prolongado: {ups.DuracionCorteActual:.0f}s")
                        # aquí: enviar_mail("Corte prolongado")
                    
                    if ups.BatVoltage < 12.0:
                        print(f"  [CRÍTICO] Batería baja: {ups.BatVoltage}V - Apagando...")
                        # aquí: apagar_nas()
                        # break
                
                # Ejemplo: estadísticas
                if len(ups.EventosCorte) > 0:
                    ultimo = ups.EventosCorte[-1]
                    print(f"  Último corte: {ultimo.duracion_segundos:.1f}s "
                          f"(de {ultimo.voltaje_inicial_bateria}V a {ultimo.voltaje_final_bateria}V)")
                
            else:
                print("Fallo lectura")
            
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\nDetenido.")
    finally:
        ups.disconnect()


if __name__ == "__main__":
    main()