# core/esp32_manager.py
# Gestor de dispositivos ESP32 - Vinculación y comunicación
import asyncio
import json
import time
import random
import string
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from pathlib import Path

class ESP32Device:
    """Representa un dispositivo ESP32 conectado"""
    def __init__(self, device_id: str, websocket):
        self.device_id = device_id
        self.websocket = websocket
        self.user_id: Optional[str] = None
        self.authenticated = False
        self.last_heartbeat = datetime.now()
        self.is_playing = False
        self.is_recording = False
        self.volume = 50
        self.connected_at = datetime.now()
    
    def update_heartbeat(self):
        """Actualiza el timestamp del último heartbeat"""
        self.last_heartbeat = datetime.now()
    
    def is_online(self) -> bool:
        """Verifica si el dispositivo sigue conectado (heartbeat reciente)"""
        return (datetime.now() - self.last_heartbeat).total_seconds() < 60


class ESP32Manager:
    """Gestor de dispositivos ESP32"""
    
    def __init__(self):
        self.devices: Dict[str, ESP32Device] = {}
        self.pairing_codes: Dict[str, Dict] = {}
        self.config_path = Path("config/esp32_devices.json")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_devices()
    
    def _load_devices(self):
        """Carga dispositivos guardados desde archivo"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    # Solo cargar datos de configuración, no websockets
                    print(f"[ESP32Manager] Cargados {len(data)} dispositivos guardados")
            except Exception as e:
                print(f"[ESP32Manager] Error cargando dispositivos: {e}")
    
    def _save_devices(self):
        """Guarda dispositivos en archivo"""
        try:
            data = {}
            for device_id, device in self.devices.items():
                if device.user_id:
                    data[device_id] = {
                        "user_id": device.user_id,
                        "authenticated": device.authenticated,
                        "last_seen": device.last_heartbeat.isoformat()
                    }
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[ESP32Manager] Error guardando dispositivos: {e}")
    
    def generate_pairing_code(self, user_id: str) -> str:
        """Genera un código de vinculación para un usuario"""
        # Generar código de 6 caracteres alfanuméricos
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Guardar con timestamp
        self.pairing_codes[code] = {
            "user_id": user_id,
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(minutes=10)
        }
        
        # Limpiar códigos expirados
        self._clean_expired_codes()
        
        return code
    
    def verify_pairing_code(self, code: str, device_id: str) -> Optional[str]:
        """Verifica un código de vinculación y retorna el user_id"""
        code = code.upper().strip()
        
        if code not in self.pairing_codes:
            return None
        
        pairing = self.pairing_codes[code]
        
        # Verificar expiración
        if datetime.now() > pairing["expires_at"]:
            del self.pairing_codes[code]
            return None
        
        user_id = pairing["user_id"]
        
        # Eliminar código después de usarlo (un solo uso)
        del self.pairing_codes[code]
        
        return user_id
    
    def _clean_expired_codes(self):
        """Elimina códigos expirados"""
        now = datetime.now()
        expired = [code for code, data in self.pairing_codes.items() if now > data["expires_at"]]
        for code in expired:
            del self.pairing_codes[code]
    
    def register_device(self, device_id: str, websocket) -> ESP32Device:
        """Registra un nuevo dispositivo o actualiza uno existente"""
        # Si el dispositivo ya existe, actualizarlo
        if device_id in self.devices:
            device = self.devices[device_id]
            device.websocket = websocket
            device.update_heartbeat()
            print(f"[ESP32Manager] Dispositivo {device_id} reconectado")
            return device
        
        # Crear nuevo dispositivo
        device = ESP32Device(device_id, websocket)
        self.devices[device_id] = device
        print(f"[ESP32Manager] Dispositivo {device_id} registrado")
        return device
    
    def unregister_device(self, device_id: str):
        """Elimina un dispositivo"""
        if device_id in self.devices:
            del self.devices[device_id]
            print(f"[ESP32Manager] Dispositivo {device_id} eliminado")
    
    def link_device_to_user(self, device_id: str, user_id: str):
        """Vincula un dispositivo a un usuario"""
        if device_id in self.devices:
            device = self.devices[device_id]
            device.user_id = user_id
            device.authenticated = True
            self._save_devices()
            print(f"[ESP32Manager] Dispositivo {device_id} vinculado a usuario {user_id}")
    
    def get_device_by_user(self, user_id: str) -> Optional[ESP32Device]:
        """Obtiene el dispositivo vinculado a un usuario"""
        for device in self.devices.values():
            if device.user_id == user_id and device.is_online():
                return device
        return None
    
    def get_connected_devices(self) -> List[Dict]:
        """Devuelve lista de dispositivos conectados"""
        result = []
        for device_id, device in self.devices.items():
            result.append({
                "device_id": device_id,
                "user_id": device.user_id,
                "authenticated": device.authenticated,
                "is_online": device.is_online(),
                "is_playing": device.is_playing,
                "is_recording": device.is_recording,
                "volume": device.volume,
                "connected_at": device.connected_at.isoformat()
            })
        return result
    
    def get_connected_count(self) -> int:
        """Devuelve el número de dispositivos conectados"""
        return len(self.devices)
    
    def get_authenticated_count(self) -> int:
        """Devuelve el número de dispositivos autenticados"""
        return sum(1 for device in self.devices.values() if device.authenticated)
    
    async def send_proactive_message(self, user_id: str, text: str, audio_base64: str = None) -> bool:
        """Envía un mensaje proactivo al ESP32 de un usuario"""
        device = self.get_device_by_user(user_id)
        if not device:
            return False
        
        try:
            message = {
                "type": "proactive",
                "text": text,
                "timestamp": datetime.now().isoformat()
            }
            if audio_base64:
                message["audio"] = audio_base64
            
            await device.websocket.send_json(message)
            return True
        except Exception as e:
            print(f"[ESP32Manager] Error enviando mensaje: {e}")
            return False
    
    async def start_cleanup_loop(self, interval_seconds: int = 30):
        """Limpia dispositivos inactivos periódicamente"""
        while True:
            await asyncio.sleep(interval_seconds)
            now = datetime.now()
            to_remove = []
            
            for device_id, device in self.devices.items():
                if not device.is_online():
                    to_remove.append(device_id)
            
            for device_id in to_remove:
                del self.devices[device_id]
                print(f"[ESP32Manager] Dispositivo {device_id} eliminado por inactividad")


# Instancia global
esp32_manager = ESP32Manager()