"""
GROQ MANAGER v3
Maneja la API de Groq con soporte para API key por usuario
- Carga desde Supabase si está disponible
- Fallback a variables de entorno
"""

import os
from typing import List, Dict, Optional

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# Importar Supabase si está disponible
try:
    from core.supabase_client import get_supabase_manager
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


class GroqManager:
    def __init__(self, user_id: str = "default", api_key: str = None):
        self.user_id = user_id
        self.api_key = api_key or self._load_api_key()
        self.model = "llama-3.1-8b-instant"  # ← Modelo actualizado
        self.client = None
        self._enabled = False
        
        if self.api_key and GROQ_AVAILABLE:
            self._init_client()
    
    def _load_api_key(self) -> str:
        """Carga API key desde múltiples fuentes en orden de prioridad."""
        # 1. Supabase (prioridad alta - API key del usuario)
        if SUPABASE_AVAILABLE:
            try:
                supabase = get_supabase_manager()
                if supabase.is_connected():
                    key = supabase.get_api_key(self.user_id)
                    if key:
                        print(f"[GroqManager] API key cargada desde Supabase para {self.user_id}")
                        return key
            except Exception as e:
                print(f"[GroqManager] Error cargando de Supabase: {e}")
        
        # 2. UserConfig local
        try:
            from core.user_config import get_user_config
            user_config = get_user_config(self.user_id)
            key = user_config.get_groq_api_key()
            if key:
                return key
        except Exception:
            pass
        
        # 3. Variable de entorno global (fallback)
        env_key = os.getenv("GROQ_API_KEY", "")
        if env_key:
            print(f"[GroqManager] Usando API key global de entorno")
        
        return env_key
    
    def _init_client(self):
        """Inicializa el cliente de Groq."""
        try:
            self.client = Groq(api_key=self.api_key)
            self._enabled = True
        except Exception as e:
            print(f"[GroqManager] Error inicializando cliente: {e}")
            self._enabled = False
    
    def set_api_key(self, api_key: str):
        """Establece una nueva API key."""
        self.api_key = api_key
        if api_key and GROQ_AVAILABLE:
            self._init_client()
        else:
            self._enabled = False
        
        # Sincronizar con Supabase
        if SUPABASE_AVAILABLE:
            try:
                supabase = get_supabase_manager()
                if supabase.is_connected():
                    supabase.save_api_key(self.user_id, api_key)
            except Exception as e:
                print(f"[GroqManager] Error sincronizando API key: {e}")
    
    def is_enabled(self) -> bool:
        """Verifica si Groq está habilitado."""
        return self._enabled and self.client is not None
    
    def chat(self, messages: List[Dict], temperature: float = 0.7, max_tokens: int = 500) -> Optional[str]:
        """Envia mensajes a Groq y retorna la respuesta."""
        if not self.is_enabled():
            return None
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=0.9
            )
            
            if response and response.choices:
                return response.choices[0].message.content.strip()
            return None
            
        except Exception as e:
            print(f"[GroqManager] Error en chat: {e}")
            if "decommissioned" in str(e).lower() or "model" in str(e).lower():
                print(f"[GroqManager] El modelo {self.model} puede estar descontinuado. Prueba con otro modelo.")
            if "auth" in str(e).lower() or "key" in str(e).lower():
                self._enabled = False
            return None
    
    def set_model(self, model: str):
        """Cambia el modelo de Groq."""
        valid_models = [
            'llama-3.1-8b-instant',
            'llama-3.3-70b-versatile',
            'mixtral-8x7b-32768',
            'gemma2-9b-it'
        ]
        if model in valid_models:
            self.model = model
            return True
        return False


# Cache de managers por usuario
_groq_managers = {}

def get_user_groq_manager(user_id: str = "default") -> GroqManager:
    """Obtiene o crea un manager de Groq para un usuario."""
    if user_id not in _groq_managers:
        _groq_managers[user_id] = GroqManager(user_id=user_id)
    return _groq_managers[user_id]

def clear_groq_manager(user_id: str):
    """Limpia el manager de un usuario."""
    if user_id in _groq_managers:
        del _groq_managers[user_id]