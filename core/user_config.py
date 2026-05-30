"""
👤 CONFIGURACIÓN DE USUARIO
Maneja el perfil y configuración de Groq por usuario
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

class UserConfig:
    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.config_path = Path(f"config/users/{user_id}/user_profile.json")
        self.config = self.load_config()
    
    def load_config(self) -> Dict:
        """Carga la configuración del usuario"""
        # Primero intentar cargar configuración específica del usuario
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Si no existe, cargar la configuración por defecto
        main_path = Path("config/user_profile.json")
        if main_path.exists():
            with open(main_path, 'r', encoding='utf-8') as f:
                default_config = json.load(f)
                # Asegurar que tiene la estructura de Groq
                if "groq_config" not in default_config:
                    default_config["groq_config"] = {
                        "api_key": "",
                        "model": "llama3-8b-8192",
                        "use_groq": False,
                        "last_validated": None,
                        "usage_stats": {
                            "total_requests": 0,
                            "total_tokens": 0,
                            "last_request": None
                        }
                    }
                return default_config
        
        # Crear configuración por defecto
        return self._create_default_config()
    
    def _create_default_config(self) -> Dict:
        """Crea configuración por defecto"""
        return {
            "user_name": "Amigo",
            "preferred_language": "es",
            "music_taste": ["lo-fi", "pop", "rock suave"],
            "study_subjects": [],
            "common_moods": [],
            "important_dates": {},
            "created_at": datetime.now().isoformat(),
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
                "use_emojis": True,
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
        """Guarda la configuración en el directorio del usuario"""
        # Crear directorio de usuario si no existe
        user_dir = self.config_path.parent
        user_dir.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    # ═══════════════════════════════════════════════════════
    # MÉTODOS PARA GROQ
    # ═══════════════════════════════════════════════════════
    
    def get_groq_api_key(self) -> str:
        """Obtiene la API key de Groq del usuario"""
        return self.config.get("groq_config", {}).get("api_key", "")
    
    def set_groq_api_key(self, api_key: str):
        """Establece la API key de Groq"""
        if "groq_config" not in self.config:
            self.config["groq_config"] = {}
        
        self.config["groq_config"]["api_key"] = api_key
        self.config["groq_config"]["use_groq"] = bool(api_key)
        self.config["groq_config"]["last_validated"] = datetime.now().isoformat()
        self.save_config()
    
    def get_groq_model(self) -> str:
        """Obtiene el modelo de Groq configurado"""
        return self.config.get("groq_config", {}).get("model", "llama3-8b-8192")
    
    def set_groq_model(self, model: str):
        """Cambia el modelo de Groq"""
        valid_models = [
            'llama3-8b-8192',
            'llama3-70b-8192',
            'mixtral-8x7b-32768',
            'gemma-7b-it'
        ]
        
        if model in valid_models:
            self.config["groq_config"]["model"] = model
            self.save_config()
            return True
        return False
    
    def is_groq_enabled(self) -> bool:
        """Verifica si Groq está habilitado para este usuario"""
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
        """Incrementa estadísticas de uso de Groq"""
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
        """Obtiene estadísticas de uso de Groq"""
        return self.config.get("groq_config", {}).get("usage_stats", {})
    
    # ═══════════════════════════════════════════════════════
    # MÉTODOS GENERALES
    # ═══════════════════════════════════════════════════════
    
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


# Instancias por usuario
_user_configs = {}

def get_user_config(user_id: str = "default") -> UserConfig:
    """Obtiene la configuración de un usuario"""
    if user_id not in _user_configs:
        _user_configs[user_id] = UserConfig(user_id)
    return _user_configs[user_id]