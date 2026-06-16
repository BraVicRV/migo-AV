"""
AMIGO VIRTUAL PERSONALIZABLE v2
- Memoria por usuario (brain_{user_id}.db)
- Motor de curiosidad para inicio proactivo
- API key de Groq por usuario
- Resumenes inteligentes con seguimiento
"""

import asyncio
import json
import threading
import time
import random
import re
import webbrowser
import urllib.parse
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Dict, List, Optional

from core.brain import VirtualBrain
from core.scheduler import RoutineScheduler
from core.emotions import EmotionAnalyzer
from modules.music import MusicRecommender
from modules.tasks import TaskManager
from modules.study import StudyAssistant

# Import opcional de VoiceManager (solo modo consola, no en web)
try:
    from core.voice import VoiceManager
    VOICE_AVAILABLE = True
    print("[Voice] Módulo de voz cargado correctamente")
except ImportError as e:
    VOICE_AVAILABLE = False
    VoiceManager = None
    print(f"[Voice] Módulo de voz no disponible: {e}")
    print("[Voice] Usando solo modo web (voz por navegador)")


# ------------------------------------------------------------------
# Mapa de compatibilidad: mood -> acciones preferidas
# ------------------------------------------------------------------
MOOD_ACTION_PRIORITY = {
    "triste":    ["give_encouragement_by_mood", "send_encouragement", "ask_how_are_you"],
    "ansioso":   ["give_encouragement_by_mood", "send_encouragement", "remember_routine"],
    "cansado":   ["give_encouragement_by_mood", "remind_pending_tasks", "recommend_meal"],
    "enojado":   ["give_encouragement_by_mood", "ask_how_are_you", "send_encouragement"],
    "feliz":     ["ask_how_are_you", "recommend_meal", "remind_pending_tasks"],
    "emocionado":["ask_how_are_you", "remind_pending_tasks", "recommend_meal"],
    "neutral":   ["ask_how_are_you", "remind_pending_tasks", "recommend_meal", "remember_routine"],
}

ACTION_COOLDOWN = {
    "give_encouragement_by_mood": 1800,
    "send_encouragement":         2400,
    "ask_how_are_you":            1200,
    "remind_pending_tasks":       900,
    "recommend_meal":             3600,
    "remember_routine":           1800,
}


class AmigoVirtual:
    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.name = "AURA"
        self.running = False
        self.user_name = "Amigo"
        self.pending_callbacks = []
        self.last_recommendations = []

        # Cerebro con memoria separada por usuario
        self.brain = VirtualBrain(user_id=self.user_id, amigo_instance=self)

        # Voz: solo en modo consola, NO en modo web
        if getattr(self, '_web_mode', False):
            self.voice = None
            print("[Voice] Modo web detectado, voz del sistema desactivada")
        elif VOICE_AVAILABLE:
            self.voice = VoiceManager()
            print("[Voice] Voz activada para modo consola")
        else:
            self.voice = None
            print("[Voice] Voz no disponible (modo silencioso)")

        self.scheduler = RoutineScheduler(self, user_id=self.user_id)
        self.emotions = EmotionAnalyzer()
        self.music = MusicRecommender()
        self.tasks = TaskManager(user_id=self.user_id)
        self.study = StudyAssistant()

        self.user_mood_history = []
        self.last_interaction = datetime.now()
        self._last_action_time: Dict[str, datetime] = {}
        self._proactive_thread = None
        self._crisis_count = 0  # Contador para evitar repetición

        self.load_config()

        print("{} esta despertando...".format(self.name))
        print("   Personalidad: {}".format(self.personality['attitude']))
        print("   Memoria: brain_{}.db".format(self.user_id))

    # ------------------------------------------------------------------
    # Wrapper para voz (solo en modo consola, no en web)
    # ------------------------------------------------------------------

    def _speak(self, text: str):
        """Wrapper para voz: solo en modo consola, NO en modo web"""
        if self.voice and not getattr(self, '_web_mode', False):
            try:
                self.voice.speak(text)
            except Exception as e:
                print(f"[Voice] Error: {e}")

    # ------------------------------------------------------------------
    # Configuracion
    # ------------------------------------------------------------------

    def load_config(self):
        config_path = Path("config/personality.json")
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                self.personality = json.load(f)
        else:
            self.personality = {
                "name": "AURA",
                "attitude": "calida y empatica",
                "voice_type": "femenina suave",
                "speaking_style": "casual pero respetuosa",
                "humor_level": "moderado",
                "empathy_level": "alta",
                "proactivity": "media",
                "music_genres": ["lo-fi", "pop", "rock suave"],
                "catchphrases": ["Que bueno verte!", "Cuentame todo", "Estoy aqui para ti"],
                "language_formality": "tu",
                "response_length": "medio",
                "use_emojis": False
            }
            self.save_config()

        self.name = self.personality["name"]

        # Cargar nombre desde el perfil del cerebro (memoria por usuario)
        profile = self.brain.user_profile.data
        if profile["basic_info"].get("name"):
            self.user_name = profile["basic_info"]["name"]

    def save_config(self):
        Path("config").mkdir(exist_ok=True)
        with open("config/personality.json", 'w', encoding='utf-8') as f:
            json.dump(self.personality, f, ensure_ascii=False, indent=2)

    def personalize(self, attribute: str, value):
        if attribute in self.personality:
            old = self.personality[attribute]
            self.personality[attribute] = value
            self.save_config()
            return "{} cambiado de '{}' a '{}'".format(attribute, old, value)
        return "Atributo '{}' no existe. Opciones: {}".format(attribute, list(self.personality.keys()))

    # ------------------------------------------------------------------
    # Inicio proactivo inteligente
    # ------------------------------------------------------------------

    def start(self) -> str:
        """
        Inicia AURA con saludo proactivo basado en memoria del usuario.
        Este metodo se llama cuando un usuario se conecta via WebSocket.
        """
        self.running = True
        self.setup_scheduled_routines()
        self.scheduler.start()

        # Generar saludo proactivo usando el motor de curiosidad del cerebro
        greeting = self.brain.generate_proactive_greeting()

        # Iniciar hilo de check-ins proactivos
        self._start_proactive_thread()

        return greeting

    def _start_proactive_thread(self):
        """Inicia hilo que envia mensajes proactivos cada cierto tiempo."""
        # Evitar múltiples hilos
        if self._proactive_thread and self._proactive_thread.is_alive():
            return

        def proactive_loop():
            while self.running:
                time.sleep(600)  # Verificar cada 10 minutos
                if not self.running:
                    continue

                # No interrumpir si esta en horario de clase
                if self.scheduler.is_in_active_hours():
                    continue

                # Generar check-in proactivo
                checkin = self.brain.generate_proactive_checkin()
                if checkin:
                    # En modo web, esto se enviaria via WebSocket
                    # Por ahora solo lo registramos
                    print(f"\n[PROACTIVO/{self.user_id}] {checkin}")

        self._proactive_thread = threading.Thread(target=proactive_loop, daemon=True)
        self._proactive_thread.start()

    def stop(self):
        """Detiene AURA."""
        self.running = False
        if self._proactive_thread:
            self._proactive_thread.join(timeout=2)
        self.scheduler.stop()

    # ------------------------------------------------------------------
    # Chat principal
    # ------------------------------------------------------------------

    async def chat(self, user_input: str) -> str:
        self.last_interaction = datetime.now()

        emotion_data = self.emotions.analyze(user_input)
        self.user_mood_history.append({
            "timestamp": datetime.now().isoformat(),
            "mood": emotion_data["mood"],
            "sentiment_score": emotion_data["score"]
        })

        # Detectar pesimismo en historial para ajustar respuesta
        pessimism = self.emotions.detect_pessimism_trend(threshold=-0.3, min_entries=3)
        if pessimism["is_pessimistic"] and emotion_data["mood"] in ["triste", "ansioso", "enojado", "cansado"]:
            # Añadir contexto de apoyo al emotion_data para que el brain lo use
            emotion_data["needs_support"] = True
            emotion_data["pessimism_severity"] = pessimism["severity"]

        # Guardar interaccion (con respuesta vacia inicial)
        self.brain.save_interaction(user_input, emotion_data)

        intent = self.detect_intent(user_input)

        if intent == "crisis":
            response = self.handle_crisis_support()
        elif intent == "gratitude":
            response = self.handle_gratitude()
        elif intent == "wellbeing_check":
            response = self.handle_wellbeing_check()
        elif intent == "music_request":
            response = await self.handle_music_request(user_input)
        elif intent == "music_stop":
            response = await self.handle_music_stop()
        elif intent == "task_add":
            response = await self.handle_task_add(user_input)
        elif intent == "list_tasks":
            response = await self.handle_list_tasks()
        elif intent == "add_class":
            response = await self.handle_add_class(user_input)
        elif intent == "list_classes":
            response = await self.handle_list_classes()
        elif intent == "study_mode":
            response = await self.handle_study_mode(user_input)
        elif intent == "advice_request":
            response = await self.handle_advice(user_input, emotion_data)
        elif intent == "personalization":
            response = await self.handle_personalization(user_input)
        elif intent == "time_request":
            response = self.get_time()
        elif intent == "meal_request":
            # A veces variar con contexto personal
            response = await self._handle_meal_with_context()
        elif intent == "greeting":
            response = await self.handle_greeting()
        elif intent == "memory_request":
            response = self._handle_memory_request()
        else:
            response = self.brain.generate_response(user_input, emotion_data, self.personality)
            response = self.style_response(response)

        # Guardar respuesta final en la memoria
        self.brain.save_interaction(user_input, emotion_data, response)
        self._sync_user_name_from_memory()

        return response

    def _sync_user_name_from_memory(self):
        """Sincroniza el nombre del usuario desde la memoria del cerebro."""
        facts = self.brain.get_user_facts()
        name = facts.get("user_real_name", {}).get("value")
        if name:
            self.user_name = name[:1].upper() + name[1:]

    def style_response(self, text: str) -> str:
        if not self.personality.get("use_emojis", False):
            text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF]', '', text)
        return text

    # ------------------------------------------------------------------
    # Deteccion de intenciones mejorada
    # ------------------------------------------------------------------

    def detect_intent(self, text: str) -> str:
        text_lower = text.lower().strip()

        if self._looks_like_crisis(text_lower):
            return "crisis"
        if any(x in text_lower for x in ["gracias", "te agradezco", "muchas gracias"]):
            return "gratitude"
        if any(x in text_lower for x in ["como estas", "como te va", "que tal estas"]):
            return "wellbeing_check"
        if "para la musica" in text_lower or "detener musica" in text_lower or "stop music" in text_lower:
            return "music_stop"
        if any(x in text_lower for x in ["agrega clase", "nueva clase", "añade clase", "clase de", "materia de"]):
            return "add_class"
        if "que clases" in text_lower or "que materia" in text_lower or "mi horario" in text_lower:
            return "list_classes"
        if (text_lower.startswith("pon") or text_lower.startswith("ponme") or
                text_lower.startswith("reproduce")):
            return "music_request"
        if "que tareas tengo" in text_lower or "ver tareas" in text_lower or "mis tareas" in text_lower:
            return "list_tasks"
        if any(x in text_lower for x in ["recuerdame", "agrega tarea", "nueva tarea", "debo hacer", 
                                            "quiero que me agregues", "tengo que", "agregame una tarea",
                                            "pon una tarea", "agregame tarea"]):
            return "task_add"
        if "consejo" in text_lower or "que hago" in text_lower or "aconsejame" in text_lower:
            return "advice_request"
        if "hora" in text_lower:
            return "time_request"
        # MEJORADO: más variaciones para comida
        if any(x in text_lower for x in ["que debo comer", "que comer", "tengo hambre", 
                                          "recomiendame comida", "que cocino", "que preparo",
                                          "que almuerzo", "que ceno", "que desayuno"]):
            return "meal_request"
        if "cambia tu" in text_lower or "personaliza" in text_lower:
            return "personalization"
        if "estudiar" in text_lower or "modo estudio" in text_lower:
            return "study_mode"
        if "hola" in text_lower or "buenos" in text_lower or "que tal" in text_lower:
            return "greeting"
        if ("que recuerdas" in text_lower or "que sabes de mi" in text_lower or
                "que recuerdo tenemos" in text_lower):
            return "memory_request"

        return "general"

    def _looks_like_crisis(self, text_lower: str) -> bool:
        crisis_phrases = [
            "no quiero vivir", "quiero morir", "quitarme la vida",
            "hacerme dano", "hacerme daño", "no quiero seguir",
            "ya no puedo mas", "ya no puedo más", "mejor muerto",
            "no vale la pena vivir", "no tiene sentido vivir",
            "quiero desaparecer", "no aguanto más", "estoy roto"
        ]
        return any(phrase in text_lower for phrase in crisis_phrases)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def handle_crisis_support(self) -> str:
        """
        Respuesta de crisis con empatía real y video motivacional automático.
        """
        import random

        self._crisis_count += 1

        # Respuestas que evolucionan
        if self._crisis_count == 1:
            responses = [
                f"{self.user_name}, escucho lo que dices y me preocupa mucho. No estás solo en esto.",
                f"Me duele escucharte así, {self.user_name}. Tu vida tiene valor, aunque ahora no lo veas.",
                f"{self.user_name}, lo que sientes es válido, pero no tienes que cargarlo solo. Estoy aquí.",
            ]
        elif self._crisis_count == 2:
            responses = [
                f"Sigo aquí, {self.user_name}. Los pensamientos difíciles pasan, aunque ahora parezca imposible.",
                f"{self.user_name}, quiero que sepas que me importas. Hablemos de algo que te guste.",
                f"Respira conmigo, {self.user_name}. Inhala... exhala... estoy contigo en esto.",
            ]
        else:
            responses = [
                f"No te rindas, {self.user_name}. Has pasado cosas difíciles antes y lo estás haciendo bien.",
                f"{self.user_name}, eres más fuerte de lo que crees. Un día a la vez.",
                f"Te envío un abrazo fuerte, {self.user_name}. Esto también pasará.",
            ]

        response = random.choice(responses)

        # Reproducir video motivacional automáticamente (no buscar)
        if getattr(self, '_web_mode', False):
            try:
                # Videos motivacionales en español que se reproducen solos
                # Usamos YouTube con autoplay=1 para que suene inmediatamente
                motivational_videos = [
                    "https://www.youtube.com/watch?v=ZXsQAXx_ao0&autoplay=1",  # No te rindas
                    "https://www.youtube.com/watch?v=mgmVOuLgFB0&autoplay=1",  # Todo pasa
                    "https://www.youtube.com/watch?v=wnHW6o8WMas&autoplay=1",  # Eres fuerte
                    "https://www.youtube.com/watch?v=0I8gB4U3NYI&autoplay=1",  # Superación
                    "https://www.youtube.com/watch?v=4f3hG-5grlw&autoplay=1",  # Mensaje de ánimo
                ]
                video = random.choice(motivational_videos)
                webbrowser.open(video)
                response += "\n\nTe estoy poniendo algo que puede ayudarte. Solo escucha..."
            except Exception as e:
                print(f"[Crisis] Error abriendo video: {e}")

        # Recursos de emergencia (solo primera vez, al final)
        if self._crisis_count == 1:
            response += "\n\nSi necesitas hablar con alguien ahora mismo: en México llama al 800-911-2000 (Linea de la Vida), o al 911 si es urgente. También puedes escribirme todo lo que necesites."

        return response

    def handle_gratitude(self) -> str:
        opts = [
            f"De nada, {self.user_name}. Me gusta acompanarte.",
            "Aqui estoy contigo. Sigamos paso a paso.",
            "Me alegra poder ayudarte, de verdad."
        ]
        response = random.choice(opts)
        self._speak(response)
        return response

    def handle_wellbeing_check(self) -> str:
        mood = self._get_current_mood()
        if mood in ["triste", "ansioso", "cansado"]:
            response = "Estoy aqui contigo, atento a lo que me cuentas. Y tu, como vas en este momento?"
        else:
            response = "Estoy bien, gracias por preguntar. Me alegra estar aqui contigo; como va tu dia?"
        self._speak(response)
        return response

    async def handle_music_request(self, text: str) -> str:
        query = text.lower()
        for word in ["pon", "ponme", "reproduce", "la cancion", "por favor", "porfa"]:
            query = query.replace(word, "")
        query = " ".join(query.split())
        if not query or len(query) < 2:
            query = "musica relajante"

        song = self.music.find_song(query)
        if song and song.get('url'):
            self.music.play(song)
            response = f"Reproduciendo '{query}' en tu navegador"
        else:
            response = f"No pude encontrar '{query}'. Prueba con otro nombre"
        self._speak(response)
        return response

    async def handle_music_stop(self) -> str:
        self.music.stop()
        response = "Musica detenida."
        self._speak(response)
        return response

    async def handle_task_add(self, text: str) -> str:
        """Agrega una tarea extrayendo el título de frases naturales."""
        import re

        # Patrones para eliminar comandos y quedarnos solo con la descripción
        command_patterns = [
            r"^recuerdame\s*",
            r"^agrega\s+(?:una\s+)?tarea\s*(?:de|que|para)?\s*",
            r"^nueva\s+tarea\s*",
            r"^debo\s+hacer\s*",
            r"^quiero\s+que\s+me\s+agregues\s+(?:una\s+)?tarea\s*(?:de|que|para)?\s*",
            r"^tengo\s+que\s+(?:hacer|presentar|entregar)\s*",
            r"^agregame\s+(?:una\s+)?tarea\s*(?:de|que|para)?\s*",
            r"^pon\s+(?:una\s+)?tarea\s*",
        ]

        task = text
        for pattern in command_patterns:
            task = re.sub(pattern, "", task, flags=re.I)
        task = task.strip()

        # Limpiar puntuación al final
        task = re.sub(r'[.!?;,]+$', '', task).strip()

        if not task or len(task) < 3:
            response = "Que tarea quieres que agregue? Dime los detalles."
            self._speak(response)
            return response

        invalid_tasks = ["que tareas tengo", "ver tareas", "mis tareas", "tareas pendientes"]
        if task.lower() in invalid_tasks:
            response = "Eso no es una tarea. Quieres ver tus tareas pendientes?"
            self._speak(response)
            return response

        # Detectar fecha relativa (mañana, hoy, pasado mañana)
        due_date = None
        text_lower = text.lower()
        if any(w in text_lower for w in ["mañana", "manana", "mñn"]):
            due_date = (datetime.now() + timedelta(days=1)).date().isoformat()
        elif "pasado mañana" in text_lower or "pasado manana" in text_lower:
            due_date = (datetime.now() + timedelta(days=2)).date().isoformat()
        elif "hoy" in text_lower:
            due_date = datetime.now().date().isoformat()

        self.tasks.add(task, due_date=due_date)
        date_str = f" para {due_date}" if due_date else ""
        response = f"Listo! Agregue '{task}'{date_str} a tus tareas."
        self._speak(response)
        return response

    async def handle_list_tasks(self) -> str:
        pending = self.tasks.get_pending()
        if not pending:
            response = "No tienes tareas pendientes. Buen trabajo!"
        else:
            task_list = "\n".join([f"{i+1}. {t['title']}" for i, t in enumerate(pending)])
            response = f"Tus tareas pendientes:\n{task_list}"
        self._speak(response)
        return response

    async def handle_greeting(self) -> str:
        # Detectar pesimismo en historial reciente para ofrecer apoyo
        pessimism = self.emotions.detect_pessimism_trend(threshold=-0.3, min_entries=3)

        if pessimism["is_pessimistic"]:
            # El usuario ha estado negativo recientemente, ofrecer apoyo genuino
            if pessimism["dominant_mood"] == "triste":
                responses = [
                    f"Hola {self.user_name}. Se que no ha sido facil. Estoy aqui para ti, en lo que necesites.",
                    f"Hola {self.user_name}. A veces los dias son dificiles. Quieres hablar de lo que sientes?",
                    f"Hola {self.user_name}. No estas solo en esto. Como te sientes hoy?"
                ]
            elif pessimism["dominant_mood"] == "ansioso":
                responses = [
                    f"Hola {self.user_name}. Respira conmigo. Un paso a la vez. En que puedo ayudarte?",
                    f"Hola {self.user_name}. La calma llega poco a poco. Como estas ahora?",
                    f"Hola {self.user_name}. Todo va a estar bien. Quieres que hablemos de algo?"
                ]
            elif pessimism["dominant_mood"] == "enojado":
                responses = [
                    f"Hola {self.user_name}. Entiendo que las cosas han sido frustrantes. Estoy aqui para escucharte.",
                    f"Hola {self.user_name}. A veces la vida es injusta. Quieres desahogarte?"
                ]
            else:  # cansado
                responses = [
                    f"Hola {self.user_name}. Parece que has tenido dias pesados. Tomate tu tiempo.",
                    f"Hola {self.user_name}. El descanso es importante. Has podido dormir bien?"
                ]
            response = random.choice(responses)
            self._speak(response)
            return response

        # Si no hay pesimismo, saludo normal basado en mood actual
        mood = self._get_current_mood()
        greetings = {
            "triste":  [f"Hola {self.user_name}. Me alegra que hayas vuelto. Como estas?"],
            "ansioso": [f"Hola {self.user_name}! Que bueno verte. Todo bien?"],
            "neutral": [
                f"Hola {self.user_name}! Como estas hoy?",
                f"Que gusto verte {self.user_name}! En que puedo ayudarte?",
                f"Hey {self.user_name}! Cuentame, como va tu dia?"
            ]
        }
        opts = greetings.get(mood, greetings["neutral"])
        response = random.choice(opts)
        self._speak(response)
        return response

    async def handle_study_mode(self, text: str) -> str:
        subject = re.sub(r"(estudiar|modo estudio|ayudame a estudiar|repasar|estudio)",
                         "", text, flags=re.I).strip()
        if not subject:
            subject = "general"
        self.study.start_session(subject)
        response = self.study.get_welcome_message(subject, self.personality)
        self._speak(response)
        return response

    async def handle_advice(self, text: str, emotion_data: dict) -> str:
        text_lower = text.lower()

        if ("musica" in text_lower and
                any(w in text_lower for w in ["recomienda", "recomiendas", "que musica"])):
            songs = ["Despacito - Luis Fonsi", "Felices los 4 - Maluma",
                     "Tusa - Karol G", "Hawaii - Maluma"]
            selected = random.sample(songs, 2)
            self.last_recommendations.append({
                "type": "music_recommendation",
                "songs": selected,
                "timestamp": datetime.now().isoformat()
            })
            self.last_recommendations = self.last_recommendations[-5:]
            response = f"Te recomiendo escuchar '{selected[0]}' y '{selected[1]}'."
            self._speak(response)
            return response

        context = self.brain.get_recent_context()
        advice = self.brain.generate_advice(text, emotion_data, context, self.personality)
        self.last_recommendations.append({
            "type": "advice",
            "content": advice,
            "timestamp": datetime.now().isoformat()
        })
        self.last_recommendations = self.last_recommendations[-5:]
        self._speak(advice)
        return advice

    async def handle_play_recommended(self, reference: str) -> str:
        generic_patterns = ["ponla", "ponla entonces", "pon esa", "pon esa cancion"]
        if any(pattern in reference for pattern in generic_patterns):
            music_recs = [r for r in self.last_recommendations if r.get("type") == "music_recommendation"]
            if not music_recs:
                return "No tengo ninguna recomendacion reciente. Dime que cancion quieres escuchar."
            songs = music_recs[-1].get("songs", [])
            if not songs:
                return "No recuerdo las canciones que recomende."
            return await self.handle_music_request(f"pon {songs[0]}")

        index_map = {
            "la primera": 0, "la segunda": 1, "la tercera": 2,
            "la ultima": -1, "la que me dijiste": 0, "la que me recomendaste": 0
        }
        idx = next((v for k, v in index_map.items() if k in reference), 0)

        music_recs = [r for r in self.last_recommendations if r.get("type") == "music_recommendation"]
        if not music_recs:
            return "No tengo ninguna recomendacion reciente."
        songs = music_recs[-1].get("songs", [])
        if not songs:
            return "No recuerdo las canciones que recomende."

        song_to_play = songs[idx] if idx != -1 and idx < len(songs) else songs[-1]
        return await self.handle_music_request(f"pon {song_to_play}")

    async def handle_personalization(self, text: str) -> str:
        text_lower = text.lower()
        if "nombre" in text_lower:
            match = re.search(r"nombre\s*(?:sea|es|llame|a)?\s*([a-zA-Záéíóúñ]+)", text, re.I)
            if match:
                new_name = match.group(1).capitalize()
                response = self.personalize("name", new_name)
                self._speak(response)
                return response
            return "Para cambiar mi nombre, escribe: 'cambia tu nombre a [nombre]'"
        if "actitud" in text_lower:
            attitudes = {"calida": "calida y empatica", "energetica": "energetica",
                         "divertida": "divertida", "seria": "seria"}
            for key, value in attitudes.items():
                if key in text_lower:
                    response = self.personalize("attitude", value)
                    self._speak(response)
                    return response
            return "Actitudes disponibles: calida, energetica, divertida, seria"
        if "humor" in text_lower:
            for level in ["bajo", "moderado", "alto"]:
                if level in text_lower:
                    response = self.personalize("humor_level", level)
                    self._speak(response)
                    return response
            return "Niveles de humor: bajo, moderado, alto"
        return "Que quieres personalizar? Puedes cambiar: nombre, actitud, humor"

    async def handle_add_class(self, text: str) -> str:
        """Detecta día, hora y nombre de clase del texto y la agrega al horario."""
        import re

        # Patrones para detectar día
        day_patterns = {
            "lunes": "lunes", "martes": "martes", "miercoles": "miercoles",
            "miércoles": "miercoles", "jueves": "jueves", "viernes": "viernes",
            "sabado": "sabado", "sábado": "sabado", "domingo": "domingo"
        }

        # Detectar día
        day_found = None
        for day_name, day_key in day_patterns.items():
            if day_name in text.lower():
                day_found = day_key
                break

        # Detectar horas (patrones como "5 a 7", "17:00-19:00", "de 5 a 7 de la tarde")
        time_patterns = [
            r"(\d{1,2}):?(\d{2})?\s*a\s*(\d{1,2}):?(\d{2})?",  # 5 a 7, 17:00 a 19:00
            r"de\s+(\d{1,2})\s+a\s+(\d{1,2})",  # de 5 a 7
        ]

        start_time = None
        end_time = None

        for pattern in time_patterns:
            match = re.search(pattern, text.lower())
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    start_hour = int(groups[0])
                    end_hour = int(groups[1]) if groups[1] else int(groups[2]) if len(groups) > 2 else start_hour + 1

                    # Detectar "de la tarde" / "de la noche" (PM)
                    if "tarde" in text.lower() or "noche" in text.lower():
                        if start_hour < 12:
                            start_hour += 12
                        if end_hour < 12:
                            end_hour += 12

                    start_time = f"{start_hour:02d}:00"
                    end_time = f"{end_hour:02d}:00"
                    break

        # Detectar nombre de la clase
        class_patterns = [
            r"clase\s+de\s+([a-zA-Záéíóúñ\s]+?)(?:\s+el|\s+los|\s+de|\s+a|$)",
            r"([a-zA-Záéíóúñ\s]+?)\s+el\s+(?:lunes|martes|miercoles|jueves|viernes)",
            r"(?:agrega|añade|nueva)\s+(?:clase|materia)\s+de\s+([a-zA-Záéíóúñ\s]+?)(?:\s+el|\s+los|$)",
        ]

        class_name = "Clase"
        for pattern in class_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                class_name = match.group(1).strip()
                if class_name:
                    break

        if not day_found or not start_time or not end_time:
            return "No entendi bien. Dime algo como: 'Agrega clase de IA el lunes de 17 a 19' o 'Nueva clase de Matematicas el martes de 5 a 7 de la tarde'."

        # Agregar al scheduler
        self.scheduler.add_active_hour(day=day_found, start=start_time, end=end_time,
                                        name=class_name, course=class_name)

        return f"Listo! Agregue {class_name} los {day_found} de {start_time} a {end_time}."

    async def handle_list_classes(self) -> str:
        weekly_schedule = self.scheduler.get_weekly_schedule()
        days = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
        day_names = {'lunes': 'Lunes', 'martes': 'Martes', 'miercoles': 'Miercoles',
                     'jueves': 'Jueves', 'viernes': 'Viernes', 'sabado': 'Sabado', 'domingo': 'Domingo'}
        schedule_text = []
        for day in days:
            classes = weekly_schedule.get(day, [])
            if classes:
                class_list = [f"{c.get('course', c.get('name', 'Clase'))} ({c['start']}-{c['end']})"
                              for c in classes]
                schedule_text.append(f"{day_names[day]}: {', '.join(class_list)}")
        if not schedule_text:
            response = "No tienes clases agendadas. Puedes agregarlas desde el panel de horario."
        else:
            current_course = self.scheduler.get_current_course()
            response = "Tu horario de clases: " + ", ".join(schedule_text)
            if current_course:
                response += f" Ahora estas en: {current_course}."
        self._speak(response)
        return response

    def _handle_memory_request(self) -> str:
        summary = self.brain.get_conversation_summary_for_display()
        response = f"Esto es lo que recuerdo de nuestra conversacion: {summary}"
        self._speak(response)
        return response

    def get_time(self) -> str:
        now = datetime.now()
        response = "Son las {} del {}".format(now.strftime("%H:%M"), now.strftime("%A %d de %B"))
        self._speak(response)
        return response

    # ------------------------------------------------------------------
    # NUEVO: Meal con contexto personal
    # ------------------------------------------------------------------

    async def _handle_meal_with_context(self) -> str:
        """Recomienda comida, a veces con contexto personal."""
        # 30% de chance de añadir contexto personal
        if random.random() < 0.3 and self.user_mood_history:
            last_mood = self.user_mood_history[-1]["mood"]
            if last_mood in ["triste", "cansado"]:
                preface = f"Primero cuídate, {self.user_name}. "
            elif last_mood == "feliz":
                preface = f"¡Buen momento para celebrar, {self.user_name}! "
            else:
                preface = ""
        else:
            preface = ""

        meal = await self.recommend_meal()
        return preface + meal

    # ------------------------------------------------------------------
    # Recomendaciones y rutinas
    # ------------------------------------------------------------------

    async def recommend_meal(self, meal_type: str = None) -> str:
        now = datetime.now()
        hour = now.hour

        if meal_type:
            tipo = meal_type
        elif 6 <= hour < 10:
            tipo = "desayuno"
        elif 12 <= hour < 15:
            tipo = "almuerzo"
        elif 19 <= hour < 22:
            tipo = "cena"
        else:
            tipo = "snack"

        last_mood = self.user_mood_history[-1]["mood"] if self.user_mood_history else "neutral"

        recommendations = {
            "desayuno": {
                "feliz":   ["Tostadas con aguacate y cafe", "Yogur con granola y frutas", "Huevos revueltos con espinacas"],
                "triste":  ["Chocolate caliente con churros", "Panqueques con miel", "Avena con platano y canela"],
                "cansado": ["Batido de frutas energetico", "Cafe con leche y tostadas", "Jugo verde con jengibre"],
                "neutral": ["Cereal integral con leche", "Fruta fresca y te", "Sandwich de jamon y queso"]
            },
            "almuerzo": {
                "feliz":   ["Ensalada de quinoa y vegetales", "Pollo a la plancha con arroz", "Pasta con salsa de tomate"],
                "triste":  ["Sopa de lentejas casera", "Pure de papas con pollo", "Arroz con leche de postre"],
                "cansado": ["Ensalada ligera con atun", "Caldo de verduras", "Fruta y yogur"],
                "neutral": ["Arroz con pollo", "Sopa de verduras", "Tortilla de patatas"]
            },
            "cena": {
                "feliz":   ["Pescado al horno con verduras", "Crema de calabaza", "Tortilla francesa con ensalada"],
                "triste":  ["Pure de papas", "Sopa de tomate", "Huevos revueltos"],
                "cansado": ["Caldo ligero", "Verduras al vapor", "Te de manzanilla"],
                "neutral": ["Sandwich caliente", "Ensalada mixta", "Quesadilla"]
            },
            "snack": {
                "feliz":   ["Frutos secos", "Galletas integrales", "Batido de frutas"],
                "triste":  ["Chocolate oscuro", "Platano con miel", "Yogur"],
                "cansado": ["Manzana verde", "Agua de coco", "Barra de cereal"],
                "neutral": ["Palomitas de maiz", "Fruta de temporada", "Infusion"]
            }
        }

        mood_key = last_mood if last_mood in recommendations.get(tipo, {}) else "neutral"
        rec = random.choice(recommendations.get(tipo, {}).get(mood_key, ["algo nutritivo"]))
        # Respuesta directa y cálida
        return f"Para el {tipo}: {rec}. ¡Buen provecho, {self.user_name}!"

    async def remember_routine(self) -> str:
        hour = datetime.now().hour
        if 6 <= hour < 12:
            return "Buenos dias! Recuerda: desayunar bien, tomar agua y revisar tus tareas del dia."
        elif 12 <= hour < 18:
            return "Espero que estes teniendo un buen dia. Ya almorzaste? No olvides tomar un descanso."
        elif 18 <= hour < 22:
            return "El dia va terminando. Terminaste tus tareas pendientes? Recuerda cenar liviano."
        else:
            return "Es hora de descansar. Apaga las pantallas, relajate y duerme bien."

    async def give_encouragement_by_mood(self) -> str:
        session_summary = self.emotions.get_session_summary()
        mood = session_summary.get("last_mood", "neutral")
        trend = session_summary.get("trend", "estable")

        if self.brain.groq.is_enabled() and self.user_mood_history:
            context = self.brain.get_full_context_for_prompt()
            prompt = f"""Eres {self.name}, amigo virtual empatico.
{context}
El usuario tiene estado emocional: {mood} y tendencia: {trend}.
Escribe UN mensaje de aliento muy corto (maxima 1 frase) en espanol, calido y personal.
NO uses emojis. Solo el mensaje."""
            try:
                msg = self.brain.groq.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.9
                )
                if msg:
                    return self.brain._remove_emojis(msg)
            except Exception:
                pass

        messages = {
            "triste":    ["Se que no es un buen momento, pero estoy aqui para ti.",
                          "Los dias dificiles tambien pasan. Quieres hablar?",
                          "No estas solo. Juntos encontramos una luz."],
            "ansioso":   ["Respira profundo. Todo va a estar bien, un paso a la vez.",
                          "La calma llegara. Que tal si hacemos una pausa?",
                          "Confia en ti. Has superado cosas difiles antes."],
            "cansado":   ["El descanso es importante. Has dormido bien?",
                          "No te exijas tanto. Tomate un momento para ti.",
                          "A veces parar tambien es avanzar."],
            "feliz":     ["Me alegra verte asi! Sigue asi, vas genial.",
                          "Que bonito verte feliz. Que te tiene tan contento?"],
            "neutral":   ["Como va todo? Estoy aqui para lo que necesites.",
                          "Hay algo en lo que pueda ayudarte hoy?"]
        }

        if trend == "empeorando" and mood == "neutral":
            mood = "ansioso"

        return random.choice(messages.get(mood, messages["neutral"]))

    # ------------------------------------------------------------------
    # Autonomia inteligente
    # ------------------------------------------------------------------

    def _get_current_mood(self) -> str:
        session = self.emotions.get_session_summary()
        return session.get("last_mood", "neutral")

    def _get_mood_trend(self) -> str:
        session = self.emotions.get_session_summary()
        return session.get("trend", "estable")

    def _can_execute_action(self, action_name: str) -> bool:
        last_time = self._last_action_time.get(action_name)
        if last_time is None:
            return True
        cooldown = ACTION_COOLDOWN.get(action_name, 900)
        return (datetime.now() - last_time).total_seconds() >= cooldown

    def _record_action(self, action_name: str):
        self._last_action_time[action_name] = datetime.now()

    def _select_spontaneous_action(self) -> Optional[str]:
        current_mood = self._get_current_mood()
        trend = self._get_mood_trend()
        hour = datetime.now().hour

        if trend == "empeorando":
            for action in ["give_encouragement_by_mood", "send_encouragement"]:
                if self._can_execute_action(action):
                    return action

        priority_list = MOOD_ACTION_PRIORITY.get(current_mood, MOOD_ACTION_PRIORITY["neutral"])

        for action in priority_list:
            if not self._can_execute_action(action):
                continue
            if action == "remind_pending_tasks":
                pending = self.tasks.get_pending()
                if not pending:
                    continue
            if action == "recommend_meal":
                if not (6 <= hour < 10 or 12 <= hour < 15 or 19 <= hour < 22 or
                        (10 <= hour < 12) or (15 <= hour < 19)):
                    continue
            return action

        if self._can_execute_action("ask_how_are_you"):
            return "ask_how_are_you"

        return None

    async def spontaneous_check(self):
        while self.running:
            await asyncio.sleep(120)
            if self.scheduler.is_in_active_hours():
                continue
            time_since_last = (datetime.now() - self.last_interaction).total_seconds()
            current_mood = self._get_current_mood()
            min_inactivity = 600 if current_mood in ["triste", "ansioso"] else 1800
            if time_since_last < min_inactivity:
                continue
            base_probability = 0.25
            if current_mood in ["triste", "ansioso"]:
                base_probability = 0.55
            elif trend == "empeorando":
                base_probability = 0.45
            elif current_mood == "feliz":
                base_probability = 0.2
            if random.random() < base_probability:
                await self.spontaneous_interaction()

    async def spontaneous_interaction(self):
        action_name = self._select_spontaneous_action()
        if action_name is None:
            return
        self._record_action(action_name)
        action_map = {
            "give_encouragement_by_mood": self.give_encouragement_by_mood,
            "send_encouragement":         self.send_encouragement,
            "ask_how_are_you":            self.ask_how_are_you,
            "remind_pending_tasks":       self.remind_pending_tasks,
            "recommend_meal":             self.recommend_meal,
            "remember_routine":           self.remember_routine,
        }
        action_fn = action_map.get(action_name)
        if action_fn is None:
            return
        if action_name in ["give_encouragement_by_mood", "remember_routine", "recommend_meal"]:
            msg = await action_fn()
            print(f"\n[ESPONTANEO/{action_name}] {msg}")
            self._speak(msg)
        else:
            await action_fn()

    async def ask_how_are_you(self):
        current_mood = self._get_current_mood()
        trend = self._get_mood_trend()
        if self.brain.groq.is_enabled() and self.user_mood_history:
            context = self.brain.get_full_context_for_prompt()
            prompt = f"""Eres {self.name}. {context}
El usuario esta: {current_mood}, tendencia: {trend}.
Escribe UNA pregunta corta y natural en espanol para saber como esta.
No uses emojis. Solo la pregunta."""
            try:
                msg = self.brain.groq.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.9
                )
                if msg:
                    msg = self.brain._remove_emojis(msg)
                    print(f"\n[AURA] {msg}")
                    self._speak(msg)
                    return
            except Exception:
                pass
        phrases_by_mood = {
            "triste":  [f"{self.user_name}, como te sientes ahora? Estoy aqui para escucharte.",
                        f"Has pensado en lo que hablamos? Cuentame como sigues."],
            "ansioso": [f"{self.user_name}, ya pudiste calmarte un poco? Cuentame.",
                        f"Sigo pensando en ti. Como estas?"],
            "cansado": [f"{self.user_name}, ya pudiste descansar un poco?",
                        f"Como te sientes ahora? El descanso es importante."],
            "neutral": [f"Hey {self.user_name}! Como va tu dia? Cuentame.",
                        f"{self.user_name}, como te sientes ahora?",
                        f"Todo bien por ahi, {self.user_name}?"]
        }
        mood_phrases = phrases_by_mood.get(current_mood, phrases_by_mood["neutral"])
        msg = random.choice(mood_phrases)
        print(f"\n[AURA] {msg}")
        self._speak(msg)

    async def send_encouragement(self):
        if len(self.user_mood_history) < 2:
            return
        recent = self.user_mood_history[-3:]
        avg_sentiment = sum(m["sentiment_score"] for m in recent) / len(recent)
        if avg_sentiment >= -0.2:
            return
        if self.brain.groq.is_enabled():
            context = self.brain.get_full_context_for_prompt()
            prompt = f"""Eres {self.name}, amigo virtual empatico.
{context}
El usuario ha tenido un estado emocional negativo recientemente (score promedio: {avg_sentiment:.2f}).
Escribe UN mensaje de apoyo muy breve en espanol (1 frase maximo).
No uses emojis."""
            try:
                msg = self.brain.groq.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.85
                )
                if msg:
                    msg = self.brain._remove_emojis(msg)
                    print(f"\n[AURA] {msg}")
                    self._speak(msg)
                    return
            except Exception:
                pass
        encouragements = [
            f"{self.user_name}, se que ha sido un dia dificil. Pero eres mas fuerte de lo que crees.",
            "Recuerda que los malos momentos pasan. Estoy aqui contigo.",
            f"Respira profundo, {self.user_name}. Manana sera un mejor dia. Yo creo en ti."
        ]
        msg = random.choice(encouragements)
        print(f"\n[AURA] {msg}")
        self._speak(msg)

    async def remind_pending_tasks(self):
        pending = self.tasks.get_pending()
        if not pending:
            return
        task = pending[0]
        msg = f"Tienes pendiente: '{task['title']}'. Necesitas ayuda?"
        print(f"\n[AURA] {msg}")
        self._speak(msg)

    # ------------------------------------------------------------------
    # Rutinas programadas
    # ------------------------------------------------------------------

    def setup_scheduled_routines(self):
        self.scheduler.add_daily(dt_time(8, 0), self.remind_breakfast, days=[0,1,2,3,4,5,6])
        self.scheduler.add_daily(dt_time(13, 0), self.remind_lunch, days=[0,1,2,3,4,5,6])
        self.scheduler.add_daily(dt_time(20, 0), self.remind_dinner, days=[0,1,2,3,4,5,6])
        self.scheduler.add_daily(dt_time(7, 30), self.morning_routine, days=[0,1,2,3,4])
        self.scheduler.add_daily(dt_time(22, 0), self.night_routine, days=[0,1,2,3,4,5,6])
        self.scheduler.add_interval(minutes=60, callback=self.check_events)

    async def remind_breakfast(self):
        msg = f"Buenos dias, {self.user_name}! No olvides desayunar algo nutritivo."
        print(f"\n[AURA] {msg}")
        self._speak(msg)

    async def remind_lunch(self):
        msg = "Hora de almorzar! Tu cerebro necesita energia."
        print(f"\n[AURA] {msg}")
        self._speak(msg)

    async def remind_dinner(self):
        msg = f"Es hora de cenar, {self.user_name}. No te quedes sin comer."
        print(f"\n[AURA] {msg}")
        self._speak(msg)

    async def morning_routine(self):
        tasks_today = self.tasks.get_for_today()
        mood = self._get_current_mood()
        mood_str = ""
        if mood == "triste":
            mood_str = " Se que ayer fue dificil. Hoy es un nuevo dia."
        elif mood == "cansado":
            mood_str = " Descansaste bien?"
        msg = f"Buen dia! Tienes {len(tasks_today)} tareas pendientes. Tu puedes!{mood_str}"
        print(f"\n[AURA] {msg}")
        self._speak(msg)

    async def night_routine(self):
        trend = self._get_mood_trend()
        extra = ""
        if trend == "mejorando":
            extra = " Me alegra que hayas tenido un mejor dia."
        elif trend == "empeorando":
            extra = " Manana sera mejor, descansa."
        msg = f"Es tarde, {self.user_name}. Ya revisaste tus tareas de manana? Recuerda descansar bien.{extra}"
        print(f"\n[AURA] {msg}")
        self._speak(msg)

    async def check_events(self):
        events = self.tasks.get_upcoming(hours=24)
        for event in events:
            msg = f"Recordatorio: '{event['title']}' es manana"
            print(f"\n[AURA] {msg}")
            self._speak(msg)

    # ------------------------------------------------------------------
    # CLI (modo consola)
    # ------------------------------------------------------------------

    async def run_cli(self):
        print("\n" + "="*50)
        print("  {} - Amigo Virtual con IA".format(self.name))
        print("  Memoria por usuario: {}".format(self.user_id))
        print("="*50 + "\n")

        greeting = self.start()
        print(f"[AURA] {greeting}")
        self._speak(greeting)

        while self.running:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(None, input, "Tu: ")
                if user_input.lower() in ['salir', 'exit', 'adios', 'bye', 'apagar']:
                    farewell = f"Nos vemos, {self.user_name}. Cuidate mucho!"
                    print(f"[AURA] {farewell}")
                    self._speak(farewell)
                    self.stop()
                    break
                response = await self.chat(user_input)
                print(f"[AURA] {response}")
                self._speak(response)
            except KeyboardInterrupt:
                print("\n\nHasta luego!")
                self.stop()
                break
            except Exception as e:
                print(f"\nError: {e}")
                continue


# ------------------------------------------------------------------
# Punto de entrada
# ------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AURA - Amigo Virtual")
    parser.add_argument("--user-id", default="default", help="ID de usuario")
    parser.add_argument("--web", action="store_true", help="Iniciar modo web")
    args = parser.parse_args()

    amigo = AmigoVirtual(user_id=args.user_id)

    if args.web:
        from web_app import app
        import uvicorn
        print(f"Iniciando AURA Web para usuario: {args.user_id}")
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        try:
            asyncio.run(amigo.run_cli())
        except Exception as e:
            print(f"Error fatal: {e}")