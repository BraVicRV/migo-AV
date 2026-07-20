"""
AURA - Interfaz Web v4 + Supabase
- Reproductor de música embebido (YouTube iframe)
- Selector de voz TTS con voces disponibles del navegador
- Mejor parsing de horarios relativos (mañana, hoy, etc.)
- Interfaz completamente responsiva
- Personalidad personalizable por usuario (género, tono, empatía)
- Tareas funcionando correctamente
- ESCUCHA ACTIVA con "Hey Migo" (frontend)
- REPRODUCTOR DE MÚSICA UNIVERSAL con fallback automático
- SOPORTE PARA ESP32 CON SELECCION DE VOZ
"""

import os
import sys
from pathlib import Path

# ============================================================
# CARGAR .ENV ANTES DE CUALQUIER IMPORT DE main o core
# ============================================================
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
        print(f"[WebApp] .env cargado desde: {env_path}")
    else:
        print(f"[WebApp] .env no encontrado en: {env_path}")
except ImportError:
    print("[WebApp] python-dotenv no instalado, usando variables de entorno del sistema")

# ============================================================
# IMPORTS ESTANDAR
# ============================================================
import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent))

# ============================================================
# IMPORTS DEL PROYECTO (despues de load_dotenv)
# ============================================================
try:
    from main import AmigoVirtual
    print("[WebApp] AmigoVirtual importado correctamente")
except ImportError as e:
    print(f"[WebApp] Error importando AmigoVirtual: {e}")
    AmigoVirtual = None

try:
    from core.supabase_client import get_supabase_manager
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("[WebApp] Supabase no disponible, usando solo SQLite local")

# ============================================================
# NUEVOS IMPORTS PARA TTS Y ESP32
# ============================================================
try:
    from core.tts_service import tts_service
    TTS_AVAILABLE = True
    print("[WebApp] TTS Service cargado correctamente")
except ImportError as e:
    TTS_AVAILABLE = False
    print(f"[WebApp] TTS Service no disponible: {e}")

try:
    from core.esp32_manager import esp32_manager
    ESP32_AVAILABLE = True
    print("[WebApp] ESP32 Manager cargado correctamente")
except ImportError as e:
    ESP32_AVAILABLE = False
    print(f"[WebApp] ESP32 Manager no disponible: {e}")

app = FastAPI(title="AURA - Amigo Virtual")

# ============================================================
# STATIC FILES
# ============================================================
static_path = Path("static")
if static_path.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

# ------------------------------------------------------------------
# Frases de crisis
# ------------------------------------------------------------------
CRISIS_PHRASES = [
    "no tengo ganas de vivir", "quiero morir", "mejor muerto", "no vale la pena vivir",
    "quiero quitarme la vida", "sin ganas de vivir", "pensar en suicidarme",
    "hacerme dano", "no quiero seguir", "ya no puedo mas"
]

def detect_crisis(text: str) -> bool:
    return any(phrase in text.lower() for phrase in CRISIS_PHRASES)

# ------------------------------------------------------------------
# Gestor de conexiones
# ------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)

manager = ConnectionManager()

# ------------------------------------------------------------------
# Instancias AURA por usuario (en memoria)
# ------------------------------------------------------------------
aura_instances: Dict[str, AmigoVirtual] = {}

def get_aura(user_id: str, api_key: str = None):
    """
    Obtiene o crea una instancia de AURA para un usuario especifico.
    Si hay Supabase, intenta cargar la API key desde alli primero.
    """
    if user_id not in aura_instances:
        # Si no se proporciono API key, intentar cargar desde Supabase
        if not api_key and SUPABASE_AVAILABLE:
            try:
                supabase = get_supabase_manager()
                if supabase.is_connected():
                    api_key = supabase.get_api_key(user_id)
                    if api_key:
                        print(f"[WebApp] API key cargada desde Supabase para {user_id}")
            except Exception as e:
                print(f"[WebApp] Error cargando API key de Supabase: {e}")
        
        # Crear instancia
        aura_instances[user_id] = AmigoVirtual(user_id=user_id)
        
        # MARCAR MODO WEB para desactivar voz en backend
        aura_instances[user_id]._web_mode = True
        
        # Configurar API key si se tiene
        if api_key and hasattr(aura_instances[user_id].brain.groq, 'set_api_key'):
            try:
                aura_instances[user_id].brain.groq.set_api_key(api_key)
                # Guardar en config local y Supabase
                from core.user_config import get_user_config
                user_config = get_user_config(user_id)
                user_config.set_groq_api_key(api_key)
                
                if SUPABASE_AVAILABLE:
                    supabase = get_supabase_manager()
                    if supabase.is_connected():
                        supabase.save_api_key(user_id, api_key)
                        print(f"[WebApp] API key sincronizada a Supabase para {user_id}")
            except Exception as e:
                print(f"[WebApp] Error configurando API key: {e}")
    
    return aura_instances[user_id]

# ============================================================
# FUNCIONES AUXILIARES PARA AUDIO
# ============================================================

async def generate_audio_for_user(user_id: str, text: str):
    """
    Genera audio usando la voz preferida del usuario o una voz por defecto
    """
    if not TTS_AVAILABLE:
        return None
    
    try:
        # Obtener la voz preferida del usuario
        aura = get_aura(user_id)
        voice_name = getattr(aura, '_voice_preference', None)
        
        # Obtener el género de la personalidad
        gender = aura.personality.get("gender", "femenino")
        
        # Generar audio con la voz seleccionada
        audio_base64 = await tts_service.text_to_speech_base64_with_voice(
            text,
            voice_name=voice_name,
            gender=gender,
            rate=0.95
        )
        return audio_base64
    except Exception as e:
        print(f"[Audio] Error generando audio: {e}")
        return None

# ============================================================
# ENDPOINTS
# ============================================================

# -------------------------------------------
# RUTA PRINCIPAL - LEE EL ARCHIVO DIRECTAMENTE
# -------------------------------------------
@app.get("/")
async def index():
    """Sirve la interfaz web desde templates/index.html"""
    html_path = Path("templates/index.html")
    if not html_path.exists():
        return HTMLResponse(
            "<h1>Error: templates/index.html no encontrado</h1>",
            status_code=404
        )
    
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    return HTMLResponse(html_content)

# -------------------------------------------
# ENDPOINTS DE HORARIO
# -------------------------------------------
@app.get("/api/schedule")
async def get_schedule(request: Request):
    user_id = request.headers.get('x-user-id', 'default')
    aura = get_aura(user_id)
    return aura.scheduler.get_schedule()

@app.post("/api/schedule")
async def add_schedule(request: Request):
    data = await request.json()
    user_id = request.headers.get('x-user-id', 'default')
    aura = get_aura(user_id)
    aura.scheduler.add_active_hour(
        day=data.get('day', 'lunes'),
        start=data['start'],
        end=data['end'],
        name=data.get('course', data.get('name', 'Clase')),
        course=data.get('course', '')
    )
    return {"success": True}

@app.delete("/api/schedule/{index}")
async def delete_schedule(index: int, request: Request):
    user_id = request.headers.get('x-user-id', 'default')
    aura = get_aura(user_id)
    aura.scheduler.remove_active_hour(index)
    return {"success": True}

@app.get("/api/schedule/active")
async def is_active(request: Request):
    user_id = request.headers.get('x-user-id', 'default')
    aura = get_aura(user_id)
    return {
        "is_active": aura.scheduler.is_in_active_hours(),
        "current_hour": datetime.now().strftime("%H:%M")
    }

@app.get("/api/schedule/weekly")
async def get_weekly_schedule(request: Request):
    user_id = request.headers.get('x-user-id', 'default')
    aura = get_aura(user_id)
    return aura.scheduler.get_weekly_schedule()

@app.get("/api/schedule/current-course")
async def get_current_course(request: Request):
    user_id = request.headers.get('x-user-id', 'default')
    aura = get_aura(user_id)
    return {
        "is_active": aura.scheduler.is_in_active_hours(),
        "course": aura.scheduler.get_current_course(),
        "current_hour": datetime.now().strftime("%H:%M")
    }

@app.post("/api/schedule/delete")
async def delete_schedule_item(request: Request):
    data = await request.json()
    day, index = data.get('day'), data.get('index')
    user_id = request.headers.get('x-user-id', 'default')
    aura = get_aura(user_id)
    if day is not None and index is not None:
        items = aura.scheduler.get_schedule()
        items_for_day = [i for i, item in enumerate(items) if item.get('day') == day]
        if index < len(items_for_day):
            aura.scheduler.remove_active_hour(items_for_day[index])
    return {"success": True}

# -------------------------------------------
# ENDPOINTS DE TAREAS
# -------------------------------------------
@app.get("/api/tasks")
async def get_tasks(request: Request):
    user_id = request.headers.get('x-user-id', 'default')
    aura = get_aura(user_id)
    return aura.tasks.get_pending()

@app.delete("/api/tasks/{task_id}")
async def complete_task(task_id: int, request: Request):
    user_id = request.headers.get('x-user-id', 'default')
    aura = get_aura(user_id)
    aura.tasks.complete(task_id)
    return {"success": True}

# -------------------------------------------
# ENDPOINTS DE SALUD Y ESTADÍSTICAS
# -------------------------------------------
@app.get("/api/health")
async def health_check():
    supabase_status = "connected" if SUPABASE_AVAILABLE and get_supabase_manager().is_connected() else "disconnected"
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "supabase": supabase_status,
        "active_users": len(aura_instances)
    }

@app.get("/api/users/{user_id}/stats")
async def get_user_stats(user_id: str):
    if user_id not in aura_instances:
        return {"error": "Usuario no encontrado"}
    aura = aura_instances[user_id]
    profile = aura.brain.user_profile.to_dict()
    return {
        "user_id": user_id,
        "interaction_count": profile.get("interaction_count", 0),
        "interests": list(profile.get("interests", [])),
        "goals": profile.get("goals", []),
        "emotional_patterns": profile.get("emotional_patterns", {}),
        "known_areas": list(profile.get("known_facts", [])),
        "unknown_areas": list(profile.get("unknown_areas", []))
    }

# -------------------------------------------
# ENDPOINT: Estado de escucha activa
# -------------------------------------------
@app.get("/api/wake/status")
async def get_wake_status():
    """Devuelve el estado de la escucha activa (para debugging)"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "message": "La escucha activa se maneja en el frontend con Web Speech API",
        "endpoints": {
            "ws": "/ws/{user_id}",
            "wake_status": "/api/wake/status"
        }
    }

# ============================================================
# ENDPOINTS PARA ESP32
# ============================================================

@app.get("/api/esp32/pairing-code")
async def generate_pairing_code(request: Request):
    """Genera un código de vinculación para el ESP32."""
    user_id = request.headers.get('x-user-id')
    if not user_id:
        user_id = request.query_params.get('user_id')
    
    if not user_id or user_id == "default":
        return JSONResponse({
            "success": False,
            "error": "Usuario inválido. Inicia sesión primero."
        }, status_code=400)
    
    try:
        code = esp32_manager.generate_pairing_code(user_id)
        return {
            "success": True,
            "code": code,
            "expires_in": 600,
            "user_id": user_id,
            "message": f"Código generado: {code}. Ingresa este código en tu ESP32."
        }
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

# ============================================================
# ENDPOINT PARA VERIFICAR CÓDIGO DE PAIRING (ESP32)
# ============================================================

@app.post("/api/esp32/pair")
async def verify_pairing_code(request: Request):
    """
    Verifica el código de vinculación enviado por el ESP32 vía HTTP.
    """
    try:
        data = await request.json()
        code = data.get("code", "").strip().upper()
        device_id = data.get("device_id", "").strip() or data.get("device", "").strip()
        
        print(f"[ESP32] Pair request - code: {code}, device_id: {device_id}")
        
        if not code:
            return JSONResponse({
                "success": False,
                "error": "Código requerido"
            }, status_code=400)
        
        # Verificar el código
        from core.esp32_manager import esp32_manager
        
        # Verificar si el código existe
        if code not in esp32_manager.pairing_codes:
            print(f"[ESP32] Código {code} no encontrado")
            return JSONResponse({
                "success": False,
                "error": "Código inválido"
            }, status_code=400)
        
        # Verificar expiración
        pairing = esp32_manager.pairing_codes[code]
        if datetime.now() > pairing["expires_at"]:
            del esp32_manager.pairing_codes[code]
            return JSONResponse({
                "success": False,
                "error": "Código expirado"
            }, status_code=400)
        
        user_id = pairing["user_id"]
        
        # Eliminar el código (un solo uso)
        del esp32_manager.pairing_codes[code]
        
        print(f"[ESP32] Código {code} verificado para usuario {user_id}")
        
        # Guardar dispositivo en memoria (simple)
        # Autorizar el dispositivo (objeto ESP32Device real, no un dict suelto).
        # OJO: esto NO lo marca "online" todavía -- online real solo ocurre
        # cuando el ESP32 abre el WebSocket /esp32/{device_id} y manda "hello".
        if device_id:
            esp32_manager.authorize_device(device_id, user_id)
            print(f"[ESP32] Dispositivo {device_id} autorizado para {user_id}")
        
        return {
            "success": True,
            "user_id": user_id,
            "message": f"Dispositivo {device_id} vinculado a {user_id}"
        }
        
    except Exception as e:
        import traceback
        print(f"[ESP32] Error en pair: {e}")
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.post("/api/esp32/voice")
async def esp32_voice_input(request: Request):
    """
    Recibe mensaje de voz desde el ESP32 y responde con audio.
    """
    try:
        data = await request.json()
        text = data.get("text", "").strip()
        device_id = data.get("device", "").strip() or data.get("device_id", "").strip()
        
        if not text:
            return JSONResponse({
                "success": False,
                "error": "Texto requerido"
            }, status_code=400)
        
        # Obtener el user_id del dispositivo o del cuerpo
        from core.esp32_manager import esp32_manager
        
        # Buscar el user_id asociado al dispositivo
        user_id = None
        if device_id and device_id in esp32_manager.devices:
            device = esp32_manager.devices[device_id]
            user_id = getattr(device, 'user_id', None)
        
        # Si no hay user_id, usar el que viene en la petición o 'default'
        if not user_id:
            user_id = data.get("user_id", "default")
        
        # Procesar mensaje con AURA
        from main import AmigoVirtual
        aura = AmigoVirtual(user_id=user_id)
        aura._web_mode = True
        
        # Procesar mensaje
        response = await aura.chat(text)
        
        # Generar audio de la respuesta
        from core.tts_service import tts_service
        audio_base64 = None
        try:
            personality = aura.personality
            voice = tts_service.get_voice_for_personality(
                gender=personality.get("gender", "femenino")
            )
            audio_base64 = await tts_service.text_to_speech_pcm_base64(
                response,
                voice=voice,
                rate=0.95
            )
        except Exception as e:
            print(f"[ESP32] Error generando audio: {e}")
        
        return {
            "success": True,
            "response": response,
            "audio": audio_base64
        }
        
    except Exception as e:
        print(f"[ESP32] Error en voice: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.get("/api/esp32/status")
async def get_esp32_status():
    """
    Devuelve el estado de los dispositivos ESP32.
    """
    try:
        from core.esp32_manager import esp32_manager
                
        devices = esp32_manager.get_connected_devices()
        
        return {
            "total_connected": len(devices),
            "authenticated": sum(1 for d in devices if d.get("authenticated")),
            "devices": devices,
            "pairing_codes": len(esp32_manager.pairing_codes)
        }
    except Exception as e:
        print(f"[ESP32] Error en status: {e}")
        return {
            "total_connected": 0,
            "authenticated": 0,
            "devices": [],
            "pairing_codes": 0
        }
    
@app.websocket("/esp32/{device_id}")
async def esp32_websocket(websocket: WebSocket, device_id: str):
    """
    WebSocket para comunicación con ESP32.
    """
    if not ESP32_AVAILABLE:
        await websocket.close()
        return
    
    await websocket.accept()
    
    # Registrar dispositivo
    device = esp32_manager.register_device(device_id, websocket)
    print(f"[ESP32] 🟢 Dispositivo {device_id} conectado")
    
    try:
        while True:
            # Recibir mensaje del ESP32
            data = await websocket.receive_json()
            
            # Tipo de mensaje
            msg_type = data.get("type", "unknown")

            if msg_type == "hello":
                # El ESP32 ya se autorizó por HTTP (/api/esp32/pair) y ahora
                # solo abre el canal en vivo para recibir audio empujado.
                if device.authenticated and device.user_id:
                    device.update_heartbeat()
                    await websocket.send_json({
                        "type": "hello_ack",
                        "user_id": device.user_id
                    })
                    print(f"[ESP32] {device_id} conectado en vivo como {device.user_id}")
                else:
                    await websocket.send_json({
                        "type": "hello_error",
                        "error": "Dispositivo no autorizado. Usa 'pair' con el código primero."
                    })
                continue            
            
            if msg_type == "heartbeat":
                # Actualizar heartbeat
                device.update_heartbeat()
                await websocket.send_json({
                    "type": "heartbeat_ack",
                    "timestamp": datetime.now().isoformat()
                })
                
            elif msg_type == "pair":
                # Vincular con usuario usando código
                code = data.get("code", "").strip()
                if not code:
                    await websocket.send_json({
                        "type": "pair_error",
                        "error": "Código requerido"
                    })
                    continue
                
                user_id = esp32_manager.verify_pairing_code(code, device_id)
                if user_id:
                    # Vincular dispositivo
                    esp32_manager.link_device_to_user(device_id, user_id)
                    
                    # Cargar personalidad del usuario
                    from main import AmigoVirtual
                    aura = AmigoVirtual(user_id=user_id)
                    personality = aura.personality
                    
                    # Generar saludo con audio
                    greeting = aura.start()
                    
                    # Generar audio del saludo
                    audio_base64 = None
                    if TTS_AVAILABLE:
                        try:
                            voice = tts_service.get_voice_for_personality(
                                gender=personality.get("gender", "femenino")
                            )
                            audio_base64 = await tts_service.text_to_speech_pcm_base64(
                                greeting,
                                voice=voice,
                                rate=0.95
                            )
                        except Exception as e:
                            print(f"[ESP32] Error generando audio: {e}")
                    
                    await websocket.send_json({
                        "type": "paired",
                        "success": True,
                        "user_id": user_id,
                        "greeting": greeting,
                        "audio": audio_base64,
                        "personality": personality
                    })
                    
                    print(f"[ESP32] 🔗 Dispositivo {device_id} vinculado a {user_id}")
                else:
                    await websocket.send_json({
                        "type": "pair_error",
                        "error": "Código inválido o expirado"
                    })
                    
            elif msg_type == "voice_input":
                # El ESP32 envió voz del usuario
                text = data.get("text", "")
                user_id = device.user_id
                
                if not user_id:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Dispositivo no vinculado"
                    })
                    continue
                
                # Procesar con AURA
                from main import AmigoVirtual
                aura = AmigoVirtual(user_id=user_id)
                
                # Marcar modo ESP32 (para no usar voz local)
                aura._web_mode = True
                
                # Procesar mensaje
                response = await aura.chat(text)
                
                # Generar audio de la respuesta
                personality = aura.personality
                audio_base64 = None
                if TTS_AVAILABLE:
                    try:
                        voice = tts_service.get_voice_for_personality(
                            gender=personality.get("gender", "femenino")
                        )
                        audio_base64 = await tts_service.text_to_speech_pcm_base64(
                            response,
                            voice=voice,
                            rate=0.95
                        )
                    except Exception as e:
                        print(f"[ESP32] Error generando audio: {e}")
                
                await websocket.send_json({
                    "type": "response",
                    "text": response,
                    "audio": audio_base64,
                    "emotion": aura.user_mood_history[-1] if aura.user_mood_history else None
                })
                
            elif msg_type == "status_update":
                # Actualizar estado del dispositivo
                if "is_playing" in data:
                    device.is_playing = data["is_playing"]
                if "is_recording" in data:
                    device.is_recording = data["is_recording"]
                if "volume" in data:
                    device.volume = data["volume"]
                    
            elif msg_type == "audio_played":
                # El ESP32 confirmó que reprodujo el audio
                print(f"[ESP32] ✅ Audio reproducido en {device_id}")
                
            else:
                print(f"[ESP32] ⚠️ Tipo de mensaje desconocido: {msg_type}")
                
    except WebSocketDisconnect:
        esp32_manager.unregister_device(device_id)
        print(f"[ESP32] 🔴 Dispositivo {device_id} desconectado")
    except Exception as e:
        print(f"[ESP32] ❌ Error en websocket {device_id}: {e}")
        esp32_manager.unregister_device(device_id)

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def _format_schedule_text(schedule: Dict) -> str:
    """Formatea el horario para mostrarlo en el chat"""
    days = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    result = []
    
    for day in days:
        classes = schedule.get(day, [])
        if classes:
            class_list = []
            for cls in classes:
                class_list.append(f"  • {cls.get('name', 'Clase')} de {cls.get('start', '')} a {cls.get('end', '')}")
            result.append(f"**{day.capitalize()}:**")
            result.extend(class_list)
    
    if not result:
        return "📭 No tienes clases agendadas."
    
    return "\n".join(result)


def _get_thinking_hint(text: str) -> str:
    """Devuelve un hint contextual para mostrar mientras AURA piensa."""
    t = text.lower()
    if any(w in t for w in ['musica', 'cancion', 'reproduce', 'pon']):
        return '🎵 Buscando música...'
    if any(w in t for w in ['tarea', 'recuerdame', 'recordatorio']):
        return '📋 Gestionando tareas...'
    if any(w in t for w in ['triste', 'mal', 'llorar', 'solo']):
        return '💭 Pensando con cuidado...'
    if any(w in t for w in ['hora', 'tiempo', 'cuando']):
        return '🕐 Consultando hora...'
    if any(w in t for w in ['comer', 'desayuno', 'almuerzo', 'cena']):
        return '🍽️ Pensando en algo rico...'
    if any(w in t for w in ['clima', 'tiempo', 'lluvia', 'soleado']):
        return '🌤️ Consultando el clima...'
    if any(w in t for w in ['horario', 'clase', 'materia', 'mañana']):
        return '📚 Revisando tu horario...'
    return '🤔 Pensando...'

# ============================================================
# WEBSOCKET PRINCIPAL
# ============================================================
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket)
    aura = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "text")

            # Configurar API key al inicio
            if msg_type == "config":
                api_key = data.get("api_key", "")
                
                # Si no hay API key, intentar cargar desde Supabase
                if not api_key and SUPABASE_AVAILABLE:
                    try:
                        supabase = get_supabase_manager()
                        if supabase.is_connected():
                            api_key = supabase.get_api_key(user_id)
                            if api_key:
                                print(f"[WebSocket] API key cargada desde Supabase para {user_id}")
                    except Exception as e:
                        print(f"[WebSocket] Error cargando de Supabase: {e}")
                
                aura = get_aura(user_id, api_key)
                
                # Generar saludo proactivo inteligente
                greeting = aura.start()
                
                # Generar audio del saludo
                audio_base64 = await generate_audio_for_user(user_id, greeting)
                
                await manager.send_message({
                    "type": "greeting",
                    "text": greeting,
                    "audio": audio_base64,
                    "personality": aura.personality
                }, websocket)

                # Enviar facts si existen
                if hasattr(aura.brain, 'get_user_facts'):
                    facts = aura.brain.get_user_facts()
                    if facts:
                        await manager.send_message({
                            "type": "user_facts", 
                            "data": {k: v["value"] for k, v in facts.items()}
                        }, websocket)
                continue

            # Actualizar personalidad
            if msg_type == "personality_update":
                personality = data.get("personality", {})
                if aura is None:
                    aura = get_aura(user_id)
                
                # Actualizar personalidad
                for key, value in personality.items():
                    if key in aura.personality:
                        aura.personality[key] = value
                
                aura.save_config()
                
                await manager.send_message({
                    "type": "system",
                    "message": f"Personalidad actualizada: {personality.get('name', 'AURA')} ahora es más {personality.get('attitude', 'empática')}.",
                    "personality": aura.personality
                }, websocket)
                continue

            # ============================================================
            # RECIBIR PREFERENCIA DE VOZ
            # ============================================================
            if msg_type == "voice_preference":
                voice_name = data.get("voice_name", "")
                if voice_name:
                    # Guardar preferencia de voz para este usuario
                    if aura is None:
                        aura = get_aura(user_id)
                    aura._voice_preference = voice_name
                    print(f"[WebSocket] Voz seleccionada para {user_id}: {voice_name}")
                    
                    await manager.send_message({
                        "type": "system",
                        "message": f"✅ Voz configurada: {voice_name}"
                    }, websocket)
                continue

            # Mensaje de chat
            if msg_type == "text":
                if aura is None:
                    aura = get_aura(user_id)
                
                user_text = data.get("text", "").strip()
                if not user_text:
                    continue

                # ============================================================
                # DETECTAR COMANDOS DE AGREGAR CLASE
                # ============================================================
                if any(word in user_text.lower() for word in ['agrega clase', 'nueva clase', 'agregar clase', 'clase de', 'añadir clase', 'agregame clase']):
                    # Intentar parsear el texto
                    parsed = aura.scheduler.parse_schedule_text(user_text)
                    
                    if parsed and parsed["start"] and parsed["end"]:
                        # Agregar la clase
                        aura.scheduler.add_active_hour(
                            day=parsed["day"],
                            start=parsed["start"],
                            end=parsed["end"],
                            name=parsed["name"],
                            course=parsed["course"]
                        )
                        
                        response = f"✅ ¡Listo! Agregué la clase de **{parsed['name']}** los **{parsed['day']}** de **{parsed['start']}** a **{parsed['end']}**."
                        
                        # Enviar respuesta
                        await manager.send_message({
                            "type": "response",
                            "text": response,
                            "personality": aura.personality,
                            "timestamp": datetime.now().isoformat()
                        }, websocket)
                        
                        # ENVIAR ACTUALIZACIÓN DEL HORARIO AL FRONTEND
                        await manager.send_message({
                            "type": "schedule_update",
                            "schedule": aura.scheduler.get_weekly_schedule()
                        }, websocket)
                        
                        continue
                    else:
                        response = "❌ No pude entender el horario. Ejemplo: 'Agrega clase de IA el lunes de 17 a 19'"
                        await manager.send_message({
                            "type": "response",
                            "text": response,
                            "personality": aura.personality,
                            "timestamp": datetime.now().isoformat()
                        }, websocket)
                        continue

                # ============================================================
                # DETECTAR CONSULTAS DE HORARIO
                # ============================================================
                if any(word in user_text.lower() for word in ['que clase tengo', 'horario', 'mi horario', 'que tengo', 'que clases', 'mi clase']):
                    schedule = aura.scheduler.get_weekly_schedule()
                    schedule_text = _format_schedule_text(schedule)
                    response = f"📚 **Tu horario semanal:**\n{schedule_text}"
                    
                    await manager.send_message({
                        "type": "response",
                        "text": response,
                        "personality": aura.personality,
                        "timestamp": datetime.now().isoformat()
                    }, websocket)
                    continue

                # ============================================================
                # DETECTAR CONSULTAS DE FECHA Y HORA
                # ============================================================
                if any(word in user_text.lower() for word in ['que hora', 'qué hora', 'hora es', 'hora actual', 'que hora es']):
                    now = datetime.now()
                    hora_str = now.strftime("%H:%M")
                    response = f"Son las {hora_str}."
                    
                    await manager.send_message({
                        "type": "response",
                        "text": response,
                        "personality": aura.personality,
                        "timestamp": now.isoformat()
                    }, websocket)
                    continue

                if any(word in user_text.lower() for word in ['que dia', 'qué día', 'que fecha', 'qué fecha', 'fecha actual', 'a que dia', 'a qué día']):
                    full_date = aura.scheduler.get_full_date_es()
                    response = f"Hoy es {full_date}."
                    
                    await manager.send_message({
                        "type": "response",
                        "text": response,
                        "personality": aura.personality,
                        "timestamp": datetime.now().isoformat()
                    }, websocket)
                    continue                

                # ============================================================
                # PROCESAMIENTO NORMAL DE MENSAJE
                # ============================================================
                # Detectar crisis
                if detect_crisis(user_text):
                    await manager.send_message({"type": "crisis"}, websocket)

                # Mostrar "pensando..."
                thinking_hint = _get_thinking_hint(user_text)
                await manager.send_message({
                    "type": "status",
                    "status": "thinking",
                    "hint": thinking_hint
                }, websocket)

                try:
                    # Procesar mensaje
                    response = await aura.chat(user_text)
                    
                    # Obtener emocion
                    emotion = aura.user_mood_history[-1] if aura.user_mood_history else None
                    if emotion and hasattr(aura.emotions, 'session_history'):
                        emotion = {**emotion, "trend": aura.emotions._compute_trend()}

                    # Generar audio de la respuesta
                    # Generar audio de la respuesta (para el navegador, en MP3)
                    audio_base64 = await generate_audio_for_user(user_id, response)

                    # Empujar la respuesta también al parlante ESP32 vinculado,
                    # si hay uno conectado por WebSocket ahora mismo.
                    try:
                        esp32_device = esp32_manager.get_device_by_user(user_id)
                        if esp32_device:
                            esp32_gender = aura.personality.get("gender", "femenino")
                            esp32_voice = tts_service.get_voice_for_personality(gender=esp32_gender)
                            esp32_audio = await tts_service.text_to_speech_pcm_base64(
                                response, voice=esp32_voice, rate=0.95
                            )
                            await esp32_manager.send_proactive_message(user_id, response, esp32_audio)
                    except Exception as e:
                        print(f"[ESP32] Error empujando audio al parlante: {e}")

                    # Enviar respuesta
                    await manager.send_message({
                        "type": "response",
                        "text": response,
                        "audio": audio_base64,
                        "emotion": emotion,
                        "personality": aura.personality,
                        "timestamp": datetime.now().isoformat(),
                        "user_query": user_text  # Para el reproductor de música
                    }, websocket)

                    # Enviar facts actualizados
                    if hasattr(aura.brain, 'get_user_facts'):
                        facts = aura.brain.get_user_facts()
                        if facts:
                            await manager.send_message({
                                "type": "user_facts",
                                "data": {k: v["value"] for k, v in facts.items()}
                            }, websocket)

                    # Enviar actualización de tareas si la respuesta contiene palabras clave
                    if response and any(word in response.lower() for word in ['tarea', 'agregué', 'listo', 'pendiente']):
                        try:
                            pending_tasks = aura.tasks.get_pending()
                            await manager.send_message({
                                "type": "tasks_update",
                                "tasks": pending_tasks
                            }, websocket)
                        except Exception as e:
                            print(f"[WebSocket] Error enviando tasks_update: {e}")

                    await manager.send_message({
                        "type": "status", 
                        "status": "idle"
                    }, websocket)

                except Exception as e:
                    print(f"[WebSocket] Error procesando mensaje: {e}")
                    await manager.send_message({
                        "type": "error", 
                        "text": str(e)
                    }, websocket)
                    await manager.send_message({
                        "type": "status", 
                        "status": "idle"
                    }, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print(f"[WebSocket] Usuario {user_id} desconectado")
        
        # Sincronizar perfil a Supabase al desconectar
        if aura and SUPABASE_AVAILABLE:
            try:
                supabase = get_supabase_manager()
                if supabase.is_connected():
                    supabase.save_user_profile(user_id, aura.brain.user_profile.to_dict())
                    facts = aura.brain.get_user_facts()
                    if facts:
                        supabase.sync_user_facts(user_id, facts)
                    print(f"[WebSocket] Perfil sincronizado a Supabase para {user_id}")
            except Exception as e:
                print(f"[WebSocket] Error sincronizando a Supabase: {e}")
                
    except Exception as e:
        print(f"[WebSocket] Error general: {e}")
        manager.disconnect(websocket)


# ============================================================
# INICIALIZAR ESP32 MANAGER
# ============================================================

@app.on_event("startup")
async def startup_event():
    """Inicia el gestor de ESP32 al arrancar la aplicación."""
    if ESP32_AVAILABLE:
        import asyncio
        asyncio.create_task(esp32_manager.start_cleanup_loop(30))
        print("[ESP32] ✅ Gestor de ESP32 iniciado")

# ------------------------------------------------------------------
# Inicio
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    # Verificar conexion a Supabase al iniciar
    if SUPABASE_AVAILABLE:
        supabase = get_supabase_manager()
        if supabase.is_connected():
            print("\n✅ Supabase conectado correctamente")
        else:
            print("\n⚠️  Supabase no conectado - funcionando en modo offline")
    else:
        print("\n⚠️  Supabase no disponible - funcionando en modo offline")

    port = int(os.environ.get("PORT", 8000))
    is_prod = os.environ.get("RENDER") or port != 8000

    print("\n" + "="*50)
    print("AURA WEB v4 + Supabase — " + ("PRODUCCION" if is_prod else "DESARROLLO"))
    print("="*50)
    print("Memoria por usuario: activada")
    print("API key por usuario: activada")
    print("Supabase sync: activado")
    print("Reproductor de musica embebido: activado")
    print("Selector de voz TTS: activado")
    print("Escucha activa (Hey Migo): activada (frontend)")
    if not is_prod:
        print("Interfaz: http://localhost:8000")
        print("Wake status: http://localhost:8000/api/wake/status")
    print("Presiona CTRL+C para detener\n")

    uvicorn.run(app, host="0.0.0.0", port=port)