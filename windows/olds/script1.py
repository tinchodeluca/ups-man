import hid
import sys
import time

# =============================================================================
# CONFIGURACIÓN - REEMPLAZÁ CON TUS VALORES REALES
# =============================================================================
VID = 0x0665  # Ejemplo común en Vertiv, cambiar por el tuyo
PID = 0x5161  # Ejemplo común en Vertiv, cambiar por el tuyo

def listar_dispositivos():
    """Lista todos los dispositivos HID conectados"""
    print("=== DISPOSITIVOS HID ENCONTRADOS ===")
    for device in hid.enumerate():
        if device['vendor_id'] != 0:  # Filtrar dispositivos reales
            print(f"VID: {device['vendor_id']:04X} | PID: {device['product_id']:04X} | "
                  f"Fabricante: {device['manufacturer_string']} | "
                  f"Producto: {device['product_string']}")
    print()

def probar_hid_power_device(vid, pid):
    """Prueba protocolo HID Power Device estándar"""
    print(f"=== PROBANDO HID POWER DEVICE (VID:{vid:04X} PID:{pid:04X}) ===")
    
    try:
        device = hid.device()
        device.open(vid, pid)
        device.set_nonblocking(True)
        
        print("✓ Conectado al dispositivo")
        
        # Intentar leer Feature Reports comunes en UPS
        # Report ID 0x01: General status
        # Report ID 0x02: Battery status  
        # Report ID 0x03: Power status
        
        for report_id in [0x00, 0x01, 0x02, 0x03, 0x10]:
            try:
                print(f"\nIntentando Feature Report ID {report_id}...")
                data = device.get_feature_report(report_id, 64)
                if data:
                    print(f"  ✓ Datos recibidos ({len(data)} bytes): {data[:20]}...")
                    print(f"  Hex: {[hex(b) for b in data[:10]]}")
                    
                    # Intentar parsear como HID Power Device
                    if len(data) > 2:
                        # Byte 0 usualmente es Report ID
                        # Byte 1 puede ser capacidad de batería (0-100)
                        if 0 <= data[1] <= 100:
                            print(f"  Posible carga batería: {data[1]}%")
            except Exception as e:
                print(f"  ✗ Error: {e}")
        
        # Intentar leer Input Report (datos que envía el dispositivo solo)
        print(f"\nEsperando Input Report (5 segundos)...")
        time.sleep(0.5)
        data = device.read(64)
        if data:
            print(f"  ✓ Input recibido: {data[:20]}")
        else:
            print("  (No hay datos disponibles - esto es normal si el UPS no envía eventos)")
            
        device.close()
        return True
        
    except Exception as e:
        print(f"✗ Error al conectar: {e}")
        return False

def probar_voltronic(vid, pid):
    """Prueba protocolo Voltronic-QS (común en Vertiv/Liebert)"""
    print(f"\n=== PROBANDO PROTOCOLO VOLTRONIC-QS (VID:{vid:04X} PID:{pid:04X}) ===")
    
    try:
        device = hid.device()
        device.open(vid, pid)
        
        print("✓ Conectado")
        
        # Comandos Voltronic comunes
        comandos = [
            b'Q1\r',      # Status query
            b'QS\r',      # Quick status
            b'QPI\r',     # Protocol ID
            b'QID\r',     # Device ID
            b'QVFW\r',    # Firmware version
        ]
        
        for cmd in comandos:
            try:
                print(f"\nEnviando: {cmd}")
                # Enviar comando (algunos necesitan Report ID 0 al inicio)
                buf = bytes([0x00]) + cmd + bytes(64 - len(cmd) - 1)
                device.write(buf)
                
                time.sleep(0.5)
                resp = device.read(64)
                
                if resp:
                    # Limpiar ceros y decodificar
                    clean = bytes(b for b in resp if b != 0)
                    print(f"  Respuesta: {clean}")
                    try:
                        text = clean.decode('ascii')
                        print(f"  Como texto: {text}")
                    except:
                        pass
                else:
                    print("  (Sin respuesta)")
                    
            except Exception as e:
                print(f"  Error: {e}")
        
        device.close()
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def probar_raw_usb(vid, pid):
    """Prueba lectura raw sin protocolo específico"""
    print(f"\n=== PROBANDO LECTURA RAW ===")
    
    try:
        device = hid.device()
        device.open(vid, pid)
        device.set_nonblocking(False)
        
        print("Leyendo 64 bytes...")
        data = device.read(64)
        if data:
            print(f"Bytes: {data}")
            print(f"Hex: {[hex(b) for b in data]}")
            
            # Análisis básico
            if any(b != 0 for b in data):
                print("\nAnálisis:")
                for i, b in enumerate(data[:10]):
                    if b != 0:
                        print(f"  Byte {i}: {b} (0x{b:02X})")
        else:
            print("No se recibieron datos")
            
        device.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("DIAGNÓSTICO UPS VERTIV PSL650\n")
    
    # Si pasás argumentos, usalos
    if len(sys.argv) >= 3:
        VID = int(sys.argv[1], 16)
        PID = int(sys.argv[2], 16)
    
    listar_dispositivos()
    
    print(f"Probando con VID={VID:04X}, PID={PID:04X}")
    print("(Si estos no son correctos, pasá los tuyos: python ups_test.py 0x1234 0x5678)\n")
    
    # Probar ambos protocolos
    probar_hid_power_device(VID, PID)
    probar_voltronic(VID, PID)
    probar_raw_usb(VID, PID)
    
    print("\n=== DIAGNÓSTICO COMPLETADO ===")