import hid
import time
from datetime import datetime

class VertivUPS:
    def __init__(self, vid=0x0665, pid=0x5161):
        self.vid = vid
        self.pid = pid
        self.device = None
        self.on_battery = False
        
    def connect(self):
        try:
            self.device = hid.device()
            self.device.open(self.vid, self.pid)
            self.device.set_nonblocking(True)
            print(f"✓ Conectado a UPS Vertiv PSL650")
            print(f"  Probá desenchufar para ver el cambio a batería...\n")
            return True
        except Exception as e:
            print(f"✗ Error: {e}")
            return False
    
    def disconnect(self):
        if self.device:
            self.device.close()
    
    def flush(self):
        """Limpia buffer"""
        for _ in range(10):
            if not self.device.read(64):
                break
    
    def read_once(self, timeout=1.0):
        """Lee una vez con timeout"""
        start = time.time()
        while time.time() - start < timeout:
            data = self.device.read(64)
            if data:
                clean = bytes(b for b in data if b != 0)
                text = clean.decode('ascii', errors='ignore').strip()
                # Remover eco
                for cmd in ['Q1', 'QS', 'QPI']:
                    if text.startswith(cmd):
                        text = text[len(cmd):].strip()
                return text
            time.sleep(0.05)
        return None
    
    def send(self, cmd, wait=0.8):
        self.flush()
        buf = bytes([0x00]) + cmd + bytes(64 - len(cmd) - 1)
        self.device.write(buf)
        time.sleep(wait)
        return self.read_once()
    
    def get_q1_detailed(self):
        """Intenta obtener Q1 con múltiples intentos"""
        # Intentar con diferentes tiempos de espera
        for wait in [1.0, 1.5, 2.0]:
            resp = self.send(b'Q1\r', wait)
            if resp and resp.startswith('(') and len(resp) > 20:
                try:
                    parts = resp[1:].split()
                    if len(parts) >= 8:
                        return {
                            'input_v': float(parts[0]),
                            'output_v': float(parts[2]),
                            'load': int(parts[3]),
                            'freq': float(parts[4]),
                            'battery_v': float(parts[5]),
                            'temp': float(parts[6]),
                            'status': parts[7],
                            'raw': resp
                        }
                except:
                    pass
        return None
    
    def get_qs_simple(self):
        """QS simple pero confiable"""
        resp = self.send(b'QS\r', 0.6)
        if resp and resp.startswith('('):
            try:
                parts = resp[1:].split()
                return {
                    'input_v': float(parts[0]),
                    'load': int(parts[1]) if len(parts) > 1 else 0,
                    'raw': resp
                }
            except:
                pass
        return None
    
    def check_battery_mode(self, input_v):
        """Detecta si está en batería por voltaje de entrada"""
        # Si el voltaje de entrada es < 50V, probablemente esté en batería
        # o en modo bypass/falla
        return input_v < 50.0
    
    def monitor(self, interval=4):
        print(f"{'='*65}")
        print("MONITOREO EN TIEMPO REAL")
        print(f"{'='*65}")
        
        last_input = 0
        last_state = "RED"
        
        try:
            while True:
                now = datetime.now().strftime("%H:%M:%S")
                
                # Intentar Q1 primero
                data = self.get_q1_detailed()
                
                if data:
                    # Detectar cambio a batería
                    current_state = "BATERÍA" if self.check_battery_mode(data['input_v']) else "RED"
                    
                    if current_state != last_state:
                        print(f"\n*** CAMBIO: {last_state} → {current_state} ***")
                        if current_state == "BATERÍA":
                            print(f"    Voltaje batería: {data['battery_v']}V")
                            print(f"    Tiempo restante estimado: ~{self.estimate_time(data['battery_v'])} min")
                        print()
                        last_state = current_state
                    
                    status_icon = "🔋" if current_state == "BATERÍA" else "⚡"
                    print(f"{status_icon} [{now}] {data['input_v']:05.1f}V → {data['output_v']:05.1f}V | "
                          f"Load:{data['load']:02d}% | Bat:{data['battery_v']:04.1f}V | "
                          f"{data['temp']:04.1f}°C | Status:{data['status']}")
                    
                else:
                    # Fallback a QS
                    data = self.get_qs_simple()
                    if data:
                        current_state = "BATERÍA" if self.check_battery_mode(data['input_v']) else "RED"
                        
                        if current_state != last_state:
                            print(f"\n*** CAMBIO: {last_state} → {current_state} ***\n")
                            last_state = current_state
                        
                        status_icon = "🔋" if current_state == "BATERÍA" else "⚡"
                        print(f"{status_icon} [{now}] {data['input_v']:05.1f}V | Load:{data['load']:02d}% "
                              f"[{current_state}]")
                    else:
                        print(f"[{now}] ---")
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\nDetenido.")
    
    def estimate_time(self, battery_v):
        """Estimación muy básica de tiempo restante según voltaje de batería"""
        # Asumiendo batería 12V: 13.5V=100%, 12.0V=50%, 10.5V=0%
        if battery_v >= 13.0:
            return "20+"
        elif battery_v >= 12.5:
            return "15-20"
        elif battery_v >= 12.0:
            return "10-15"
        elif battery_v >= 11.5:
            return "5-10"
        else:
            return "<5"

if __name__ == "__main__":
    ups = VertivUPS()
    if ups.connect():
        try:
            ups.monitor(interval=4)
        finally:
            ups.disconnect()