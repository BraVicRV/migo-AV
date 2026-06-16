"""
AURA - Interfaz Web v3 + Supabase
- Perfiles en Supabase (sincronizacion multi-dispositivo)
- API keys en Supabase (seguridad centralizada)
- Resumenes en Supabase (persistencia en la nube)
- SQLite local como cache offline
- Voz en navegador con Web Speech API
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
from datetime import datetime
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
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

app = FastAPI(title="AURA - Amigo Virtual")

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

# ------------------------------------------------------------------
# HTML completo de la interfaz
# ------------------------------------------------------------------
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>AURA - Amigo Virtual con IA</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg-primary: #0a0e1a;
  --bg-secondary: #111827;
  --bg-tertiary: #1f2937;
  --bg-hover: #374151;
  --accent: #6366f1;
  --accent-light: #818cf8;
  --accent-dark: #4f46e5;
  --text-primary: #f9fafb;
  --text-secondary: #9ca3af;
  --text-muted: #6b7280;
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  --info: #3b82f6;
  --border: rgba(255,255,255,0.08);
  --radius: 12px;
  --radius-sm: 8px;
  --shadow: 0 4px 6px -1px rgba(0,0,0,0.3);
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;font-family:'Inter',sans-serif;background:var(--bg-primary);color:var(--text-primary);overflow:hidden;font-size:14px}

/* Scrollbar global */
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--bg-hover);border-radius:10px}
::-webkit-scrollbar-thumb:hover{background:var(--text-muted)}

.app-container{display:flex;height:100vh;width:100vw}

/* SIDEBAR CON SCROLL GLOBAL - paneles se expanden libremente */
.sidebar{
  width:320px;min-width:320px;max-width:320px;background:var(--bg-secondary);
  border-right:1px solid var(--border);display:flex;flex-direction:column;
  overflow-y:auto;overflow-x:hidden;transition:transform .3s ease;
  padding-bottom:20px;flex-shrink:0;
  scrollbar-width:thin;
  scrollbar-color:var(--bg-hover) var(--bg-secondary);
}
.sidebar::-webkit-scrollbar{
  width:6px;
}
.sidebar::-webkit-scrollbar-track{
  background:var(--bg-secondary);
}
.sidebar::-webkit-scrollbar-thumb{
  background:var(--bg-hover);
  border-radius:3px;
}
.sidebar::-webkit-scrollbar-thumb:hover{
  background:var(--text-muted);
}

/* Panel: SIN max-height, SIN overflow. Se expande con su contenido */
.panel{
  margin:12px 16px;background:var(--bg-tertiary);border-radius:var(--radius);
  border:1px solid var(--border);overflow:visible;
  flex-shrink:0;
}

/* Panel body: SIN scroll, se expande */
.panel-body{
  padding:12px 16px;
  overflow:visible;
  overflow-wrap:break-word;
  word-wrap:break-word;
}

/* List container: SIN max-height, SIN overflow. Se expande con items */
.list-container{
  display:flex;flex-direction:column;
  gap:6px;
  padding-right:0;
}

/* Info row: mejorado para no cortar */
.info-row{
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  padding:8px 0;
  border-bottom:1px solid var(--border);
  font-size:13px;
  gap:12px;
}
.info-row:last-child{border-bottom:none}
.info-label{color:var(--text-muted);font-weight:400;flex-shrink:0}
.info-value{
  color:var(--text-primary);
  font-weight:500;
  text-align:right;
  max-width:70%;
  word-break:break-word;
}

/* Resto del CSS (sin cambios) */
.menu-toggle{
  display:none;position:fixed;top:16px;left:16px;z-index:100;
  background:var(--bg-tertiary);border:1px solid var(--border);
  border-radius:var(--radius-sm);padding:10px;cursor:pointer;color:var(--text-primary);
  transition:all .2s
}
.menu-toggle:hover{background:var(--bg-hover)}
.sidebar-header{padding:24px 20px;border-bottom:1px solid var(--border)}
.logo{display:flex;align-items:center;gap:12px;margin-bottom:16px}
.logo-icon{
  width:44px;height:44px;background:linear-gradient(135deg,var(--accent),var(--accent-light));
  border-radius:var(--radius);display:flex;align-items:center;justify-content:center;
  font-size:20px;font-weight:700;color:white;flex-shrink:0;
  animation:pulse 3s ease-in-out infinite
}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(99,102,241,.4)}50%{box-shadow:0 0 0 8px rgba(99,102,241,0)}}
.logo-text h1{font-size:22px;font-weight:700;color:var(--text-primary);letter-spacing:-.5px}
.logo-text span{font-size:12px;color:var(--text-muted);font-weight:400}
.connection-status{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--text-secondary)}
.status-dot{
  width:8px;height:8px;border-radius:50%;background:var(--danger);transition:background .3s;position:relative
}
.status-dot.connected{background:var(--success)}
.status-dot.connected::after{
  content:'';position:absolute;inset:-2px;border-radius:50%;border:2px solid var(--success);
  animation:ping 1.5s cubic-bezier(0,0,.2,1) infinite
}
@keyframes ping{75%,100%{transform:scale(1.5);opacity:0}}
.panel-header{
  padding:12px 16px;background:rgba(255,255,255,.02);border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:8px
}
.panel-header h3{
  font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em
}
.panel-icon{width:16px;height:16px;opacity:.6}
.emotion-display{display:flex;align-items:center;gap:12px}
.emotion-icon{
  width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-size:18px;flex-shrink:0;transition:all .3s
}
.emotion-icon.neutral{background:rgba(156,163,175,.2);color:#9ca3af}
.emotion-icon.happy{background:rgba(16,185,129,.2);color:#10b981}
.emotion-icon.sad{background:rgba(59,130,246,.2);color:#3b82f6}
.emotion-icon.angry{background:rgba(239,68,68,.2);color:#ef4444}
.emotion-icon.anxious{background:rgba(245,158,11,.2);color:#f59e0b}
.emotion-icon.tired{background:rgba(139,92,246,.2);color:#8b5cf6}
.emotion-details{flex:1;min-width:0}
.emotion-name{font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:2px}
.emotion-secondary{font-size:11px;color:var(--text-muted);margin-bottom:6px}
.sentiment-bar{width:100%;height:4px;background:var(--bg-hover);border-radius:2px;overflow:hidden}
.sentiment-fill{height:100%;border-radius:2px;transition:width .5s ease,background .3s}
.sentiment-fill.positive{background:var(--success)}
.sentiment-fill.negative{background:var(--danger)}
.sentiment-fill.neutral{background:var(--text-muted)}
.trend-badge{
  display:inline-flex;align-items:center;gap:4px;font-size:10px;padding:2px 8px;
  border-radius:20px;margin-top:6px;font-weight:500
}
.trend-badge.up{background:rgba(16,185,129,.15);color:var(--success)}
.trend-badge.down{background:rgba(239,68,68,.15);color:var(--danger)}
.trend-badge.flat{background:rgba(255,255,255,.05);color:var(--text-muted)}
.list-item{
  display:flex;align-items:center;gap:8px;padding:8px 10px;
  background:var(--bg-secondary);border-radius:var(--radius-sm);font-size:12px;border:1px solid var(--border)
}
.list-item-time{color:var(--accent-light);font-weight:600;font-size:11px;min-width:70px;flex-shrink:0}
.list-item-text{flex:1;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.list-item-action{
  background:none;border:none;color:var(--text-muted);cursor:pointer;padding:2px 6px;
  border-radius:4px;font-size:11px;transition:all .2s
}
.list-item-action:hover{background:rgba(239,68,68,.2);color:var(--danger)}
.empty-state{text-align:center;padding:16px;color:var(--text-muted);font-size:12px}
.btn{
  width:100%;padding:8px;border-radius:var(--radius-sm);border:1px dashed var(--border);
  background:transparent;color:var(--text-muted);font-size:12px;cursor:pointer;
  transition:all .2s;font-family:inherit;margin-top:8px
}
.btn:hover{border-color:var(--accent);color:var(--accent-light);background:rgba(99,102,241,.1)}
.btn-primary{
  background:var(--accent);color:white;border:none;font-weight:500
}
.btn-primary:hover{background:var(--accent-dark)}
.btn-secondary{
  background:var(--bg-hover);color:var(--text-secondary);border:none
}
.btn-secondary:hover{background:var(--bg-tertiary);color:var(--text-primary)}
.quick-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:12px 16px}
.quick-btn{
  background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:10px 8px;color:var(--text-secondary);font-size:12px;cursor:pointer;
  transition:all .2s;text-align:center;font-family:inherit;font-weight:500
}
.quick-btn:hover{background:var(--accent);border-color:var(--accent);color:white;transform:translateY(-1px)}
.main-content{flex:1;display:flex;flex-direction:column;min-width:0;background:var(--bg-primary);position:relative}
.avatar-section{
  padding:32px 24px 20px;text-align:center;
  background:linear-gradient(180deg,rgba(99,102,241,.08) 0%,transparent 100%);
  flex-shrink:0
}
.avatar-container{position:relative;display:inline-block;margin-bottom:16px}
.avatar-abstract{
  width:90px;height:90px;border-radius:50%;
  background:linear-gradient(135deg,var(--accent),var(--accent-dark));
  display:flex;align-items:center;justify-content:center;
  position:relative;box-shadow:0 8px 32px rgba(99,102,241,.3);
  transition:transform .2s
}
.avatar-abstract:hover{transform:scale(1.05)}
.avatar-inner{
  width:60px;height:60px;border-radius:50%;
  background:rgba(255,255,255,.1);backdrop-filter:blur(10px);
  display:flex;align-items:center;justify-content:center
}
.avatar-inner svg{width:32px;height:32px;color:white;opacity:.9}
.avatar-ring{
  position:absolute;inset:-10px;border-radius:50%;
  border:2px solid rgba(99,102,241,.3);animation:spin 4s linear infinite
}
@keyframes spin{to{transform:rotate(360deg)}}
.sound-wave{
  display:flex;justify-content:center;align-items:center;gap:3px;
  height:32px;margin-bottom:8px
}
.wave-bar{
  width:3px;height:16px;background:var(--accent);border-radius:2px;transition:height .1s ease
}
.status-text{
  font-size:12px;color:var(--text-muted);font-weight:500;transition:color .3s
}
.status-text.thinking{color:var(--warning)}
.status-text.speaking{color:var(--accent-light)}
.status-text.error{color:var(--danger)}
.chat-section{
  flex:1;display:flex;flex-direction:column;overflow:hidden;
  margin:0 20px 20px;background:var(--bg-secondary);border-radius:var(--radius);
  border:1px solid var(--border)
}
.quick-pills{
  display:flex;gap:8px;padding:12px 16px;overflow-x:auto;flex-shrink:0;
  border-bottom:1px solid var(--border);scrollbar-width:none
}
.quick-pills::-webkit-scrollbar{display:none}
.pill{
  background:var(--bg-tertiary);border:1px solid var(--border);border-radius:20px;
  padding:6px 14px;color:var(--text-secondary);font-size:12px;white-space:nowrap;
  cursor:pointer;transition:all .2s;font-family:inherit;border:none
}
.pill:hover{background:var(--accent);color:white}
.messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
.message{display:flex;animation:msgIn .25s ease;max-width:80%}
@keyframes msgIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.message.user{align-self:flex-end;justify-content:flex-end}
.message.bot{align-self:flex-start}
.bubble{padding:10px 14px;border-radius:16px;font-size:13px;line-height:1.5;position:relative;word-wrap:break-word}
.message.user .bubble{background:var(--accent);color:white;border-bottom-right-radius:4px}
.message.bot .bubble{background:var(--bg-tertiary);color:var(--text-primary);border-bottom-left-radius:4px;border:1px solid var(--border)}
.message-time{display:block;font-size:10px;margin-top:4px;opacity:.6}
.message.user .message-time{color:rgba(255,255,255,.7)}
.message.bot .message-time{color:var(--text-muted)}
.typing-indicator{display:flex;align-items:center;gap:4px;padding:12px 16px}
.typing-dot{
  width:6px;height:6px;background:var(--text-muted);border-radius:50%;
  animation:typingBounce 1.4s infinite ease-in-out both
}
.typing-dot:nth-child(1){animation-delay:-.32s}
.typing-dot:nth-child(2){animation-delay:-.16s}
@keyframes typingBounce{0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}.typing-hint{font-size:11px;color:var(--text-muted);margin-left:8px}
.crisis-alert{
  background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);
  border-radius:var(--radius-sm);padding:12px 16px;margin:0 16px 12px;
  font-size:12px;color:#fca5a5;display:none;align-items:center;gap:8px
}
.crisis-alert.show{display:flex}
.crisis-alert svg{width:16px;height:16px;flex-shrink:0;color:var(--danger)}
.input-area{padding:12px 16px;border-top:1px solid var(--border);flex-shrink:0}
.input-row{display:flex;gap:10px;align-items:center}
.input-btn{
  width:40px;height:40px;border-radius:50%;border:1px solid var(--border);
  background:var(--bg-tertiary);color:var(--text-secondary);
  display:flex;align-items:center;justify-content:center;cursor:pointer;
  transition:all .2s;flex-shrink:0
}
.input-btn:hover{background:var(--accent);border-color:var(--accent);color:white}
.input-btn.listening{
  background:var(--danger);border-color:var(--danger);color:white;
  animation:pulseMic 1s infinite
}
@keyframes pulseMic{0%,100%{transform:scale(1)}50%{transform:scale(1.1)}}.msg-input{
  flex:1;background:var(--bg-tertiary);border:1px solid var(--border);
  border-radius:20px;padding:10px 18px;color:var(--text-primary);font-size:14px;
  font-family:inherit;outline:none;transition:all .2s
}
.msg-input:focus{border-color:var(--accent);background:var(--bg-hover)}
.msg-input::placeholder{color:var(--text-muted)}
.modal-overlay{
  position:fixed;inset:0;background:rgba(0,0,0,.8);backdrop-filter:blur(8px);
  display:none;align-items:center;justify-content:center;z-index:1000;padding:20px
}
.modal-overlay.show{display:flex}
.modal-box{
  background:var(--bg-secondary);border:1px solid var(--border);
  border-radius:var(--radius);padding:24px;width:100%;max-width:400px;
  box-shadow:var(--shadow)
}
.modal-box h3{font-size:18px;font-weight:600;margin-bottom:8px;color:var(--text-primary)}
.modal-box p{font-size:13px;color:var(--text-secondary);margin-bottom:16px;line-height:1.5}
.modal-box input,.modal-box select{
  width:100%;padding:10px 12px;margin-bottom:10px;border-radius:var(--radius-sm);
  border:1px solid var(--border);background:var(--bg-tertiary);color:var(--text-primary);
  font-size:13px;font-family:inherit;outline:none
}
.modal-box input:focus,.modal-box select:focus{border-color:var(--accent)}
.modal-actions{display:flex;gap:8px;margin-top:16px}
.modal-actions button{flex:1;padding:10px;border-radius:var(--radius-sm);border:none;cursor:pointer;font-size:13px;font-family:inherit;font-weight:500;transition:all .2s}
.api-key-input{font-family:monospace;letter-spacing:.5px}
.api-help{
  font-size:11px;color:var(--accent-light);margin-bottom:12px;display:block
}
.api-help:hover{text-decoration:underline}
@media(max-width:768px){
  .menu-toggle{display:block}
  .sidebar{position:fixed;left:0;top:0;height:100%;z-index:50;transform:translateX(-100%);box-shadow:4px 0 24px rgba(0,0,0,.5)}
  .sidebar.open{transform:translateX(0)}
  .main-content{width:100%}
  .message{max-width:90%}
}
.sidebar-overlay{
  display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:40
}
.sidebar-overlay.show{display:block}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:10px;font-weight:600;margin-top:8px}
.badge-success{background:rgba(16,185,129,.15);color:var(--success)}
.badge-danger{background:rgba(239,68,68,.15);color:var(--danger)}
.badge-info{background:rgba(59,130,246,.15);color:var(--info)}
</style>
</head>
<body>

<button class="menu-toggle" onclick="toggleSidebar()" aria-label="Menu">
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/>
  </svg>
</button>

<div class="sidebar-overlay" onclick="toggleSidebar()"></div>

<div class="app-container">

<<aside class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <div class="logo">
      <div class="logo-icon">A</div>
      <div class="logo-text">
        <h1>AURA</h1>
        <span>Amigo Virtual con IA</span>
      </div>
    </div>
    <div class="connection-status">
      <div class="status-dot" id="connDot"></div>
      <span id="connText">Desconectado</span>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <svg class="panel-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
      </svg>
      <h3>Personalidad</h3>
    </div>
    <div class="panel-body">
      <div class="info-row"><span class="info-label">Nombre</span><span class="info-value" id="pName">AURA</span></div>
      <div class="info-row"><span class="info-label">Actitud</span><span class="info-value" id="pAttitude">-</span></div>
      <div class="info-row"><span class="info-label">Humor</span><span class="info-value" id="pHumor">-</span></div>
      <div class="info-row"><span class="info-label">Empatia</span><span class="info-value" id="pEmpathy">-</span></div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <svg class="panel-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
      </svg>
      <h3>Tu Estado</h3>
    </div>
    <div class="panel-body">
      <div class="emotion-display">
        <div class="emotion-icon neutral" id="emoIcon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/><line x1="8" y1="15" x2="16" y2="15"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/>
          </svg>
        </div>
        <div class="emotion-details">
          <div class="emotion-name" id="emoName">Neutral</div>
          <div class="emotion-secondary" id="emoSecondary"></div>
          <div class="sentiment-bar"><div class="sentiment-fill neutral" id="emoFill" style="width:50%"></div></div>
          <div class="trend-badge flat" id="trendBadge">estable</div>
        </div>
      </div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <svg class="panel-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
      </svg>
      <h3>Lo que sabe de ti</h3>
    </div>
    <div class="panel-body">
      <div class="list-container scrollable" id="userFactsList">
        <div class="empty-state">Cuentame cosas sobre ti</div>
      </div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <svg class="panel-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
      </svg>
      <h3>Horario</h3>
    </div>
    <div class="panel-body">
      <div class="list-container scrollable" id="scheduleList">
        <div class="empty-state">Sin clases configuradas</div>
      </div>
      <button class="btn" onclick="openScheduleModal()">+ Agregar clase</button>
      <div class="badge badge-info" id="activeBadge">Verificando...</div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <svg class="panel-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
      </svg>
      <h3>Tareas</h3>
    </div>
    <div class="panel-body">
      <div class="list-container scrollable" id="taskList">
        <div class="empty-state">Sin tareas pendientes</div>
      </div>
    </div>
  </div>

  <div class="panel" style="margin-bottom:20px">
    <div class="panel-header">
      <svg class="panel-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
      </svg>
      <h3>Acciones</h3>
    </div>
    <div class="quick-grid">
      <button class="quick-btn" onclick="send('hora')">Hora</button>
      <button class="quick-btn" onclick="send('pon musica relajante')">Musica</button>
      <button class="quick-btn" onclick="send('modo estudio')">Estudiar</button>
      <button class="quick-btn" onclick="send('que debo comer')">Comer</button>
      <button class="quick-btn" onclick="send('que tareas tengo')">Tareas</button>
      <button class="quick-btn" onclick="send('que recuerdas de mi')">Memoria</button>
    </div>
  </div>
</aside>

<<main class="main-content">
  <div class="avatar-section">
    <div class="avatar-container">
      <div class="avatar-ring"></div>
      <div class="avatar-abstract" id="avatarFace">
        <div class="avatar-inner">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
            <line x1="9" y1="9" x2="9.01" y2="9"/>
            <line x1="15" y1="9" x2="15.01" y2="9"/>
          </svg>
        </div>
      </div>
    </div>
    <div class="sound-wave" id="soundWave">
      <div class="wave-bar"></div><div class="wave-bar"></div><div class="wave-bar"></div>
      <div class="wave-bar"></div><div class="wave-bar"></div><div class="wave-bar"></div>
      <div class="wave-bar"></div><div class="wave-bar"></div>
    </div>
    <div class="status-text" id="auraStatus">AURA esta lista</div>
  </div>

  <div class="chat-section">
    <div class="quick-pills">
      <button class="pill" onclick="send('Hola')">Saludar</button>
      <button class="pill" onclick="send('Como te llamas')">Quien eres</button>
      <button class="pill" onclick="send('Estoy triste')">Animo</button>
      <button class="pill" onclick="send('Que hora es')">Hora</button>
      <button class="pill" onclick="send('Pon musica relajante')">Musica</button>
      <button class="pill" onclick="send('que debo comer')">Comer</button>
      <button class="pill" onclick="send('que recuerdas de mi')">Memoria</button>
    </div>

    <div class="crisis-alert" id="crisisAlert">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <span>Si estas pasando por un momento dificil, no estas solo. Puedes llamar a una linea de crisis o hablar con alguien de confianza. Estoy aqui contigo.</span>
    </div>

    <div class="messages" id="messages">
      <div class="message bot">
        <div class="bubble">
          Conectando con AURA...
          <span class="message-time" id="welcomeTime"></span>
        </div>
      </div>
    </div>

    <div class="input-area">
      <div class="input-row">
        <button class="input-btn" id="micBtn" onclick="toggleMic()" aria-label="Microfono">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
            <line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/>
          </svg>
        </button>
        <input class="msg-input" id="msgInput" placeholder="Escribe un mensaje..." onkeydown="onKey(event)">
        <button class="input-btn" onclick="sendMsg()" aria-label="Enviar">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</main>
</div>

<!-- Modal API Key -->
<div class="modal-overlay" id="apiKeyModal">
  <div class="modal-box">
    <h3>Configuracion de Groq</h3>
    <p>Para usar AURA con IA necesitas una API key de Groq (es gratuita). Tu API key se guarda de forma segura y solo tu la usas.</p>
    <a href="https://console.groq.com" target="_blank" class="api-help">Obtener API key en console.groq.com →</a>
    <input type="password" id="apiKeyInput" class="api-key-input" placeholder="gsk_...">
    <div class="modal-actions">
      <button class="btn-primary" onclick="saveApiKey()">Guardar</button>
      <button class="btn-secondary" onclick="skipApiKey()">Continuar sin IA</button>
    </div>
    <p id="apiKeyError" style="color:var(--danger);font-size:12px;margin-top:10px;display:none"></p>
  </div>
</div>

<!-- Modal Horario -->
<div class="modal-overlay" id="scheduleModal">
  <div class="modal-box">
    <h3>Agregar Clase</h3>
    <select id="scheduleDay">
      <option value="lunes">Lunes</option><option value="martes">Martes</option>
      <option value="miercoles">Miercoles</option><option value="jueves">Jueves</option>
      <option value="viernes">Viernes</option><option value="sabado">Sabado</option>
      <option value="domingo">Domingo</option>
    </select>
    <input type="time" id="scheduleStart" placeholder="Hora inicio">
    <input type="time" id="scheduleEnd" placeholder="Hora fin">
    <input type="text" id="scheduleCourse" placeholder="Nombre de la clase (ej. Robotica)">
    <div class="modal-actions">
      <button class="btn-primary" onclick="saveSchedule()">Guardar</button>
      <button class="btn-secondary" onclick="closeScheduleModal()">Cancelar</button>
    </div>
  </div>
</div>

<script>
const NOW = () => new Date().toLocaleTimeString('es',{hour:'2-digit',minute:'2-digit'});
document.getElementById('welcomeTime').textContent = NOW();

// ============================================
// USER ID - Identificador unico por sesion
// ============================================
function getOrCreateUserId() {
  let id = localStorage.getItem('aura_user_id');
  if (!id) {
    id = 'web_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now().toString(36);
    localStorage.setItem('aura_user_id', id);
  }
  return id;
}

let userId = getOrCreateUserId();
console.log('User ID:', userId);

let ws = null;
let isListening = false;
let recognition = null;
let waveTimer = null;
let userFacts = {};
let msgCount = 0;

const EMOTION_ICONS = {
  neutral: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="8" y1="15" x2="16" y2="15"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>',
  feliz: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>',
  triste: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M16 14s-1.5 2-4 2-4-2-4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>',
  enojado: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M16 14s-1.5 2-4 2-4-2-4-2"/><line x1="8" y1="8" x2="12" y2="11"/><line x1="16" y1="8" x2="12" y2="11"/></svg>',
  ansioso: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9 10h.01"/><path d="M15 10h.01"/><path d="M12 16v-1"/><path d="M8 16h8"/></svg>',
  cansado: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="8" y1="9" x2="10" y2="9"/><line x1="14" y1="9" x2="16" y2="9"/></svg>'
};

const EMOTION_CLASSES = {
  neutral: 'neutral', feliz: 'happy', triste: 'sad', 
  enojado: 'angry', ansioso: 'anxious', cansado: 'tired'
};

const FACT_LABELS = {
  user_name:'Nombre', user_age:'Edad', user_studies:'Dedicacion',
  user_job:'Trabajo', user_likes:'Gustos', user_dislikes:'Disgustos',
  favorite_subject:'Materia favorita', upcoming_exam:'Proximo examen', 
  user_goals:'Objetivos'
};

// ============================================
// VOZ (Text-to-Speech) - Web Speech API
// ============================================
function speakText(text) {
    if (!('speechSynthesis' in window)) {
        console.log('[TTS] Web Speech API no disponible');
        return;
    }
    
    // Cancelar cualquier utterance previa
    window.speechSynthesis.cancel();
    
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'es-ES';
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.volume = 1.0;
    
    // Intentar usar una voz en español
    const voices = window.speechSynthesis.getVoices();
    const spanishVoice = voices.find(v => v.lang.startsWith('es'));
    if (spanishVoice) {
        utterance.voice = spanishVoice;
    }
    
    window.speechSynthesis.speak(utterance);
}

// Precargar voces (Chrome las carga asíncronamente)
if ('speechSynthesis' in window) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.getVoices();
    };
}

// ============================================
// WebSocket
// ============================================
function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws/${userId}`);

  ws.onopen = () => {
    setConn(true);
    const apiKey = localStorage.getItem('groq_api_key');
    if (apiKey) {
      ws.send(JSON.stringify({type: 'config', api_key: apiKey}));
    } else {
      document.getElementById('apiKeyModal').classList.add('show');
    }
  };

  ws.onclose = () => {
    setConn(false);
    setTimeout(connect, 3000);
  };

  ws.onerror = (err) => {
    console.error('WebSocket error:', err);
    setConn(false);
  };

  ws.onmessage = (e) => handleMsg(JSON.parse(e.data));
}

function setConn(ok) {
  const dot = document.getElementById('connDot');
  const text = document.getElementById('connText');
  if (ok) {
    dot.classList.add('connected');
    text.textContent = 'Conectado';
  } else {
    dot.classList.remove('connected');
    text.textContent = 'Reconectando...';
  }
}

function handleMsg(d) {
  switch(d.type) {
    case 'greeting':
      removeTyping();
      addMsg(d.text, 'bot');
      speakText(d.text);  // VOZ
      if (d.emotion) updateEmotion(d.emotion);
      if (d.personality) updatePersonality(d.personality);
      if (d.user_facts) updateUserFacts(d.user_facts);
      animWave(true);
      setTimeout(() => animWave(false), Math.min(d.text.length * 70, 3500));
      break;
      
    case 'response':
      removeTyping();
      addMsg(d.text, 'bot');
      speakText(d.text);  // VOZ
      if (d.emotion) updateEmotion(d.emotion);
      if (d.personality) updatePersonality(d.personality);
      if (d.user_facts) updateUserFacts(d.user_facts);
      animWave(true);
      setTimeout(() => animWave(false), Math.min(d.text.length * 70, 3500));
      if (d.text.toLowerCase().includes('tarea')) loadTasks();
      break;
      
    case 'spontaneous':
      addMsg(d.text, 'bot');
      speakText(d.text);  // VOZ
      animWave(true);
      setTimeout(() => animWave(false), 2500);
      break;
      
    case 'status':
      if (d.status === 'thinking') {
        showTyping(d.hint || '');
      } else {
        removeTyping();
        updateStatus(d.status);
      }
      break;
      
    case 'system':
      addMsg(d.message, 'bot');
      if (d.personality) updatePersonality(d.personality);
      break;
      
    case 'crisis':
      document.getElementById('crisisAlert').classList.add('show');
      break;
      
    case 'tasks_update':
      loadTasks();
      break;
      
    case 'user_facts':
      updateUserFacts(d.data);
      break;
      
    case 'error':
      removeTyping();
      addMsg('Error: ' + d.text, 'bot');
      updateStatus('error');
      break;
  }
}

function updateStatus(status) {
  const el = document.getElementById('auraStatus');
  el.className = 'status-text';
  switch(status) {
    case 'thinking': el.classList.add('thinking'); el.textContent = 'AURA esta pensando...'; break;
    case 'speaking': el.classList.add('speaking'); el.textContent = 'AURA esta hablando...'; break;
    case 'idle': el.textContent = 'AURA esta lista'; break;
    case 'error': el.classList.add('error'); el.textContent = 'Error de conexion'; break;
    default: el.textContent = 'AURA esta lista';
  }
}

// ============================================
// Mensajes
// ============================================
function send(text) {
  document.getElementById('msgInput').value = text;
  sendMsg();
}

function sendMsg() {
  const inp = document.getElementById('msgInput');
  const text = inp.value.trim();
  if (!text) return;

  if (!ws || ws.readyState !== WebSocket.OPEN) {
    addMsg('Desconectado. Reconectando...', 'bot');
    connect();
    return;
  }

  addMsg(text, 'user');
  ws.send(JSON.stringify({type:'text', text}));
  inp.value = '';
  msgCount++;

  document.getElementById('crisisAlert').classList.remove('show');
}

function onKey(e) { if (e.key === 'Enter') sendMsg(); }

function addMsg(text, who) {
  const box = document.getElementById('messages');
  const d = document.createElement('div');
  d.className = `message ${who}`;
  // FIX: <<span> corregido a <span>
  d.innerHTML = `<div class="bubble">${esc(text)}<span class="message-time">${NOW()}</span></div>`;
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
}

let typingEl = null;
function showTyping(hint) {
  removeTyping();
  const box = document.getElementById('messages');
  typingEl = document.createElement('div');
  typingEl.className = 'message bot';
  typingEl.innerHTML = `<div class="bubble"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>${hint ? `<span class="typing-hint">${esc(hint)}</span>` : ''}</div></div>`;
  box.appendChild(typingEl);
  box.scrollTop = box.scrollHeight;
  updateStatus('thinking');
}

function removeTyping() {
  if (typingEl) { typingEl.remove(); typingEl = null; }
}

function esc(t) {
  const d = document.createElement('div');
  d.textContent = t;
  return d.innerHTML;
}

// ============================================
// Emociones
// ============================================
function updateEmotion(e) {
  if (!e) return;
  const mood = e.mood || 'neutral';
  const icon = document.getElementById('emoIcon');
  const name = document.getElementById('emoName');
  const secondary = document.getElementById('emoSecondary');
  const fill = document.getElementById('emoFill');
  const badge = document.getElementById('trendBadge');

  icon.innerHTML = EMOTION_ICONS[mood] || EMOTION_ICONS.neutral;
  icon.className = 'emotion-icon ' + (EMOTION_CLASSES[mood] || 'neutral');
  name.textContent = mood.charAt(0).toUpperCase() + mood.slice(1);
  secondary.textContent = e.secondary_mood ? `con rasgos de ${e.secondary_mood}` : '';

  const score = e.score ?? e.sentiment_score ?? 0;
  const pct = Math.round(((score + 1) / 2) * 100);
  fill.style.width = pct + '%';
  fill.className = 'sentiment-fill ' + (score > 0.2 ? 'positive' : score < -0.2 ? 'negative' : 'neutral');

  const trend = e.trend || 'estable';
  badge.textContent = trend;
  badge.className = 'trend-badge ' + (trend === 'mejorando' ? 'up' : trend === 'empeorando' ? 'down' : 'flat');
}

function updatePersonality(p) {
  if (!p) return;
  if (p.name) document.getElementById('pName').textContent = p.name;
  if (p.attitude) document.getElementById('pAttitude').textContent = p.attitude;
  if (p.humor_level) document.getElementById('pHumor').textContent = p.humor_level;
  if (p.empathy_level) document.getElementById('pEmpathy').textContent = p.empathy_level;
  document.title = (p.name || 'AURA') + ' - Amigo Virtual';
}

function updateUserFacts(facts) {
  if (!facts) return;
  userFacts = {...userFacts, ...facts};
  const cont = document.getElementById('userFactsList');
  const entries = Object.entries(userFacts).filter(([,v]) => v);

  if (!entries.length) {
    cont.innerHTML = '<div class="empty-state">Cuentame cosas sobre ti</div>';
    return;
  }

  cont.innerHTML = entries.map(([k,v]) => 
    `<div class="list-item"><span style="color:var(--text-muted);min-width:80px;font-size:11px">${FACT_LABELS[k]||k}</span><span style="color:var(--text-primary);font-weight:500">${esc(v)}</span></div>`
  ).join('');
}

// ============================================
// API Key
// ============================================
function saveApiKey() {
  const key = document.getElementById('apiKeyInput').value.trim();
  const err = document.getElementById('apiKeyError');

  if (!key.startsWith('gsk_')) {
    err.textContent = 'API key invalida. Debe empezar con "gsk_"';
    err.style.display = 'block';
    return;
  }

  localStorage.setItem('groq_api_key', key);
  document.getElementById('apiKeyModal').classList.remove('show');

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({type: 'config', api_key: key}));
  }
}

function skipApiKey() {
  localStorage.removeItem('groq_api_key');
  document.getElementById('apiKeyModal').classList.remove('show');
}

// ============================================
// Horario
// ============================================
async function loadSchedule() {
  try {
    const r = await fetch('/api/schedule/weekly', {
      headers: {'x-user-id': userId}
    });
    const data = await r.json();
    const container = document.getElementById('scheduleList');
    const days = ['lunes','martes','miercoles','jueves','viernes','sabado','domingo'];
    const names = {lunes:'Lun',martes:'Mar',miercoles:'Mie',jueves:'Jue',viernes:'Vie',sabado:'Sab',domingo:'Dom'};

    let html = '';
    let any = false;

    for (const day of days) {
      const items = data[day] || [];
      if (!items.length) continue;
      any = true;
      html += `<div style="font-size:10px;color:var(--accent-light);font-weight:600;margin:8px 0 4px;text-transform:uppercase">${names[day]}</div>`;
      items.forEach((it, i) => {
        html += `<div class="list-item"><span class="list-item-time">${it.start}-${it.end}</span><span class="list-item-text">${esc(it.course||it.name||'Clase')}</span><button class="list-item-action" onclick="delClass('${day}',${i})">Eliminar</button></div>`;
      });
    }

    container.innerHTML = any ? html : '<div class="empty-state">Sin clases configuradas</div>';
  } catch(e) {
    console.error('Error cargando horario:', e);
  }
}

async function checkActive() {
  try {
    const r = await fetch('/api/schedule/current-course', {
      headers: {'x-user-id': userId}
    });
    const d = await r.json();
    const badge = document.getElementById('activeBadge');

    if (d.is_active) {
      badge.textContent = `En clase: ${d.course}`;
      badge.className = 'badge badge-danger';
    } else {
      badge.textContent = 'Libre - Puedo interactuar';
      badge.className = 'badge badge-success';
    }
  } catch(e) {
    console.error('Error verificando clase:', e);
  }
}

function openScheduleModal() { document.getElementById('scheduleModal').classList.add('show'); }

function closeScheduleModal() {
  document.getElementById('scheduleModal').classList.remove('show');
  document.getElementById('scheduleStart').value = '';
  document.getElementById('scheduleEnd').value = '';
  document.getElementById('scheduleCourse').value = '';
}

async function saveSchedule() {
  const day = document.getElementById('scheduleDay').value;
  const start = document.getElementById('scheduleStart').value;
  const end = document.getElementById('scheduleEnd').value;
  const course = document.getElementById('scheduleCourse').value.trim() || 'Clase';

  if (!start || !end) {
    alert('Selecciona hora de inicio y fin');
    return;
  }

  try {
    await fetch('/api/schedule', {
      method: 'POST',
      headers: {
        'Content-Type':'application/json',
        'x-user-id': userId
      },
      body: JSON.stringify({day, start, end, course})
    });
    closeScheduleModal();
    loadSchedule();
    checkActive();
  } catch(e) {
    console.error('Error guardando clase:', e);
  }
}

async function delClass(day, idx) {
  try {
    await fetch('/api/schedule/delete', {
      method: 'POST',
      headers: {
        'Content-Type':'application/json',
        'x-user-id': userId
      },
      body: JSON.stringify({day, index: idx})
    });
    loadSchedule();
    checkActive();
  } catch(e) {
    console.error('Error eliminando clase:', e);
  }
}

// ============================================
// Tareas
// ============================================
async function loadTasks() {
  try {
    const r = await fetch('/api/tasks');
    const tasks = await r.json();
    const cont = document.getElementById('taskList');

    if (!tasks || !tasks.length) {
      cont.innerHTML = '<div class="empty-state">Sin tareas pendientes</div>';
      return;
    }

    cont.innerHTML = tasks.map(t => 
      `<div class="list-item"><span class="list-item-text">${esc(t.title)}</span><button class="list-item-action" onclick="doneTask(${t.id})">Completar</button></div>`
    ).join('');
  } catch(e) {
    console.error('Error cargando tareas:', e);
  }
}

async function doneTask(id) {
  try {
    await fetch(`/api/tasks/${id}`, {method: 'DELETE'});
    loadTasks();
  } catch(e) {
    console.error('Error completando tarea:', e);
  }
}

// ============================================
// Microfono
// ============================================
function toggleMic() {
  if (!('webkitSpeechRecognition' in window)) {
    alert('Tu navegador no soporta reconocimiento de voz. Usa Chrome o Edge.');
    return;
  }
  isListening ? stopMic() : startMic();
}

function startMic() {
  recognition = new webkitSpeechRecognition();
  recognition.lang = 'es-ES';
  recognition.continuous = false;
  recognition.interimResults = false;

  recognition.onstart = () => {
    isListening = true;
    document.getElementById('micBtn').classList.add('listening');
    updateStatus('thinking');
  };

  recognition.onresult = (e) => {
    document.getElementById('msgInput').value = e.results[0][0].transcript;
    sendMsg();
    stopMic();
  };

  recognition.onerror = () => stopMic();
  recognition.onend = () => stopMic();
  recognition.start();
}

function stopMic() {
  if (recognition) recognition.stop();
  isListening = false;
  document.getElementById('micBtn').classList.remove('listening');
  updateStatus('idle');
}

// ============================================
// Animaciones
// ============================================
function animWave(on) {
  const bars = document.querySelectorAll('.wave-bar');
  if (on) {
    if (waveTimer) return;
    waveTimer = setInterval(() => {
      bars.forEach(b => { b.style.height = (Math.random() * 24 + 8) + 'px'; });
    }, 100);
    updateStatus('speaking');
  } else {
    clearInterval(waveTimer);
    waveTimer = null;
    bars.forEach(b => { b.style.height = '16px'; });
    updateStatus('idle');
  }
}

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
  document.querySelector('.sidebar-overlay').classList.toggle('show');
}

// ============================================
// Event Listeners
// ============================================
document.getElementById('apiKeyModal').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) skipApiKey();
});

document.getElementById('scheduleModal').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeScheduleModal();
});

document.addEventListener('DOMContentLoaded', () => {
  connect();
  loadSchedule();
  loadTasks();
  checkActive();
  setInterval(checkActive, 60000);
  setInterval(loadTasks, 30000);
});
</script>
</body>
</html>"""

# ------------------------------------------------------------------
# Endpoints REST
# ------------------------------------------------------------------
@app.get("/")
async def index():
    return HTMLResponse(HTML_PAGE)

@app.get("/api/schedule")
async def get_schedule():
    if aura_instances:
        aura = next(iter(aura_instances.values()))
        return aura.scheduler.get_schedule()
    return []

@app.post("/api/schedule")
async def add_schedule(request: Request):
    data = await request.json()
    if aura_instances:
        aura = next(iter(aura_instances.values()))
        aura.scheduler.add_active_hour(
            day=data.get('day', 'lunes'),
            start=data['start'],
            end=data['end'],
            name=data.get('course', data.get('name', 'Clase')),
            course=data.get('course', '')
        )
    return {"success": True}

@app.delete("/api/schedule/{index}")
async def delete_schedule(index: int):
    if aura_instances:
        aura = next(iter(aura_instances.values()))
        aura.scheduler.remove_active_hour(index)
    return {"success": True}

@app.get("/api/schedule/active")
async def is_active():
    if aura_instances:
        aura = next(iter(aura_instances.values()))
        return {
            "is_active": aura.scheduler.is_in_active_hours(),
            "current_hour": datetime.now().strftime("%H:%M")
        }
    return {"is_active": False, "current_hour": ""}

@app.get("/api/schedule/weekly")
async def get_weekly_schedule():
    if aura_instances:
        aura = next(iter(aura_instances.values()))
        return aura.scheduler.get_weekly_schedule()
    return {}

@app.get("/api/schedule/current-course")
async def get_current_course():
    if aura_instances:
        aura = next(iter(aura_instances.values()))
        return {
            "is_active": aura.scheduler.is_in_active_hours(),
            "course": aura.scheduler.get_current_course(),
            "current_hour": datetime.now().strftime("%H:%M")
        }
    return {"is_active": False, "course": "", "current_hour": ""}

@app.post("/api/schedule/delete")
async def delete_schedule_item(request: Request):
    data = await request.json()
    day, index = data.get('day'), data.get('index')
    if aura_instances and day is not None and index is not None:
        aura = next(iter(aura_instances.values()))
        items = aura.scheduler.get_schedule()
        items_for_day = [i for i, item in enumerate(items) if item.get('day') == day]
        if index < len(items_for_day):
            aura.scheduler.remove_active_hour(items_for_day[index])
    return {"success": True}

@app.get("/api/tasks")
async def get_tasks():
    if aura_instances:
        aura = next(iter(aura_instances.values()))
        return aura.tasks.get_pending()
    return []

@app.delete("/api/tasks/{task_id}")
async def complete_task(task_id: int):
    if aura_instances:
        aura = next(iter(aura_instances.values()))
        aura.tasks.complete(task_id)
    return {"success": True}

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

# ------------------------------------------------------------------
# WebSocket con user_id + Supabase
# ------------------------------------------------------------------
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
                
                await manager.send_message({
                    "type": "greeting",
                    "text": greeting,
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

            # Mensaje de chat
            if msg_type == "text":
                if aura is None:
                    aura = get_aura(user_id)
                
                user_text = data.get("text", "").strip()
                if not user_text:
                    continue

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

                    # Enviar respuesta
                    await manager.send_message({
                        "type": "response",
                        "text": response,
                        "emotion": emotion,
                        "personality": aura.personality,
                        "timestamp": datetime.now().isoformat()
                    }, websocket)

                    # Enviar facts actualizados
                    if hasattr(aura.brain, 'get_user_facts'):
                        facts = aura.brain.get_user_facts()
                        if facts:
                            await manager.send_message({
                                "type": "user_facts",
                                "data": {k: v["value"] for k, v in facts.items()}
                            }, websocket)

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


def _get_thinking_hint(text: str) -> str:
    """Devuelve un hint contextual para mostrar mientras AURA piensa."""
    t = text.lower()
    if any(w in t for w in ['musica', 'cancion', 'reproduce', 'pon']):
        return 'Buscando musica...'
    if any(w in t for w in ['tarea', 'recuerdame', 'recordatorio']):
        return 'Gestionando tareas...'
    if any(w in t for w in ['triste', 'mal', 'llorar', 'solo']):
        return 'Pensando con cuidado...'
    if any(w in t for w in ['hora', 'tiempo', 'cuando']):
        return 'Consultando hora...'
    if any(w in t for w in ['comer', 'desayuno', 'almuerzo', 'cena']):
        return 'Pensando en algo rico...'
    return 'Pensando...'


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
    print("AURA WEB v3 + Supabase — " + ("PRODUCCION" if is_prod else "DESARROLLO"))
    print("="*50)
    print("Memoria por usuario: activada")
    print("API key por usuario: activada")
    print("Supabase sync: activado")
    if not is_prod:
        print("Interfaz: http://localhost:8000")
    print("Presiona CTRL+C para detener\n")

    uvicorn.run(app, host="0.0.0.0", port=port)