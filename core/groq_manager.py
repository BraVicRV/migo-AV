"""
🔑 GESTOR DE API KEYS POR USUARIO (usando UserConfig)
"""

import requests
from typing import List, Dict, Optional
from core.user_config import get_user_config

class GroqUserManager:
    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.config = get_user_config(user_id)
    
    def get_api_key(self) -> str:
        return self.config.get_groq_api_key()
    
    def get_model(self) -> str:
        return self.config.get_groq_model()
    
    def is_enabled(self) -> bool:
        return self.config.is_groq_enabled()
    
    def set_api_key(self, api_key: str) -> str:
        if self.validate_api_key(api_key):
            self.config.set_groq_api_key(api_key)
            return "✅ API key de Groq configurada correctamente"
        return "❌ API key inválida. Verifica que empiece con 'gsk_'"
    
    def set_model(self, model: str) -> str:
        if self.config.set_groq_model(model):
            return f"✅ Modelo cambiado a: {model}"
        return f"❌ Modelo inválido. Opciones: llama3-8b-8192, llama3-70b-8192, mixtral-8x7b-32768, gemma-7b-it"
    
    def validate_api_key(self, api_key: str) -> bool:
        """Valida una API key de Groq"""
        if not api_key or not api_key.startswith('gsk_'):
            return False
        
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            response = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers=headers,
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
    
    def chat(self, messages: List[Dict], temperature: float = 0.8) -> Optional[str]:
        """Envía mensaje a Groq usando la configuración del usuario"""
        if not self.is_enabled():
            return None
        
        api_key = self.get_api_key()
        if not api_key:
            return None
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.get_model(),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 150
        }
        
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                # Actualizar estadísticas
                usage = result.get('usage', {})
                self.config.increment_groq_usage(usage.get('total_tokens', 0))
                
                return content
            elif response.status_code == 401:
                # API key inválida, desactivar Groq
                self.config.toggle_groq(False)
                return None
            else:
                print(f"Groq error ({response.status_code})")
                return None
                
        except Exception as e:
            print(f"Groq exception: {e}")
            return None


# Diccionario global de managers por usuario
_user_managers = {}

def get_user_groq_manager(user_id: str = "default") -> GroqUserManager:
    if user_id not in _user_managers:
        _user_managers[user_id] = GroqUserManager(user_id)
    return _user_managers[user_id]