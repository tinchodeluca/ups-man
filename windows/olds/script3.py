import hid
import time
import json
from datetime import datetime
from typing import Dict, Optional, Callable

class VertivUPS:
    def __init__(self, vid=0x0665, pid=0x5161):
        self.vid = vid
        self.pid = pid
        self.device = None
        self.last_state = None
        self.on_state_change: Optional[Callable] = None
        
    def connect(self) -> bool:
        try:
            self.device = hid.device()
            self.device.open(self.vid, self.pid)
            self.device.set_nonblocking(True)
            return True
        except Exception as e:
            print(f"Error conectando: {e}")
            return False
    
    def disconnect(self):
        if self.device:
            self.device.close()
    
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
        # Limpiar eco del comando
        if text.startswith('QS'):
            text = text[2:].strip()
        return text
    
    def _parse_data(self, text: str) -> Optional[Dict]:
        """
        Parsea respuesta QS completa.
        Formato: (VVV.V FFF.F OOO.O LLL FF.F BB.BB TT.T --.- SSSSSSSS
        
        Retorna dict con:
        - timestamp (ISO)
        - input_voltage (float)
        - fault_voltage (float) 
        - output_voltage (float)
        - load_percent (int)
        - frequency (float)
        - battery_voltage (float)
        - temperature (float|null)
        - status_bits (str)
        - on_battery (bool)
        - status_text (str)
        """
        if not text or '(' not in text:
            return None
        
        try:
            start = text.find('(')
            parts = text[start+1:].strip().split()
            
            if len(parts) < 8:
                return None
            
            # Parsear temperatura (puede ser --.-)
            temp_str = parts[6]
            temperature = float(temp_str) if temp_str != '--.-' else None
            
            # Determinar estado
            input_v = float(parts[0])
            on_battery = input_v < 100.0  # Si entrada < 100V, está en batería
            
            # Texto de estado básico
            status_text = "BATTERY" if on_battery else "LINE"
            
            return {
                'timestamp': datetime.now().isoformat(),
                'input_voltage': float(parts[0]),
                'fault_voltage': float(parts[1]),
                'output_voltage': float(parts[2]),
                'load_percent': int(parts[3]),
                'frequency': float(parts[4]),
                'battery_voltage': float(parts[5]),
                'temperature': temperature,
                'status_bits': parts[7],
                'on_battery': on_battery,
                'status_text': status_text,
                'raw': text[:100]
            }
            
        except (ValueError, IndexError) as e:
            print(f"Error parseando: {e}")
            return None
    
    def get_data_dict(self) -> Optional[Dict]:
        """
        Obtiene datos del UPS como diccionario limpio.
        Principal método para integraciones.
        """
        # Enviar comando QS
        buf = bytes([0x00]) + b'QS\r' + bytes(64 - 4)
        self.device.write(buf)
        time.sleep(0.1)
        
        # Leer respuesta
        response = self._accumulate_response(duration=1.2)
        data = self._parse_data(response)
        
        # Detectar cambio de estado
        if data and self.on_state_change:
            current_state = data['status_text']
            if self.last_state and self.last_state != current_state:
                self.on_state_change(self.last_state, current_state, data)
            self.last_state = current_state
        
        return data
    
    def monitor(self, interval: int = 5, callback: Optional[Callable] = None):
        """
        Monitoreo continuo.
        
        Args:
            interval: Segundos entre lecturas
            callback: Función(data_dict) llamada en cada lectura válida
        """
        print(f"{'='*70}")
        print("MONITOREO UPS - Dict Output")
        print(f"{'='*70}\n")
        
        try:
            while True:
                data = self.get_data_dict()
                
                if data:
                    # Mostrar en consola
                    icon = "🔋" if data['on_battery'] else "⚡"
                    temp_str = f"{data['temperature']}°C" if data['temperature'] else "N/A"
                    
                    print(f"{icon} [{data['timestamp'][11:19]}] "
                          f"In:{data['input_voltage']:05.1f}V | "
                          f"Out:{data['output_voltage']:05.1f}V | "
                          f"Load:{data['load_percent']:03d}% | "
                          f"Freq:{data['frequency']:04.1f}Hz | "
                          f"Bat:{data['battery_voltage']:04.1f}V | "
                          f"Temp:{temp_str} | "
                          f"{data['status_text']}")
                    
                    # Guardar JSON
                    with open('ups_status.json', 'w') as f:
                        json.dump(data, f, indent=2)
                    
                    # Llamar callback si existe
                    if callback:
                        callback(data)
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Sin datos")
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\nDetenido.")

# Ejemplo de uso avanzado
def on_state_change(old_state, new_state, data):
    """Callback cuando cambia de LINE a BATTERY o viceversa"""
    print(f"\n>>> CAMBIO DE ESTADO: {old_state} -> {new_state}")
    print(f"    Voltaje batería: {data['battery_voltage']}V")
    print(f"    Carga: {data['load_percent']}%\n")
    
    # Aquí podrías enviar email, webhook, etc.
    if new_state == "BATTERY":
        print("    [ALERTA] Corte de energía detectado!")
    else:
        print("    [INFO] Retornó la energía")

def main():
    ups = VertivUPS()
    
    if not ups.connect():
        return
    
    # Configurar callback de cambio de estado
    ups.on_state_change = on_state_change
    
    try:
        # Monitoreo con callback en cada lectura
        ups.monitor(interval=5, callback=lambda d: None)  # Callback vacío por ahora
    finally:
        ups.disconnect()

if __name__ == "__main__":
    main()