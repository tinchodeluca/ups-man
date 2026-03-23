import hid
import time
import json
import os
import sys
import statistics
import tempfile
from datetime import datetime
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

        # Buzzer: estado trackeado por software
        # El PSL650 no da ACK en Q, así que mantenemos estado propio.
        # bit 7 del status_bits puede reflejarlo, pero no es fiable en todos los modelos.
        self._buzzer_on: bool = False

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
            
            temp_str    = parts[6]
            temperature = float(temp_str) if temp_str not in ('--.-', '---.-', 'N/A') else None
            input_v     = float(parts[0])
            output_v    = float(parts[2])
            load_pct    = int(parts[3])
            frequency   = float(parts[4])
            battery_v   = float(parts[5])

            # Validar rangos antes de aceptar la lectura
            if not (0.0 <= input_v <= 300.0):
                print(f"[WARN] input_voltage fuera de rango: {input_v}V — descartando")
                return None
            if not (0.0 <= output_v <= 300.0):
                print(f"[WARN] output_voltage fuera de rango: {output_v}V — descartando")
                return None
            if not (0 <= load_pct <= 100):
                print(f"[WARN] load_percent fuera de rango: {load_pct}% — descartando")
                return None
            if not (40.0 <= frequency <= 70.0):
                print(f"[WARN] frequency fuera de rango: {frequency}Hz — descartando")
                return None
            if not (0.0 <= battery_v <= 30.0):
                print(f"[WARN] battery_voltage fuera de rango: {battery_v}V — descartando")
                return None

            return {
                'input_voltage'  : input_v,
                'fault_voltage'  : float(parts[1]),
                'output_voltage' : output_v,
                'load_percent'   : load_pct,
                'frequency'      : frequency,
                'battery_voltage': battery_v,
                'temperature'    : temperature,
                'status_bits'    : parts[7],
                'on_battery'     : input_v < 100.0,
                'raw'            : text[:100]
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
            # 2 beeps cortos para avisar el corte
            self.buzzer_beep(1.0)
            time.sleep(0.3)
            self.buzzer_beep(1.0)

        # Fin de corte
        elif not en_bateria and self._corte_actual:
            corte = self._corte_actual
            corte.fin = ahora
            corte.voltaje_final_bateria = data['battery_voltage']

            inicio = datetime.fromisoformat(corte.inicio)
            fin = datetime.fromisoformat(corte.fin)
            corte.duracion_segundos = (fin - inicio).total_seconds()

            corte.carga_promedio = data['load_percent']

            self._eventos_corte.append(corte)
            self._corte_actual = None

            print(f"[EVENTO] Fin de corte - Duración: {corte.duracion_segundos:.1f}s")
            self._guardar_eventos()
            # 1 beep corto de confirmación: volvió la energía
            self.buzzer_beep(0.5)
    
    def _atomic_write(self, path: Path, data: object):
        """Escribe JSON de forma atómica: escribe a .tmp y luego renombra."""
        dir_ = path.parent
        with tempfile.NamedTemporaryFile('w', dir=dir_, delete=False, suffix='.tmp') as tmp:
            json.dump(data, tmp, indent=2)
            tmp_path = tmp.name
        os.replace(tmp_path, path)

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

        self._atomic_write(self._json_file, output)

    def _guardar_eventos(self):
        """Guarda historial de eventos en JSON"""
        eventos_dict = [asdict(e) for e in self._eventos_corte]
        self._atomic_write(self._eventos_file, eventos_dict)
    
    # =========================================================================
    # COMANDOS
    # =========================================================================

    def send_command(self, cmd: str) -> str:
        """Envía un comando raw al UPS y devuelve la respuesta como string."""
        if not self.device:
            return ""
        try:
            payload = cmd.encode('ascii') + b'\r'
            buf = bytes([0x00]) + payload + bytes(64 - len(payload))
            self.device.write(buf)
            time.sleep(0.3)

            start = time.time()
            fragments = []
            while time.time() - start < 1.2:
                data = self.device.read(64)
                if data:
                    clean = bytes(b for b in data if b != 0)
                    if clean:
                        fragments.append(clean.decode('ascii', errors='ignore'))
                time.sleep(0.05)
            return ''.join(fragments).strip()
        except Exception as e:
            print(f"Error enviando comando: {e}")
            return ""

    def _buzzer_toggle(self):
        """Envía Q y actualiza el estado interno."""
        self.send_command('Q')
        self._buzzer_on = not self._buzzer_on

    def buzzer_off(self):
        if self._buzzer_on:
            self._buzzer_toggle()

    def buzzer_on(self):
        if not self._buzzer_on:
            self._buzzer_toggle()

    def buzzer_beep(self, seconds: float = 2.0):
        """Prende el buzzer, espera, lo apaga."""
        self.buzzer_on()
        time.sleep(seconds)
        self.buzzer_off()

    def sync_buzzer_state(self):
        """
        Sincroniza el estado del buzzer con el hardware usando el bit 7
        del status_bits. Si no está disponible, asume off.
        Llamar una vez después del primer refresh() exitoso.
        """
        if not self._data:
            return
        bits = self._data.get('status_bits', '')
        if len(bits) == 8:
            self._buzzer_on = (bits[7] == '1')
        # Si el bit no es fiable en este modelo, _buzzer_on queda en False
        # y el primer buzzer_off() no mandará Q innecesariamente.

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

def _connect_with_backoff(ups: VertivUPS) -> bool:
    """Intenta conectar con backoff exponencial. Retorna False si se interrumpe."""
    delay = 10
    max_delay = 300
    attempt = 0
    while True:
        attempt += 1
        print(f"Intento de conexión #{attempt}...")
        if ups.connect():
            print("UPS conectado.")
            return True
        print(f"Conexión fallida. Reintentando en {delay}s...")
        try:
            time.sleep(delay)
        except KeyboardInterrupt:
            return False
        delay = min(delay * 2, max_delay)


def main():
    ups = VertivUPS()

    if not _connect_with_backoff(ups):
        print("\nDetenido durante conexión inicial.")
        return

    # Primera lectura: sincronizar estado del buzzer y silenciarlo
    if ups.refresh():
        ups.sync_buzzer_state()
        ups.buzzer_off()
        print(f"Buzzer {'apagado' if not ups._buzzer_on else 'ya estaba apagado'}.")

    print("Propiedades disponibles: ups.InVoltage, ups.BatVoltage, ups.OnBattery, etc.\n")

    _bat_critica_avisada = False  # evitar beep repetido en cada ciclo

    try:
        while True:
            if ups.refresh():
                print(f"\n{ups}")

                if ups.OnBattery:
                    if ups.DuracionCorteActual and ups.DuracionCorteActual > 60:
                        print(f"  [ALERTA] Corte prolongado: {ups.DuracionCorteActual:.0f}s")
                        # aquí: enviar_mail("Corte prolongado")

                    if ups.BatVoltage and ups.BatVoltage < 12.0:
                        print(f"  [CRÍTICO] Batería baja: {ups.BatVoltage}V - Apagando...")
                        if not _bat_critica_avisada:
                            ups.buzzer_beep(4.0)  # beep largo en batería crítica
                            _bat_critica_avisada = True
                        # aquí: apagar_nas()
                        # break
                else:
                    _bat_critica_avisada = False  # reset si volvió la energía

                if ups.EventosCorte:
                    ultimo = ups.EventosCorte[-1]
                    print(f"  Último corte: {ultimo.duracion_segundos:.1f}s "
                          f"(de {ultimo.voltaje_inicial_bateria}V a {ultimo.voltaje_final_bateria}V)")

            else:
                print("Fallo lectura")
                if not ups.IsConnected:
                    print("Dispositivo desconectado — intentando reconectar...")
                    ups.disconnect()
                    if not _connect_with_backoff(ups):
                        break

            time.sleep(5)

    except KeyboardInterrupt:
        print("\nDetenido.")
    finally:
        ups.disconnect()


_CLI_HELP = """
Comandos conocidos:
  qs          Query status (parseado)
  f           Rating info (voltaje nominal, corriente, batería)
  i           Manufacturer info (modelo, firmware)
  q           Toggle buzzer
  pda         Deshabilitar alarma permanentemente
  pea         Rehabilitar alarma
  t           Self-test 10 segundos
  tl          Self-test hasta batería baja
  c           Cancelar shutdown/test
  s<n>        Shutdown en n×6s  (ej: s10 = 60s)
  s<n>r<m>    Shutdown + restore (ej: s10r0020)
  psdv<vv.v>  Set low battery voltage (ej: psdv11.0)
  raw <cmd>   Enviar cualquier comando custom
  help        Mostrar esta ayuda
  quit / q!   Salir
"""

def cli_mode():
    """CLI interactivo para explorar comandos del UPS."""
    ups = VertivUPS()

    print("=== UPS CLI ===")
    print(f"Conectando a VID:{ups.vid:04X} PID:{ups.pid:04X}...")

    if not ups.connect():
        print("No se pudo conectar al UPS.")
        return

    print("Conectado. Escribí 'help' para ver los comandos.\n")

    while True:
        try:
            line = input("ups> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            break

        if not line:
            continue

        if line in ('quit', 'q!', 'exit'):
            break

        if line == 'help':
            print(_CLI_HELP)
            continue

        # Comando QS con parseo bonito
        if line == 'qs':
            if ups.refresh():
                print(f"  Input voltage  : {ups.InVoltage} V")
                print(f"  Output voltage : {ups.OutVoltage} V")
                print(f"  Battery voltage: {ups.BatVoltage} V")
                print(f"  Load           : {ups.LoadPercent} %")
                print(f"  Frequency      : {ups.Frequency} Hz")
                print(f"  Temperature    : {ups.Temperature}")
                print(f"  Status bits    : {ups.StatusBits}")
                print(f"  On battery     : {ups.OnBattery}")
            else:
                print("  Sin respuesta o datos fuera de rango.")
            continue

        # Comando raw explícito
        if line.startswith('raw '):
            cmd = line[4:].strip()
        else:
            cmd = line.upper()  # el protocolo espera mayúsculas

        if not cmd:
            continue

        print(f"  → enviando: {repr(cmd)}")
        resp = ups.send_command(cmd)
        if resp:
            print(f"  ← respuesta: {repr(resp)}")
        else:
            print("  ← sin respuesta (comando no soportado o sin ACK)")

    ups.disconnect()
    print("Desconectado.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'cli':
        cli_mode()
    else:
        main()