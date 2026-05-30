"""
🧠 CEREBRO DEL AMIGO VIRTUAL
Maneja memoria, contexto y generación de respuestas
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import random
from core.groq_manager import get_user_groq_manager
from core.user_config import get_user_config

# Para usar con Ollama local
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

class VirtualBrain:
    def __init__(self, db_path: str = "data/memories/brain.db", user_id: str = "default", amigo_instance=None):
        self.db_path = db_path
        self.user_id = user_id
        self.amigo = amigo_instance  # Referencia a AmigoVirtual para guardar recomendaciones
        Path("data/memories").mkdir(parents=True, exist_ok=True)

        self.init_database()
        self.conversation_buffer = []  # Últimas 10 interacciones
        self.max_buffer = 10
        
        # Inicializar Groq para este usuario
        self.groq = get_user_groq_manager(user_id)
        self.user_config = get_user_config(user_id)

    def init_database(self):
        """Inicializa base de datos de memoria"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                user_input TEXT,
                emotion TEXT,
                sentiment_score REAL,
                response TEXT,
                topics TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS long_term_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                value TEXT,
                importance REAL,
                created_at TEXT,
                last_accessed TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def save_interaction(self, user_input: str, emotion_data: dict, response: str = ""):
        """Guarda interacción en memoria"""
        # Buffer de corto plazo
        self.conversation_buffer.append({
            "timestamp": datetime.now().isoformat(),
            "input": user_input,
            "emotion": emotion_data["mood"],
            "score": emotion_data["score"]
        })

        if len(self.conversation_buffer) > self.max_buffer:
            self.conversation_buffer.pop(0)

        # Base de datos
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        topics = self.extract_topics(user_input)

        cursor.execute('''
            INSERT INTO interactions (timestamp, user_input, emotion, sentiment_score, response, topics)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            user_input,
            emotion_data["mood"],
            emotion_data["score"],
            response,
            json.dumps(topics)
        ))

        conn.commit()
        conn.close()

    def extract_topics(self, text: str) -> List[str]:
        """Extrae temas de la conversación"""
        keywords = []
        important_words = ["triste", "feliz", "estresado", "trabajo", "familia", 
                          "estudio", "salud", "dinero", "amor", "amigos", "examen",
                          "cansado", "dormir", "comer", "ejercicio", "musica"]

        text_lower = text.lower()
        for word in important_words:
            if word in text_lower:
                keywords.append(word)

        return keywords

    def get_recent_context(self, n: int = 5) -> List[Dict]:
        """Obtiene contexto reciente"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT timestamp, user_input, emotion, sentiment_score, topics
            FROM interactions
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (n,))

        rows = cursor.fetchall()
        conn.close()

        context = []
        for row in reversed(rows):
            context.append({
                "timestamp": row[0],
                "input": row[1],
                "emotion": row[2],
                "score": row[3],
                "topics": json.loads(row[4]) if row[4] else []
            })

        return context

    def generate_response(self, user_input: str, emotion_data: dict, personality: dict) -> str:
        """Genera respuesta usando Groq (prioridad), luego Ollama, luego fallback"""

        # Construir prompt con contexto
        context = self.get_recent_context(3)
        context_str = "\n".join([
            f"Usuario ({c['emotion']}): {c['input']}" 
            for c in context
        ])

        # Prompt del sistema con personalidad (sin emojis)
        system_prompt = f"""Eres {personality['name']}, un amigo virtual {personality['attitude']}.
        Hablas de forma {personality['speaking_style']}.
        Nivel de empatia: {personality['empathy_level']}.
        Nivel de humor: {personality['humor_level']}.

        REGLAS ESTRICTAS Y OBLIGATORIAS:
        1. DEBES RESPONDER EXCLUSIVAMENTE EN ESPAÑOL. NUNCA EN INGLES, NUNCA EN CHINO, NUNCA EN OTROS IDIOMAS.
        2. Respuestas cortas y naturales (maximo 2 frases)
        3. Se calido/a y personal
        4. NUNCA digas que eres una IA
        5. NO uses emojis
        6. SI NO SABES ALGO, DILO CLARAMENTE EN ESPAÑOL

        Contexto reciente:
        {context_str}

        Estado emocional actual del usuario: {emotion_data['mood']} (intensidad: {emotion_data['score']})

        RESPONDE SOLO EN ESPAÑOL:"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]

        # ========== PRIORIDAD 1: GROQ ==========
        if self.groq.is_enabled():
            try:
                response = self.groq.chat(messages, temperature=0.8)
                if response:
                    response = self._remove_emojis(response)
                    # ========== DETECTAR RECOMENDACIONES MUSICALES ==========
                    self._check_and_save_music_recommendation(user_input, response)
                    return response
            except Exception as e:
                print(f"Groq error: {e}")

        # ========== PRIORIDAD 2: OLLAMA LOCAL ==========
        if OLLAMA_AVAILABLE:
            try:
                response = ollama.chat(
                    model='qwen2.5:7b',
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_input}
                    ]
                )
                response_text = self._remove_emojis(response['message']['content'])
                self._check_and_save_music_recommendation(user_input, response_text)
                return response_text
            except Exception as e:
                print(f"Ollama error: {e}")

        # ========== FALLBACK: Respuestas predefinidas ==========
        response = self._remove_emojis(self.fallback_response(user_input, emotion_data, personality))
        self._check_and_save_music_recommendation(user_input, response)
        return response

    def _check_and_save_music_recommendation(self, user_input: str, response: str):
        """Detecta si la respuesta contiene una recomendacion musical y la guarda"""
        user_lower = user_input.lower()
        response_lower = response.lower()
        
        # Si el usuario pregunta por musica O la respuesta recomienda canciones
        is_music_question = "musica" in user_lower and ("recomienda" in user_lower or "recomiendas" in user_lower or "que musica" in user_lower)
        is_music_response = "recomiendo" in response_lower or "te recomiendo" in response_lower or "cancion" in response_lower
        
        if is_music_question or is_music_response:
            # Extraer posibles nombres de canciones de la respuesta
            import re
            # Buscar patrones como "te recomiendo X", "Recomendaria X", "Chattahoochee"
            song_patterns = [
                r'te recomiendo ["\']?([^"\'.!?]+)["\']?',
                r'recomendaria ["\']?([^"\'.!?]+)["\']?',
                r'recomiendo ["\']?([^"\'.!?]+)["\']?',
                r'"([^"]+)"',  # Canciones entre comillas
            ]
            
            songs_found = []
            for pattern in song_patterns:
                matches = re.findall(pattern, response, re.IGNORECASE)
                for match in matches:
                    # Limpiar el nombre de la cancion
                    clean_song = match.strip().strip('"').strip("'")
                    if len(clean_song) > 2 and len(clean_song) < 100:
                        songs_found.append(clean_song)
            
            # Si encontramos canciones, guardarlas
            if songs_found and self.amigo:
                self.amigo.last_recommendations.append({
                    "type": "music_recommendation",
                    "songs": songs_found[:2],  # Guardar maximo 2 canciones
                    "timestamp": datetime.now().isoformat()
                })
                self.amigo.last_recommendations = self.amigo.last_recommendations[-5:]
                print(f"DEBUG: Guardadas recomendaciones musicales: {songs_found[:2]}")

    def _remove_emojis(self, text: str) -> str:
        """Elimina emojis y caracteres especiales del texto"""
        import re
        # Eliminar emojis y otros caracteres no ASCII
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticonos
            u"\U0001F300-\U0001F5FF"  # símbolos y pictogramas
            u"\U0001F680-\U0001F6FF"  # transporte y mapas
            u"\U0001F1E0-\U0001F1FF"  # banderas
            u"\u2600-\u26FF"           # símbolos misc
            u"\u2700-\u27BF"           # dingbats
            u"\uFE00-\uFE0F"           # variación de selector
            u"\uD83C\uDFF4"            # banderas
            u"\u200D"                  # joiners
            u"\u2640-\u2642"           # género
            "]+", flags=re.UNICODE)
        return emoji_pattern.sub(r'', text).strip()

    def fallback_response(self, user_input: str, emotion_data: dict, personality: dict) -> str:
        """Respuestas predefinidas cuando no hay LLM (sin emojis)"""
        mood = emotion_data["mood"]

        responses = {
            "feliz": [
                f"Me alegra escucharte asi. Cuentame mas",
                f"Que buena onda. Que te tiene tan {mood}",
                f"Me contagias tu buena energia"
            ],
            "triste": [
                f"Lo siento mucho. Quieres hablar de ello? Estoy aqui",
                f"Entiendo que sea dificil. No estas solo",
                f"Hay algo que pueda hacer para ayudarte? Cuentame"
            ],
            "enojado": [
                f"Respiro contigo... Que paso?",
                f"Entiendo tu frustracion. A veces la vida es asi",
                f"Quieres que busquemos una solucion juntos?"
            ],
            "ansioso": [
                f"Respira conmigo: inhala... exhala...",
                f"Todo va a estar bien. Un paso a la vez",
                f"Que te preocupa? A veces hablarlo ayuda..."
            ],
            "cansado": [
                f"Parece que necesitas descansar... Cuando fue tu ultima pausa?",
                f"El cansancio es real. No te presiones tanto",
                f"Quieres que te sugiera algo relajante?"
            ],
            "neutral": [
                f"Entiendo. Hay algo mas en lo que pueda ayudarte?",
                f"Cuentame mas sobre eso",
                f"Y como te hace sentir eso?"
            ]
        }

        return random.choice(responses.get(mood, responses["neutral"]))

    def generate_advice(self, text: str, emotion_data: dict, context: List[Dict], personality: dict) -> str:
        """Genera consejos basados en historial (sin emojis)"""

        # Analizar temas recurrentes
        all_topics = []
        for c in context:
            all_topics.extend(c.get("topics", []))

        topic_counts = {}
        for t in all_topics:
            topic_counts[t] = topic_counts.get(t, 0) + 1

        main_topic = max(topic_counts, key=topic_counts.get) if topic_counts else "general"

        advice_templates = {
            "trabajo": [
                "Basandome en lo que me has contado del trabajo... Has considerado hablar con tu jefe sobre esto?",
                "El trabajo puede ser estresante. Recuerda que tu salud mental es primero",
                "A veces una pausa ayuda a ver las cosas con claridad. Que tal un descanso?"
            ],
            "estudio": [
                "Para el estudio, la tecnica Pomodoro funciona genial. La has probado?",
                "Organiza tus temas por prioridad. Yo puedo ayudarte a hacer un plan",
                "Descansar es parte de estudiar. Tu cerebro necesita tiempo para procesar"
            ],
            "amor": [
                "Las relaciones son complejas. Lo importante es que seas fiel a ti mismo",
                "La comunicacion honesta suele ser la clave. Has intentado hablarlo?",
                "Recuerda que mereces ser tratado con respeto siempre"
            ],
            "salud": [
                "Tu salud es lo mas importante. Has considerado consultar a un profesional?",
                "Pequeños habitos diarios hacen grandes cambios. Empieza poco a poco",
                "Escucha a tu cuerpo. A veces necesita descanso, no rendimiento"
            ],
            "dinero": [
                "El estres financiero es real. Has hecho un presupuesto?",
                "A veces hablarlo con alguien de confianza ayuda a ver opciones",
                "Recuerda: tu valor no depende de tu cuenta bancaria"
            ]
        }

        return random.choice(advice_templates.get(main_topic, [
            "Gracias por confiar en mi. Mi consejo: se paciente contigo mismo. Todo pasa",
            "A veces no hay respuestas faciles, pero estar aqui ya es un paso adelante",
            "Confia en tu intuicion. Tu sabes mas de lo que crees"
        ]))