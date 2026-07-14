# core/self_awareness.py
# Autoconocimiento y reflexión de AURA

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

class SelfAwareness:
    """
    Gestiona el autoconocimiento de AURA:
    - Registro de interacciones
    - Patrones de conversación
    - Estado emocional a largo plazo
    - Metas de mejora
    """
    
    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.data_dir = Path("data/self_awareness")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.data_file = self.data_dir / f"{user_id}.json"
        self.data = self._load_data()
    
    def _load_data(self) -> Dict:
        """Carga los datos de autoconocimiento"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return self._default_data()
    
    def _default_data(self) -> Dict:
        """Datos por defecto"""
        return {
            "created_at": datetime.now().isoformat(),
            "interaction_count": 0,
            "daily_interactions": [],
            "topics_discussed": {},
            "emotional_trend": [],
            "user_preferences": {},
            "learning_goals": [],
            "reflection_notes": []
        }
    
    def _save_data(self):
        """Guarda los datos"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
    
    def register_interaction(self, user_message: str, response: str, emotion: Optional[Dict] = None):
        """Registra una interacción"""
        self.data["interaction_count"] += 1
        
        # Registrar interacción diaria
        today = datetime.now().strftime("%Y-%m-%d")
        if not self.data["daily_interactions"] or self.data["daily_interactions"][-1]["date"] != today:
            self.data["daily_interactions"].append({
                "date": today,
                "count": 0
            })
        self.data["daily_interactions"][-1]["count"] += 1
        
        # Registrar temas
        for topic in self._extract_topics(user_message):
            if topic in self.data["topics_discussed"]:
                self.data["topics_discussed"][topic] += 1
            else:
                self.data["topics_discussed"][topic] = 1
        
        # Registrar emoción
        if emotion:
            self.data["emotional_trend"].append({
                "timestamp": datetime.now().isoformat(),
                "mood": emotion.get("mood", "neutral"),
                "score": emotion.get("score", 0)
            })
            # Mantener solo los últimos 100 registros
            if len(self.data["emotional_trend"]) > 100:
                self.data["emotional_trend"] = self.data["emotional_trend"][-100:]
        
        self._save_data()
    
    def _extract_topics(self, text: str) -> List[str]:
        """Extrae temas de un texto"""
        text = text.lower()
        topics = []
        
        topic_keywords = {
            "saludo": ["hola", "buenos días", "buenas", "hey", "hello"],
            "despedida": ["adiós", "chao", "hasta luego", "nos vemos"],
            "estado_animo": ["triste", "feliz", "enojado", "ansioso", "emocionado"],
            "tareas": ["tarea", "deber", "trabajo", "proyecto"],
            "estudio": ["estudiar", "clase", "examen", "aprender"],
            "musica": ["música", "canción", "escuchar", "melodía"],
            "clima": ["clima", "lluvia", "calor", "frío", "soleado"],
            "tiempo": ["hora", "día", "fecha", "mañana", "ayer"],
            "comida": ["comer", "desayuno", "almuerzo", "cena", "hamburguesa"],
            "familia": ["mamá", "papá", "hermano", "familia"],
            "amigos": ["amigo", "amiga", "compañero"],
            "salud": ["salud", "enfermo", "dolor", "cuidado"]
        }
        
        for topic, keywords in topic_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    topics.append(topic)
                    break
        
        return topics
    
    def get_emotional_summary(self) -> Dict:
        """Resumen del estado emocional"""
        if not self.data["emotional_trend"]:
            return {"message": "Aún no hay suficientes datos emocionales"}
        
        recent = self.data["emotional_trend"][-30:]
        moods = {}
        avg_score = 0
        
        for entry in recent:
            mood = entry.get("mood", "neutral")
            moods[mood] = moods.get(mood, 0) + 1
            avg_score += entry.get("score", 0)
        
        if recent:
            avg_score = avg_score / len(recent)
        
        dominant_mood = max(moods.items(), key=lambda x: x[1])[0] if moods else "neutral"
        
        return {
            "dominant_mood": dominant_mood,
            "mood_distribution": moods,
            "avg_sentiment_score": round(avg_score, 2),
            "total_interactions": self.data["interaction_count"],
            "samples": len(recent)
        }
    
    def get_learning_goals(self) -> List[str]:
        """Obtiene las metas de aprendizaje"""
        return self.data.get("learning_goals", [])
    
    def add_learning_goal(self, goal: str):
        """Agrega una meta de aprendizaje"""
        if goal not in self.data["learning_goals"]:
            self.data["learning_goals"].append(goal)
            self._save_data()
    
    def get_reflection(self) -> str:
        """Genera una reflexión sobre las interacciones"""
        total = self.data["interaction_count"]
        if total == 0:
            return "Aún no hemos tenido conversaciones profundas. ¿Qué te gustaría hablar?"
        
        topics = sorted(self.data["topics_discussed"].items(), key=lambda x: x[1], reverse=True)
        top_topics = [t[0] for t in topics[:3]]
        
        return f"Hemos tenido {total} interacciones. Los temas que más hemos hablado son: {', '.join(top_topics)}"