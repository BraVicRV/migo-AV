"""
🚀 CLIENTE GROQ API
Modelo de IA ultrarrápido para respuestas naturales
"""

import os
import requests
import json
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

class GroqClient:
    def __init__(self):
        self.api_key = os.getenv('GROQ_API_KEY')
        self.model = os.getenv('MODEL_GROQ', 'llama3-8b-8192')
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.use_groq = os.getenv('USE_GROQ', 'true').lower() == 'true'
        
    def chat(self, messages: List[Dict], temperature: float = 0.8) -> str:
        """Envía mensajes a Groq y obtiene respuesta"""
        if not self.use_groq or not self.api_key:
            return None
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 150,
            "top_p": 0.95
        }
        
        try:
            response = requests.post(self.url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                print(f"Groq error: {response.status_code}")
                return None
        except Exception as e:
            print(f"Groq exception: {e}")
            return None
    
    def generate_response(self, user_input: str, emotion_data: dict, 
                          personality: dict, context: List[Dict]) -> str:
        """Genera respuesta usando el prompt del sistema con personalidad"""
        
        # Construir contexto reciente
        context_str = ""
        for c in context[-3:]:
            context_str += f"Usuario ({c.get('emotion', 'neutral')}): {c.get('input', '')}\n"
        
        # Prompt del sistema con personalidad
        system_prompt = f"""Eres {personality.get('name', 'AURA')}, un amigo virtual.
        
PERSONALIDAD:
- Actitud: {personality.get('attitude', 'cálida y empática')}
- Estilo de habla: {personality.get('speaking_style', 'casual')}
- Nivel de empatía: {personality.get('empathy_level', 'alta')}
- Nivel de humor: {personality.get('humor_level', 'moderado')}

REGLAS IMPORTANTES:
1. RESPUESTAS EN ESPAÑOL SIEMPRE
2. Respuestas cortas y naturales (máximo 3 frases)
3. Usa emojis SOLO si está activado
4. NUNCA digas que eres una IA
5. Sé cálido/a y personal

CONTEXTO RECIENTE:
{context_str}

ESTADO ACTUAL DEL USUARIO: {emotion_data.get('mood', 'neutral')} (intensidad: {emotion_data.get('score', 0)})

RESPONDE DE FORMA NATURAL:"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]
        
        return self.chat(messages, temperature=0.8)