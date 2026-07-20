# core/esp32_manager.py
# Gestor de dispositivos ESP32 - Vinculación y comunicación
#
# CAMBIOS CLAVE respecto a la versión anterior:
# 1. Ya no se crea un dict plano en self.devices al hacer pairing por HTTP.
#    Ahora TODO dispositivo es siempre un objeto ESP32Device, tenga o no
#    WebSocket abierto. Esto es lo que rompía get_device_by_user() y por
#    lo tanto send_proactive_message() (fallaba con AttributeError o
#    simplemente nunca encontraba el dispositivo).
# 2. Se separa "autorizado" (el código de pairing fue verificado, sabemos
#    a qué user_id pertenece) de "online" (hay un WebSocket vivo con
#    heartbeat reciente). El panel web ahora puede confiar en is_online()
#    real en vez de un valor congelado en True para siempre.
# 3. authorize_device() es el nuevo punto de entrada para el pairing HTTP.
#    register_device() (WebSocket) ahora reutiliza el mismo objeto si ya
#    fue autorizado por HTTP, en vez de crear una entrada duplicada.

import asyncio
import json
import random
import string
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from pathlib import Path


class ESP32Device:
    """Representa un dispositivo ESP32 (autorizado y/o conectado por WebSocket)."""

    def __init__(self, device_id: str, websocket=None):
        self.device_id = device_id
        self.websocket = websocket
        self.user_id: Optional[str] = None
        self.authenticated = False          # el pairing (código) fue verificado
        self.last_heartbeat = datetime.now()
        self.is_playing = False
        self.is_recording = False
        self.volume = 50
        self.connected_at = datetime.now()

    def update_heartbeat(self):
        self.last_heartbeat = datetime.now()

    def is_online(self) -> bool:
        """
        Online de verdad = tiene un websocket activo y mandó heartbeat
        hace menos de 60s. Si nunca abrió WebSocket (solo pairing HTTP),
        NO se considera online aunque esté autenticado.
        """
        if self.websocket is None:
            return False
        return (datetime.now() - self.last_heartbeat).total_seconds() < 60

    def to_public_dict(self) -> Dict:
        return {
            "device_id": self.device_id,
            "user_id": self.user_id,
            "authenticated": self.authenticated,
            "is_online": self.is_online(),
            "is_playing": self.is_playing,
            "is_recording": self.is_recording,
            "volume": self.volume,
            "connected_at": self.connected_at.isoformat(),
        }


class ESP32Manager:
    """Gestor de dispositivos ESP32"""

    def __init__(self):
        self.devices: Dict[str, ESP32Device] = {}
        self.pairing_codes: Dict[str, Dict] = {}
        self.config_path = Path("config/esp32_devices.json")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_devices()

    # ------------------------------------------------------------------
    # Persistencia simple (solo metadatos, no websockets)
    # ------------------------------------------------------------------
    def _load_devices(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                for device_id, info in data.items():
                    dev = ESP32Device(device_id)
                    dev.user_id = info.get("user_id")
                    dev.authenticated = info.get("authenticated", False)
                    self.devices[device_id] = dev
                print(f"[ESP32Manager] Cargados {len(data)} dispositivos guardados")
            except Exception as e:
                print(f"[ESP32Manager] Error cargando dispositivos: {e}")

    def _save_devices(self):
        try:
            data = {}
            for device_id, device in self.devices.items():
                if device.user_id:
                    data[device_id] = {
                        "user_id": device.user_id,
                        "authenticated": device.authenticated,
                        "last_seen": device.last_heartbeat.isoformat(),
                    }
            with open(self.config_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[ESP32Manager] Error guardando dispositivos: {e}")

    # ------------------------------------------------------------------
    # Códigos de vinculación
    # ------------------------------------------------------------------
    def generate_pairing_code(self, user_id: str) -> str:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        self.pairing_codes[code] = {
            "user_id": user_id,
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(minutes=10),
        }
        self._clean_expired_codes()
        return code

    def verify_pairing_code(self, code: str, device_id: str) -> Optional[str]:
        """Usado por el flujo WebSocket (mensaje tipo 'pair')."""
        code = code.upper().strip()
        if code not in self.pairing_codes:
            return None
        pairing = self.pairing_codes[code]
        if datetime.now() > pairing["expires_at"]:
            del self.pairing_codes[code]
            return None
        user_id = pairing["user_id"]
        del self.pairing_codes[code]
        return user_id

    def _clean_expired_codes(self):
        now = datetime.now()
        expired = [c for c, d in self.pairing_codes.items() if now > d["expires_at"]]
        for c in expired:
            del self.pairing_codes[c]

    # ------------------------------------------------------------------
    # NUEVO: autorización vía HTTP (reemplaza la escritura manual de dict
    # que había antes en /api/esp32/pair dentro de web_app.py)
    # ------------------------------------------------------------------
    def authorize_device(self, device_id: str, user_id: str) -> ESP32Device:
        """
        Marca un device_id como autorizado/vinculado a un user_id.
        Esto NO significa que esté online: solo que si ese device_id
        abre un WebSocket, se le debe dejar pasar sin repetir el código.
        """
        device = self.devices.get(device_id)
        if device is None:
            device = ESP32Device(device_id)
            self.devices[device_id] = device
        device.user_id = user_id
        device.authenticated = True
        self._save_devices()
        print(f"[ESP32Manager] Dispositivo {device_id} autorizado para {user_id} (pendiente de WebSocket)")
        return device

    # ------------------------------------------------------------------
    # Conexión en vivo (WebSocket)
    # ------------------------------------------------------------------
    def register_device(self, device_id: str, websocket) -> ESP32Device:
        """
        Se llama cuando el ESP32 abre el WebSocket /esp32/{device_id}.
        Si el dispositivo ya fue autorizado por HTTP, reutiliza esa
        identidad en vez de crear una entrada nueva sin user_id.
        """
        device = self.devices.get(device_id)
        if device is not None:
            device.websocket = websocket
            device.update_heartbeat()
            print(f"[ESP32Manager] Dispositivo {device_id} conectado por WebSocket "
                  f"(autenticado={device.authenticated}, user={device.user_id})")
            return device

        device = ESP32Device(device_id, websocket)
        self.devices[device_id] = device
        print(f"[ESP32Manager] Dispositivo {device_id} registrado (sin autorizar aún)")
        return device

    def unregister_device(self, device_id: str):
        """Al desconectar el WebSocket, NO borramos el dispositivo (perderíamos
        el vínculo con el usuario) — solo soltamos el websocket."""
        device = self.devices.get(device_id)
        if device is not None:
            device.websocket = None
            print(f"[ESP32Manager] Dispositivo {device_id} desconectado (sigue autorizado)")

    def link_device_to_user(self, device_id: str, user_id: str):
        device = self.devices.get(device_id)
        if device is None:
            device = ESP32Device(device_id)
            self.devices[device_id] = device
        device.user_id = user_id
        device.authenticated = True
        self._save_devices()
        print(f"[ESP32Manager] Dispositivo {device_id} vinculado a usuario {user_id}")

    def get_device_by_user(self, user_id: str) -> Optional[ESP32Device]:
        for device in self.devices.values():
            if device.user_id == user_id and device.is_online():
                return device
        return None

    def get_connected_devices(self) -> List[Dict]:
        return [d.to_public_dict() for d in self.devices.values()]

    def get_connected_count(self) -> int:
        return sum(1 for d in self.devices.values() if d.is_online())

    def get_authenticated_count(self) -> int:
        return sum(1 for d in self.devices.values() if d.authenticated)

    async def send_proactive_message(self, user_id: str, text: str, audio_base64: str = None) -> bool:
        """Envía un mensaje (y opcionalmente audio PCM) al ESP32 vinculado a user_id."""
        device = self.get_device_by_user(user_id)
        if not device or not device.websocket:
            return False
        try:
            message = {
                "type": "proactive",
                "text": text,
                "timestamp": datetime.now().isoformat(),
            }
            if audio_base64:
                message["audio"] = audio_base64
            await device.websocket.send_json(message)
            return True
        except Exception as e:
            print(f"[ESP32Manager] Error enviando mensaje: {e}")
            # el socket probablemente murió; lo soltamos para que is_online() sea correcto
            device.websocket = None
            return False

    async def start_cleanup_loop(self, interval_seconds: int = 30):
        """Suelta websockets inactivos (no borra el dispositivo, solo el socket)."""
        while True:
            await asyncio.sleep(interval_seconds)
            for device in self.devices.values():
                if device.websocket is not None and not device.is_online():
                    print(f"[ESP32Manager] Dispositivo {device.device_id} sin heartbeat, soltando socket")
                    device.websocket = None


# Instancia global
esp32_manager = ESP32Manager()