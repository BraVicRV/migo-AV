"""
AMIGO VIRTUAL PERSONALIZABLE
Version Laptop - 2026

Ejecutar con: python main.py
"""

import asyncio
import json
import threading
import time
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Dict, List, Optional
import random
import re
import os
import sys

# Core imports
from core.brain import VirtualBrain
from core.voice import VoiceManager
from core.scheduler import RoutineScheduler
from core.emotions import EmotionAnalyzer
from modules.music import MusicRecommender
from modules.tasks import TaskManager
from modules.study import StudyAssistant

def solicitar_api_key():
    """Solicita la API key de Groq al usuario"""
    print("\n" + "="*50)
    print("CONFIGURACION DE GROQ")
    print("="*50)
    print("Groq es necesario para que tu amigo virtual pueda responder de forma inteligente.")
    print("Puedes obtener una API key gratis en: https://console.groq.com")
    print("")
    
    api_key = input("Ingresa tu API key de Groq (gsk_...): ").strip()
    
    if api_key.startswith('gsk_') and len(api_key) > 10:
        os.environ['GROQ_API_KEY'] = api_key
        print("API key configurada correctamente\n")
        return api_key
    else:
        print("API key invalida. Debe empezar con 'gsk_'")
        print("Quieres intentar de nuevo? (s/n): ")
        if input().lower() == 's':
            return solicitar_api_key()
        else:
            print("Continuando sin Groq (respuestas limitadas)")
            return None

class AmigoVirtual:
    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.name = "AURA"
        self.running = False
        self.user_name = "Amigo"
        self.pending_callbacks = []
        self.last_recommendations = []

        # Inicializar componentes
        self.brain = VirtualBrain(user_id=self.user_id, amigo_instance=self)
        self.voice = VoiceManager()
        self.scheduler = RoutineScheduler(self)
        self.emotions = EmotionAnalyzer()
        self.music = MusicRecommender()
        self.tasks = TaskManager()
        self.study = StudyAssistant()

        self.user_mood_history = []
        self.last_interaction = datetime.now()

        self.load_config()

        print("{} esta despertando...".format(self.name))
        print("   Personalidad: {}".format(self.personality['attitude']))
        print("   Voz: {}".format(self.personality['voice_type']))

    def load_config(self):
        """Carga o crea configuracion de personalidad"""
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

        user_path = Path("config/user_profile.json")
        if user_path.exists():
            with open(user_path, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
                self.user_name = user_data.get("user_name", "Amigo")

    def save_config(self):
        """Guarda configuracion"""
        Path("config").mkdir(exist_ok=True)
        with open("config/personality.json", 'w', encoding='utf-8') as f:
            json.dump(self.personality, f, ensure_ascii=False, indent=2)

    def personalize(self, attribute: str, value):
        """Permite personalizar cualquier atributo"""
        if attribute in self.personality:
            old = self.personality[attribute]
            self.personality[attribute] = value
            self.save_config()
            return "{} cambiado de '{}' a '{}'".format(attribute, old, value)
        return "Atributo '{}' no existe. Opciones: {}".format(attribute, list(self.personality.keys()))

    # ============================================================
    # FUNCIONES DE RECOMENDACION Y RUTINAS
    # ============================================================

    async def recommend_meal(self, meal_type: str = None) -> str:
        """Recomienda que comer segun la hora y estado de animo"""
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
                "feliz": ["Tostadas con aguacate y cafe", "Yogur con granola y frutas", "Huevos revueltos con espinacas"],
                "triste": ["Chocolate caliente con churros", "Panqueques con miel", "Avena con platano y canela"],
                "cansado": ["Batido de frutas energetico", "Cafe con leche y tostadas", "Jugo verde con jengibre"],
                "neutral": ["Cereal integral con leche", "Fruta fresca y te", "Sandwich de jamon y queso"]
            },
            "almuerzo": {
                "feliz": ["Ensalada de quinoa y vegetales", "Pollo a la plancha con arroz", "Pasta con salsa de tomate"],
                "triste": ["Sopa de lentejas casera", "Pure de papas con pollo", "Arroz con leche de postre"],
                "cansado": ["Ensalada ligera con atun", "Caldo de verduras", "Fruta y yogur"],
                "neutral": ["Arroz con pollo", "Sopa de verduras", "Tortilla de patatas"]
            },
            "cena": {
                "feliz": ["Pescado al horno con verduras", "Crema de calabaza", "Tortilla francesa con ensalada"],
                "triste": ["Pure de papas", "Sopa de tomate", "Huevos revueltos"],
                "cansado": ["Caldo ligero", "Verduras al vapor", "Te de manzanilla"],
                "neutral": ["Sandwich caliente", "Ensalada mixta", "Quesadilla"]
            },
            "snack": {
                "feliz": ["Frutos secos", "Galletas integrales", "Batido de frutas"],
                "triste": ["Chocolate oscuro", "Platano con miel", "Yogur"],
                "cansado": ["Manzana verde", "Agua de coco", "Barra de cereal"],
                "neutral": ["Palomitas de maiz", "Fruta de temporada", "Infusion"]
            }
        }
        
        rec = random.choice(recommendations.get(tipo, {}).get(last_mood, recommendations[tipo]["neutral"]))
        response = f"Para el {tipo}, te recomiendo: {rec}"
        self.voice.speak(response)
        return response

    async def remember_routine(self) -> str:
        """Recuerda las rutinas programadas para hoy"""
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
        """Da aliento segun el historial emocional del usuario"""
        if not self.user_mood_history:
            return "Estoy aqui para ti siempre. Como te sientes hoy?"
        
        last_mood = self.user_mood_history[-1]
        mood = last_mood["mood"]
        
        messages = {
            "triste": [
                "Se que no es un buen momento, pero quiero que sepas que estoy aqui para ti.",
                "Los dias dificiles tambien pasan. Quieres hablar de ello?",
                "No estas solo. Juntos podemos encontrar una luz."
            ],
            "ansioso": [
                "Respira profundo. Todo va a estar bien, un paso a la vez.",
                "La calma llegara. Que tal si hacemos una pausa?",
                "Confia en ti. Has superado cosas dificiles antes."
            ],
            "cansado": [
                "El descanso es importante. Has dormido bien?",
                "No te exijas tanto. Tomate un momento para ti.",
                "A veces parar tambien es avanzar. Necesitas un respiro?"
            ],
            "feliz": [
                "Me alegra verte asi! Sigue asi, vas genial.",
                "Que bonito verte feliz. Que te tiene asi de contento?",
                "Esa energia positiva contagia. A seguir asi!"
            ],
            "neutral": [
                "Como va todo? Estoy aqui para lo que necesites.",
                "Cuentame como ha sido tu dia. Me interesa saber de ti.",
                "Hay algo en lo que pueda ayudarte hoy?"
            ]
        }
        
        return random.choice(messages.get(mood, messages["neutral"]))

    # ============================================================
    # FUNCIONES ESPONTANEAS
    # ============================================================

    async def spontaneous_check(self):
        while self.running:
            await asyncio.sleep(60)
            if self.scheduler.is_in_active_hours():
                continue
            time_since_last = (datetime.now() - self.last_interaction).total_seconds()
            if time_since_last > 1800 and random.random() < 0.3:
                await self.spontaneous_interaction()

    async def spontaneous_interaction(self):
        actions = [
            self.ask_how_are_you,
            self.remember_routine,
            self.recommend_meal,
            self.remind_pending_tasks,
            self.give_encouragement_by_mood,
            self.send_encouragement
        ]
        action = random.choice(actions)
        
        if action == self.remember_routine:
            msg = await self.remember_routine()
        elif action == self.recommend_meal:
            msg = await self.recommend_meal()
        elif action == self.give_encouragement_by_mood:
            msg = await self.give_encouragement_by_mood()
        else:
            await action()
            return
        
        print(f"\n[ESPONTANEO] {msg}")
        self.voice.speak(msg)

    async def ask_how_are_you(self):
        phrases = [
            "Hey {}! Como va tu dia? Cuentame".format(self.user_name),
            "{}, como te sientes ahora? Estoy aqui para escucharte".format(self.user_name),
            "Todo bien por ahi, {}? Te extranaba un poco".format(self.user_name)
        ]
        msg = random.choice(phrases)
        print("\n[AURA] {}".format(msg))
        self.voice.speak(msg)

    async def send_encouragement(self):
        if len(self.user_mood_history) < 2:
            return
        recent = self.user_mood_history[-3:]
        avg_sentiment = sum(m["sentiment_score"] for m in recent) / len(recent)
        if avg_sentiment < -0.3:
            encouragements = [
                "{}, se que ha sido un dia dificil. Pero eres mas fuerte de lo que crees".format(self.user_name),
                "Recuerda que los malos momentos pasan. Estoy aqui contigo, siempre",
                "Respira profundo, {}. Manana sera un mejor dia. Yo creo en ti".format(self.user_name)
            ]
            msg = random.choice(encouragements)
            print("\n[AURA] {}".format(msg))
            self.voice.speak(msg)

    async def remind_pending_tasks(self):
        pending = self.tasks.get_pending()
        if pending:
            task = pending[0]
            msg = "Tienes pendiente: '{}'. Necesitas ayuda?".format(task['title'])
            print("\n[AURA] {}".format(msg))
            self.voice.speak(msg)

    # ============================================================
    # FUNCIONES PROGRAMADAS
    # ============================================================

    def setup_scheduled_routines(self):
        self.scheduler.add_daily(dt_time(8, 0), self.remind_breakfast, days=[0,1,2,3,4,5,6])
        self.scheduler.add_daily(dt_time(13, 0), self.remind_lunch, days=[0,1,2,3,4,5,6])
        self.scheduler.add_daily(dt_time(20, 0), self.remind_dinner, days=[0,1,2,3,4,5,6])
        self.scheduler.add_daily(dt_time(7, 30), self.morning_routine, days=[0,1,2,3,4])
        self.scheduler.add_daily(dt_time(22, 0), self.night_routine, days=[0,1,2,3,4,5,6])
        self.scheduler.add_interval(minutes=60, callback=self.check_events)

    async def remind_breakfast(self):
        msg = "Buenos dias, {}! No olvides desayunar algo nutritivo.".format(self.user_name)
        print("\n[AURA] {}".format(msg))
        self.voice.speak(msg)

    async def remind_lunch(self):
        msg = "Hora de almorzar! Tu cerebro necesita energia."
        print("\n[AURA] {}".format(msg))
        self.voice.speak(msg)

    async def remind_dinner(self):
        msg = "Es hora de cenar, {}. No te quedes sin comer.".format(self.user_name)
        print("\n[AURA] {}".format(msg))
        self.voice.speak(msg)

    async def morning_routine(self):
        tasks_today = self.tasks.get_for_today()
        msg = "Buen dia! Tienes {} tareas pendientes. Tu puedes!".format(len(tasks_today))
        print("\n[AURA] {}".format(msg))
        self.voice.speak(msg)

    async def night_routine(self):
        msg = "Es tarde, {}. Ya revisaste tus tareas de manana? Recuerda descansar bien.".format(self.user_name)
        print("\n[AURA] {}".format(msg))
        self.voice.speak(msg)

    async def check_events(self):
        events = self.tasks.get_upcoming(hours=24)
        for event in events:
            msg = "Recordatorio: '{}' es manana".format(event['title'])
            print("\n[AURA] {}".format(msg))
            self.voice.speak(msg)

    # ============================================================
    # INTERACCION PRINCIPAL
    # ============================================================

    async def chat(self, user_input: str) -> str:
        self.last_interaction = datetime.now()

        emotion_data = self.emotions.analyze(user_input)
        self.user_mood_history.append({
            "timestamp": datetime.now().isoformat(),
            "mood": emotion_data["mood"],
            "sentiment_score": emotion_data["score"]
        })

        self.brain.save_interaction(user_input, emotion_data)
        
        # Detectar referencias a recomendaciones
        user_lower = user_input.lower()
        referral_patterns = [
            r"ponla\s*(entonces)?", r"pon\s+esa", r"pon\s+esa\s+cancion",
            r"pon\s+la\s+que\s+me\s+dijiste", r"pon\s+la\s+que\s+me\s+recomendaste",
            r"pon\s+la\s+primera", r"pon\s+la\s+segunda", r"pon\s+la\s+tercera", r"pon\s+la\s+ultima",
        ]
        
        match = None
        for pattern in referral_patterns:
            match = re.search(pattern, user_lower)
            if match:
                break
        
        if match:
            return await self.handle_play_recommended(match.group(0))
        
        intent = self.detect_intent(user_input)

        # Manejo de intenciones
        if intent == "music_request":
            return await self.handle_music_request(user_input)
        elif intent == "music_stop":
            return await self.handle_music_stop()
        elif intent == "task_add":
            return await self.handle_task_add(user_input)
        elif intent == "list_tasks":
            return await self.handle_list_tasks()
        elif intent == "list_classes":
            return await self.handle_list_classes()
        elif intent == "study_mode":
            return await self.handle_study_mode(user_input)
        elif intent == "advice_request":
            return await self.handle_advice(user_input, emotion_data)
        elif intent == "personalization":
            return await self.handle_personalization(user_input)
        elif intent == "time_request":
            return self.get_time()
        elif intent == "meal_request":
            return await self.recommend_meal()
        elif intent == "greeting":
            return await self.handle_greeting()

        response = self.brain.generate_response(user_input, emotion_data, self.personality)
        response = self.style_response(response)

        print("\n[AURA] {}".format(response))
        self.voice.speak(response)

        return response

    def detect_intent(self, text: str) -> str:
        text_lower = text.lower().strip()
        
        if "para la musica" in text_lower or "detener musica" in text_lower or "stop music" in text_lower:
            return "music_stop"
        
        if "que clases" in text_lower or "que materia" in text_lower or "mi horario" in text_lower:
            return "list_classes"
        
        if (text_lower.startswith("pon") or 
            text_lower.startswith("ponme") or 
            text_lower.startswith("reproduce")):
            return "music_request"
        
        if "que tareas tengo" in text_lower or "ver tareas" in text_lower or "mis tareas" in text_lower:
            return "list_tasks"
        
        if "recuerdame" in text_lower:
            return "task_add"
        
        if "consejo" in text_lower or "que hago" in text_lower or "aconsejame" in text_lower:
            return "advice_request"
        
        if "hora" in text_lower:
            return "time_request"
        
        if "que debo comer" in text_lower or "que comer" in text_lower:
            return "meal_request"
        
        if "cambia tu" in text_lower or "personaliza" in text_lower:
            return "personalization"
        
        if "estudiar" in text_lower or "modo estudio" in text_lower:
            return "study_mode"
        
        if "hola" in text_lower or "buenos" in text_lower or "que tal" in text_lower:
            return "greeting"
        
        return "general"

    async def handle_music_request(self, text: str) -> str:
        query = text.lower()
        remove_words = ["pon", "ponme", "reproduce", "la cancion", "por favor", "porfa"]
        for word in remove_words:
            query = query.replace(word, "")
        query = " ".join(query.split())
        
        if not query or len(query) < 2:
            query = "musica relajante"
        
        print(f"Buscando musica para: '{query}'")
        song = self.music.find_song(query)
        
        if song and song.get('url'):
            self.music.play(song)
            response = f"Reproduciendo '{query}' en tu navegador"
            self.voice.speak(response)
            return response
        else:
            response = f"No pude encontrar '{query}'. Prueba con otro nombre"
            self.voice.speak(response)
            return response
        
    async def handle_music_stop(self) -> str:
        self.music.stop()
        response = "Musica detenida."
        self.voice.speak(response)
        return response

    async def handle_task_add(self, text: str) -> str:
        patterns = [r"recuerdame", r"agrega tarea", r"nueva tarea", r"debo hacer"]
        task = text
        for pattern in patterns:
            task = re.sub(pattern, "", task, flags=re.I)
        task = task.strip()
        
        if not task or len(task) < 3:
            response = "Que tarea quieres que agregue? Dime los detalles."
            self.voice.speak(response)
            return response
        
        invalid_tasks = ["que tareas tengo", "ver tareas", "mis tareas"]
        if task.lower() in invalid_tasks:
            response = "Eso no es una tarea. Quieres ver tus tareas pendientes?"
            self.voice.speak(response)
            return response
        
        self.tasks.add(task)
        response = f"Listo! He agregado '{task}' a tus tareas."
        self.voice.speak(response)
        return response

    async def handle_list_tasks(self) -> str:
        pending = self.tasks.get_pending()
        if not pending:
            response = "No tienes tareas pendientes. Buen trabajo!"
            self.voice.speak(response)
            return response
        
        task_list = "\n".join([f"{i+1}. {t['title']}" for i, t in enumerate(pending)])
        response = f"Tus tareas pendientes:\n{task_list}"
        self.voice.speak(response)
        return response

    async def handle_greeting(self) -> str:
        greetings = [
            f"Hola {self.user_name}! Como estas hoy?",
            f"Que gusto verte {self.user_name}! En que puedo ayudarte?",
            f"Hey {self.user_name}! Cuentame, como va tu dia?"
        ]
        response = random.choice(greetings)
        self.voice.speak(response)
        return response

    async def handle_study_mode(self, text: str) -> str:
        subject = re.sub(r"(estudiar|modo estudio|ayudame a estudiar|repasar|estudio)", "", text, flags=re.I).strip()
        if not subject:
            subject = "general"
        self.study.start_session(subject)
        response = self.study.get_welcome_message(subject, self.personality)
        self.voice.speak(response)
        return response

    async def handle_advice(self, text: str, emotion_data: dict) -> str:
        text_lower = text.lower()
        
        # Detectar preguntas de musica
        if "musica" in text_lower and ("recomienda" in text_lower or "recomiendas" in text_lower or "que musica" in text_lower):
            songs = ["Despacito - Luis Fonsi", "Felices los 4 - Maluma", "Tusa - Karol G", "Hawái - Maluma"]
            selected = random.sample(songs, 2)
            
            self.last_recommendations.append({
                "type": "music_recommendation",
                "songs": selected,
                "timestamp": datetime.now().isoformat()
            })
            self.last_recommendations = self.last_recommendations[-5:]
            response = f"Te recomiendo escuchar '{selected[0]}' y '{selected[1]}'."
            self.voice.speak(response)
            return response
        
        context = self.brain.get_recent_context()
        advice = self.brain.generate_advice(text, emotion_data, context, self.personality)
        
        self.last_recommendations.append({
            "type": "advice",
            "content": advice,
            "timestamp": datetime.now().isoformat()
        })
        self.last_recommendations = self.last_recommendations[-5:]
        
        self.voice.speak(advice)
        return advice

    async def handle_play_recommended(self, reference: str) -> str:
        print(f"DEBUG: handle_play_recommended llamado con: '{reference}'")
        
        generic_patterns = ["ponla", "ponla entonces", "pon esa", "pon esa cancion", "reproduce esa", "tocame esa"]
        
        if any(pattern in reference for pattern in generic_patterns):
            music_recs = [rec for rec in self.last_recommendations if rec.get("type") == "music_recommendation"]
            if not music_recs:
                return "No tengo ninguna recomendacion reciente. Dime que cancion quieres escuchar."
            
            last_rec = music_recs[-1]
            songs = last_rec.get("songs", [])
            if not songs:
                return "No recuerdo las canciones que recomende. Dime el nombre de la cancion."
            
            song_to_play = songs[0]
            return await self.handle_music_request(f"pon {song_to_play}")
        
        index_map = {
            "la primera": 0, "la segunda": 1, "la tercera": 2,
            "la ultima": -1, "la que me dijiste": 0, "la que me recomendaste": 0
        }
        
        idx = None
        for key, value in index_map.items():
            if key in reference:
                idx = value
                break
        
        if idx is None:
            idx = 0
        
        music_recs = [rec for rec in self.last_recommendations if rec.get("type") == "music_recommendation"]
        if not music_recs:
            return "No tengo ninguna recomendacion reciente. Dime que cancion quieres escuchar."
        
        last_rec = music_recs[-1]
        songs = last_rec.get("songs", [])
        
        if not songs:
            return "No recuerdo las canciones que recomende. Dime el nombre de la cancion."
        
        if idx == -1:
            song_to_play = songs[-1]
        elif idx < len(songs):
            song_to_play = songs[idx]
        else:
            song_to_play = songs[0]
        
        return await self.handle_music_request(f"pon {song_to_play}")

    async def handle_personalization(self, text: str) -> str:
        text_lower = text.lower()
        
        if "nombre" in text_lower:
            match = re.search(r"nombre\s*(?:sea|es|llame|a)?\s*([a-zA-Záéíóúñ]+)", text, re.I)
            if match:
                new_name = match.group(1).capitalize()
                response = self.personalize("name", new_name)
                self.voice.speak(response)
                return response
            return "Para cambiar mi nombre, escribe: 'cambia tu nombre a [nombre]'"
        
        if "actitud" in text_lower:
            attitudes = {"calida": "calida y empatica", "energetica": "energetica", "divertida": "divertida", "seria": "seria"}
            for key, value in attitudes.items():
                if key in text_lower:
                    response = self.personalize("attitude", value)
                    self.voice.speak(response)
                    return response
            return "Actitudes disponibles: calida, energetica, divertida, seria"
        
        if "humor" in text_lower:
            levels = ["bajo", "moderado", "alto"]
            for level in levels:
                if level in text_lower:
                    response = self.personalize("humor_level", level)
                    self.voice.speak(response)
                    return response
            return "Niveles de humor: bajo, moderado, alto"
        
        return "Que quieres personalizar? Puedes cambiar: nombre, actitud, humor"

    def get_time(self) -> str:
        now = datetime.now()
        response = "Son las {} del {}".format(now.strftime("%H:%M"), now.strftime("%A %d de %B"))
        self.voice.speak(response)
        return response

    def style_response(self, text: str) -> str:
        if not self.personality["use_emojis"]:
            text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF]', '', text)
        return text

    async def handle_list_classes(self) -> str:
        """Lista las clases del horario semanal"""
        weekly_schedule = self.scheduler.get_weekly_schedule()
        
        days = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
        day_names = {'lunes': 'Lunes', 'martes': 'Martes', 'miercoles': 'Miercoles', 'jueves': 'Jueves', 'viernes': 'Viernes', 'sabado': 'Sabado', 'domingo': 'Domingo'}
        
        schedule_text = []
        for day in days:
            classes = weekly_schedule.get(day, [])
            if classes:
                day_text = f"{day_names[day]}: "
                class_list = []
                for cls in classes:
                    class_list.append(f"{cls.get('course', cls.get('name', 'Clase'))} ({cls['start']}-{cls['end']})")
                day_text += ", ".join(class_list)
                schedule_text.append(day_text)
        
        if not schedule_text:
            response = "No tienes clases agendadas en tu horario. Puedes agregarlas desde el panel de horario."
        else:
            current_course = self.scheduler.get_current_course()
            current_day = self.scheduler.get_day_name()
            day_names_es = {'lunes': 'Lunes', 'martes': 'Martes', 'miercoles': 'Miercoles', 'jueves': 'Jueves', 'viernes': 'Viernes', 'sabado': 'Sabado', 'domingo': 'Domingo'}
            
            response = "Tu horario de clases: " + ", ".join(schedule_text)
            
            if current_course:
                response += f" Actualmente estas en clase de: {current_course} ({day_names_es.get(current_day, current_day)})."
        
        self.voice.speak(response)
        return response

    # ============================================================
    # INICIO Y CONTROL
    # ============================================================

    async def start(self):
        self.running = True
        self.setup_scheduled_routines()
        self.scheduler.start()
        spontaneous_task = asyncio.create_task(self.spontaneous_check())

        print("\n" + "="*50)
        print("{} ESTA LISTA".format(self.name))
        print("="*50)
        print("Comandos disponibles:")
        print("  - 'hora' -> Dime la hora")
        print("  - 'pon musica' -> Reproduce musica")
        print("  - 'para musica' -> Para la musica")
        print("  - 'recuerdame [tarea]' -> Agrega recordatorio")
        print("  - 'que tareas tengo' -> Ver tareas pendientes")
        print("  - 'que debo comer' -> Recomendacion de comida")
        print("  - 'que clases tengo' -> Ver horario de clases")
        print("  - 'cambia tu nombre a [nombre]' -> Cambiar nombre")
        print("  - 'cambia tu actitud a [actitud]' -> Cambiar actitud")
        print("  - 'salir' -> Apagar")
        print("="*50 + "\n")

        greeting = "Hola {}! Soy {}, tu amiga virtual. En que puedo ayudarte hoy?".format(self.user_name, self.name)
        print("[AURA] {}".format(greeting))
        self.voice.speak(greeting)

        while self.running:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(None, input, "Tu: ")

                if user_input.lower() in ['salir', 'exit', 'adios', 'bye', 'apagar']:
                    farewell = "Nos vemos, {}. Cuidate mucho!".format(self.user_name)
                    print("[AURA] {}".format(farewell))
                    self.voice.speak(farewell)
                    self.running = False
                    break

                await self.chat(user_input)

            except KeyboardInterrupt:
                print("\n\nHasta luego!")
                self.running = False
                break
            except Exception as e:
                print("\nError: {}".format(e))
                continue

        spontaneous_task.cancel()
        self.scheduler.stop()

    def stop(self):
        self.running = False


if __name__ == "__main__":
    api_key = solicitar_api_key()
    
    if api_key:
        try:
            user_profile_path = Path("config/user_profile.json")
            if user_profile_path.exists():
                with open(user_profile_path, 'r', encoding='utf-8') as f:
                    user_profile = json.load(f)
            else:
                user_profile = {}
            
            if "groq_config" not in user_profile:
                user_profile["groq_config"] = {}
            
            user_profile["groq_config"]["api_key"] = api_key
            user_profile["groq_config"]["use_groq"] = True
            user_profile["groq_config"]["model"] = "llama3-8b-8192"
            
            Path("config").mkdir(exist_ok=True)
            with open(user_profile_path, 'w', encoding='utf-8') as f:
                json.dump(user_profile, f, ensure_ascii=False, indent=2)
            
            print("API key guardada en el perfil\n")
        except Exception as e:
            print(f"No se pudo guardar la API key: {e}")
    
    amigo = AmigoVirtual()
    
    try:
        asyncio.run(amigo.start())
    except Exception as e:
        print("Error fatal: {}".format(e))