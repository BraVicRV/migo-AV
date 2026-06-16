"""
CONFIGURACION DE USUARIO v3
Maneja el perfil y configuracion por usuario
- Local: SQLite + archivos JSON
- Cloud: Supabase (sincronizacion)
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

# Importar Supabase si está disponible
try:
    from core.supabase_client import get_supabase_manager
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


class UserConfig:
    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        # Configuracion local
        self.config_dir = Path(f"config/users/{user_id}")
        self.config_path = self.config_dir / "user_profile.json"
        
        # Supabase para sincronizacion (ANTES de load_config)
        self.supabase = get_supabase_manager() if SUPABASE_AVAILABLE else None
        
        # Ahora cargar configuracion
        self.config = self.load_config()
    
    def load_config(self) -> Dict:
        """Carga la configuracion del usuario (local primero, cloud como fallback)"""
        # 1. Intentar cargar configuracion local
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    local_config = json.load(f)
                
                # Si hay Supabase, verificar si hay version mas reciente en la nube
                if self.supabase and self.supabase.is_connected():
                    try:
                        cloud_config = self.supabase.load_user_profile(self.user_id)
                        if cloud_config:
                            # Comparar timestamps
                            local_time = local_config.get("updated_at", "2000-01-01")
                            cloud_time = cloud_config.get("updated_at", "2000-01-01")
                            
                            if cloud_time > local_time:
                                # Cloud es mas reciente, usar cloud
                                self._save_local_config(cloud_config)
                                return cloud_config
                    except Exception as e:
                        print(f"[UserConfig] Error cargando de Supabase: {e}")
                
                return local_config
            except Exception as e:
                print(f"[UserConfig] Error cargando local: {e}")
        
        # 2. Si no hay local, intentar cargar desde Supabase
        if self.supabase and self.supabase.is_connected():
            try:
                cloud_config = self.supabase.load_user_profile(self.user_id)
                if cloud_config:
                    # Guardar localmente para proximas veces
                    self._save_local_config(cloud_config)
                    return cloud_config
            except Exception as e:
                print(f"[UserConfig] Error cargando de Supabase: {e}")
        
        # 3. Crear configuracion por defecto
        return self._create_default_config()
    
    def _create_default_config(self) -> Dict:
        """Crea configuracion por defecto para nuevo usuario"""
        return {
            "user_id": self.user_id,
            "user_name": "Amigo",
            "preferred_language": "es",
            "music_taste": ["lo-fi", "pop", "rock suave"],
            "study_subjects": [],
            "common_moods": [],
            "important_dates": {},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "groq_config": {
                "api_key": "",
                "model": "llama3-8b-8192",
                "use_groq": False,
                "last_validated": None,
                "usage_stats": {
                    "total_requests": 0,
                    "total_tokens": 0,
                    "last_request": None
                }
            },
            "ai_preferences": {
                "response_length": "medio",
                "use_emojis": False,
                "spontaneous_interactions": True,
                "reminder_frequency": "normal"
            },
            "privacy_settings": {
                "save_conversations": True,
                "share_anonymous_stats": False,
                "local_processing_only": False
            }
        }
    
    def save_config(self):
        """Guarda la configuracion local y en Supabase"""
        self.config["updated_at"] = datetime.now().isoformat()
        
        # Guardar local
        self._save_local_config(self.config)
        
        # Sincronizar con Supabase
        if self.supabase and self.supabase.is_connected():
            try:
                self.supabase.save_user_profile(self.user_id, self.config)
                print(f"[UserConfig] Config sincronizada a Supabase para {self.user_id}")
            except Exception as e:
                print(f"[UserConfig] Error sincronizando a Supabase: {e}")
    
    def _save_local_config(self, config: Dict):
        """Guarda configuracion en disco local"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    # ============================================================
    # METODOS PARA GROQ (API KEY POR USUARIO)
    # ============================================================
    
    def get_groq_api_key(self) -> str:
        """Obtiene la API key de Groq del usuario (local o Supabase)"""
        # 1. Intentar desde Supabase primero (mas seguro)
        if self.supabase and self.supabase.is_connected():
            try:
                cloud_key = self.supabase.get_api_key(self.user_id)
                if cloud_key:
                    # Actualizar local
                    self.config["groq_config"]["api_key"] = cloud_key
                    self._save_local_config(self.config)
                    return cloud_key
            except Exception as e:
                print(f"[UserConfig] Error obteniendo API key de Supabase: {e}")
        
        # 2. Fallback a local
        return self.config.get("groq_config", {}).get("api_key", "")
    
    def set_groq_api_key(self, api_key: str):
        """Establece la API key de Groq para este usuario"""
        if "groq_config" not in self.config:
            self.config["groq_config"] = {}
        
        self.config["groq_config"]["api_key"] = api_key
        self.config["groq_config"]["use_groq"] = bool(api_key)
        self.config["groq_config"]["last_validated"] = datetime.now().isoformat()
        
        # Guardar local y en Supabase
        self.save_config()
        
        # Guardar específicamente en tabla de API keys
        if self.supabase and self.supabase.is_connected():
            try:
                self.supabase.save_api_key(self.user_id, api_key)
            except Exception as e:
                print(f"[UserConfig] Error guardando API key en Supabase: {e}")
    
    def get_groq_model(self) -> str:
        """Obtiene el modelo de Groq configurado"""
        return self.config.get("groq_config", {}).get("model", "llama3-8b-8192")
        
    def set_groq_model(self, model: str):
        """Cambia el modelo de Groq"""
        valid_models = [
            'llama-3.1-8b-instant',
            'llama-3.3-70b-versatile',
            'mixtral-8x7b-32768',
            'gemma2-9b-it'
        ]
        if model in valid_models:
            self.config["groq_config"]["model"] = model
            self.save_config()
            return True
        return False
    
    def is_groq_enabled(self) -> bool:
        """Verifica si Groq esta habilitado para este usuario"""
        groq_config = self.config.get("groq_config", {})
        return groq_config.get("use_groq", False) and bool(groq_config.get("api_key", ""))
    
    def toggle_groq(self, enabled: bool = None):
        """Activa o desactiva Groq"""
        if enabled is None:
            enabled = not self.is_groq_enabled()
        
        self.config["groq_config"]["use_groq"] = enabled
        self.save_config()
        return enabled
    
    def increment_groq_usage(self, tokens: int = 0):
        """Incrementa estadisticas de uso de Groq"""
        groq_config = self.config.get("groq_config", {})
        
        if "usage_stats" not in groq_config:
            groq_config["usage_stats"] = {
                "total_requests": 0,
                "total_tokens": 0,
                "last_request": None
            }
        
        groq_config["usage_stats"]["total_requests"] += 1
        groq_config["usage_stats"]["total_tokens"] += tokens
        groq_config["usage_stats"]["last_request"] = datetime.now().isoformat()
        
        self.save_config()
    
    def get_groq_usage_stats(self) -> Dict:
        """Obtiene estadisticas de uso de Groq"""
        return self.config.get("groq_config", {}).get("usage_stats", {})
    
    # ============================================================
    # METODOS GENERALES
    # ============================================================
    
    def get_user_name(self) -> str:
        return self.config.get("user_name", "Amigo")
    
    def set_user_name(self, name: str):
        self.config["user_name"] = name
        self.save_config()
    
    def get_preference(self, key: str, default=None):
        return self.config.get("ai_preferences", {}).get(key, default)
    
    def set_preference(self, key: str, value):
        if "ai_preferences" not in self.config:
            self.config["ai_preferences"] = {}
        self.config["ai_preferences"][key] = value
        self.save_config()
    
    def get_music_taste(self) -> list:
        return self.config.get("music_taste", [])
    
    def add_music_genre(self, genre: str):
        if genre not in self.config.get("music_taste", []):
            self.config.setdefault("music_taste", []).append(genre)
            self.save_config()


# Instancias por usuario (cache)
_user_configs = {}

def get_user_config(user_id: str = "default") -> UserConfig:
    """Obtiene la configuracion de un usuario"""
    if user_id not in _user_configs:
        _user_configs[user_id] = UserConfig(user_id)
    return _user_configs[user_id]

def clear_user_config(user_id: str):
    """Limpia la configuracion de un usuario del cache"""
    if user_id in _user_configs:
        del _user_configs[user_id]