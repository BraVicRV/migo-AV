
"""
CEREBRO DEL AMIGO VIRTUAL v3 — MEMORIA POR USUARIO + SUPABASE
- Memoria local SQLite (rápida, offline)
- Sincronización con Supabase (multi-dispositivo, backup)
- SALUDO HONESTO: nunca alucina, solo usa facts confirmados
"""

import json
import re
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from core.groq_manager import get_user_groq_manager
from core.user_config import get_user_config

# Importar Supabase si está disponible
try:
    from core.supabase_client import get_supabase_manager
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("[Brain] Supabase no disponible, funcionando en modo offline")

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


SUMMARY_EVERY_N = 6
KEEP_RECENT_N = 3

CURIOSITY_QUESTIONS = {
    "family": ["Como estan tu familia ultimamente?", "Hablaste con tu familia recientemente?"],
    "work": ["Como va el trabajo o los estudios?", "Hay algun proyecto que te tenga ocupado?"],
    "hobbies": ["Has tenido tiempo para tus hobbies ultimamente?", "Hay algo nuevo que quieras aprender?"],
    "social": ["Viste a tus amigos recientemente?", "Como va tu vida social?"],
    "health": ["Como has dormido ultimamente?", "Has hecho algo de ejercicio?"],
    "goals": ["Como van esos objetivos que me mencionaste?", "En que te gustaria enfocarte estos dias?"],
    "emotions": ["En que momento del dia te sientes mejor?", "Que te hace sonreir estos dias?"]
}


class UserProfile:
    """Perfil enriquecido del usuario que evoluciona con cada interaccion."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.data = {
            "basic_info": {},
            "interests": set(),
            "relationships": {},
            "goals": [],
            "emotional_patterns": {},
            "conversation_topics": [],
            "last_topics": [],
            "known_facts": set(),
            "unknown_areas": set(["family", "work", "hobbies", "social", "health", "goals", "emotions"]),
            "interaction_count": 0,
            "last_interaction": None,
            "first_interaction": None,
        }

    def update_from_interaction(self, user_input: str, emotion: str, topics: List[str]):
        self.data["interaction_count"] += 1
        self.data["last_interaction"] = datetime.now().isoformat()
        if not self.data["first_interaction"]:
            self.data["first_interaction"] = self.data["last_interaction"]

        self.data["last_topics"] = topics
        for topic in topics:
            if topic not in self.data["conversation_topics"]:
                self.data["conversation_topics"].append(topic)

        # Patrones emocionales temporales
        hour = datetime.now().hour
        day = datetime.now().strftime("%A")
        key = f"{day}_{hour//4}"
        if key not in self.data["emotional_patterns"]:
            self.data["emotional_patterns"][key] = []
        self.data["emotional_patterns"][key].append(emotion)
        if len(self.data["emotional_patterns"][key]) > 10:
            self.data["emotional_patterns"][key] = self.data["emotional_patterns"][key][-10:]

        self._extract_interests(user_input)
        self._extract_goals(user_input)
        self._update_unknown_areas(user_input, topics)

    def _extract_interests(self, text: str):
        patterns = [r"me gusta (\w+)", r"me encanta (\w+)", r"amo (\w+)", r"me apasiona (\w+)"]
        for pattern in patterns:
            for match in re.findall(pattern, text.lower()):
                self.data["interests"].add(match.strip())

    def _extract_goals(self, text: str):
        patterns = [r"quiero (\w+ .{3,30})", r"mi meta es (\w+ .{3,30})", r"mi objetivo es (\w+ .{3,30})"]
        for pattern in patterns:
            for match in re.findall(pattern, text.lower()):
                goal = match.strip()
                if goal and len(goal) > 5 and goal not in self.data["goals"]:
                    self.data["goals"].append(goal)
                    if len(self.data["goals"]) > 10:
                        self.data["goals"].pop(0)

    def _update_unknown_areas(self, text: str, topics: List[str]):
        area_keywords = {
            "family": ["familia", "mama", "papa", "hermano", "hermana", "hijo", "hija"],
            "work": ["trabajo", "estudio", "universidad", "escuela", "clase", "examen", "proyecto"],
            "hobbies": ["hobby", "pasatiempo", "juego", "deporte", "musica", "pelicula"],
            "social": ["amigo", "amiga", "salir", "fiesta", "reunion", "cita"],
            "health": ["dormir", "ejercicio", "gym", "comida", "salud", "enfermo", "cansado"],
            "goals": ["meta", "objetivo", "plan", "futuro", "lograr", "aprender"],
            "emotions": ["siento", "emocion", "animo", "estres", "ansiedad", "feliz", "triste"]
        }
        text_lower = text.lower()
        for area, keywords in area_keywords.items():
            if any(kw in text_lower or kw in topics for kw in keywords):
                self.data["unknown_areas"].discard(area)
                self.data["known_facts"].add(area)

    def get_emotional_pattern(self) -> str:
        patterns = self.data["emotional_patterns"]
        if not patterns:
            return ""
        negative_emotions = {"triste", "ansioso", "enojado", "cansado"}
        insights = []
        for key, emotions in patterns.items():
            if len(emotions) >= 3:
                neg_count = sum(1 for e in emotions if e in negative_emotions)
                if neg_count / len(emotions) > 0.6:
                    day, hour_block = key.split("_")
                    hour_start = int(hour_block) * 4
                    hour_end = hour_start + 4
                    days_es = {"Monday": "los lunes", "Tuesday": "los martes", "Wednesday": "los miercoles",
                              "Thursday": "los jueves", "Friday": "los viernes", "Saturday": "los sabados",
                              "Sunday": "los domingos"}
                    insights.append(f"Sueles estar {emotions[-1]} {days_es.get(day, day)} entre {hour_start}:00 y {hour_end}:00")
        return "; ".join(insights[:2]) if insights else ""

    def get_curiosity_prompt(self) -> Optional[str]:
        unknown = self.data["unknown_areas"]
        if not unknown:
            return None
        area = random.choice(list(unknown))
        questions = CURIOSITY_QUESTIONS.get(area, ["Como te sientes hoy?"])
        name = self.data["basic_info"].get("name", "")
        if name and random.random() > 0.5:
            return f"{name}, {random.choice(questions).lower()}"
        return random.choice(questions)

    def get_context_for_greeting(self) -> Dict:
        context = {
            "name": self.data["basic_info"].get("name", ""),
            "last_topics": self.data["last_topics"],
            "goals": self.data["goals"],
            "emotional_pattern": self.get_emotional_pattern(),
            "interaction_count": self.data["interaction_count"],
            "unknown_areas": list(self.data["unknown_areas"]),
            "interests": list(self.data["interests"]),
        }
        if self.data["last_interaction"]:
            last = datetime.fromisoformat(self.data["last_interaction"])
            hours_ago = (datetime.now() - last).total_seconds() / 3600
            context["hours_since_last"] = round(hours_ago, 1)
        else:
            context["hours_since_last"] = None
        return context

    def to_dict(self) -> dict:
        return {
            "basic_info": self.data["basic_info"],
            "interests": list(self.data["interests"]),
            "relationships": self.data["relationships"],
            "goals": self.data["goals"],
            "emotional_patterns": self.data["emotional_patterns"],
            "conversation_topics": self.data["conversation_topics"],
            "known_facts": list(self.data["known_facts"]),
            "unknown_areas": list(self.data["unknown_areas"]),
            "interaction_count": self.data["interaction_count"],
            "last_interaction": self.data["last_interaction"],
            "first_interaction": self.data["first_interaction"],
        }

    @classmethod
    def from_dict(cls, user_id: str, data: dict) -> "UserProfile":
        profile = cls(user_id)
        profile.data["basic_info"] = data.get("basic_info", {})
        profile.data["interests"] = set(data.get("interests", []))
        profile.data["relationships"] = data.get("relationships", {})
        profile.data["goals"] = data.get("goals", [])
        profile.data["emotional_patterns"] = data.get("emotional_patterns", {})
        profile.data["conversation_topics"] = data.get("conversation_topics", [])
        profile.data["known_facts"] = set(data.get("known_facts", []))
        profile.data["unknown_areas"] = set(data.get("unknown_areas", 
            ["family", "work", "hobbies", "social", "health", "goals", "emotions"]))
        profile.data["interaction_count"] = data.get("interaction_count", 0)
        profile.data["last_interaction"] = data.get("last_interaction")
        profile.data["first_interaction"] = data.get("first_interaction")
        return profile


class VirtualBrain:
    def __init__(self, user_id: str = "default", amigo_instance=None):
        self.user_id = user_id
        self.amigo = amigo_instance

        # Base de datos local SQLite (rápida, offline)
        self.db_path = f"data/memories/brain_{user_id}.db"
        Path("data/memories").mkdir(parents=True, exist_ok=True)

        # Perfil local
        self.profile_path = f"data/memories/profile_{user_id}.json"

        # Supabase para sincronización en la nube
        self.supabase = get_supabase_manager() if SUPABASE_AVAILABLE else None

        # Cargar perfil (con sincronización desde Supabase)
        self.user_profile = self._load_profile()

        self.init_database()

        self.conversation_buffer: List[Dict] = []
        self.conversation_summary: str = ""
        self.interactions_since_summary: int = 0

        self.groq = get_user_groq_manager(user_id)
        self.user_config = get_user_config(user_id)

        # NO cargar resúmenes viejos al inicio (evitan alucinación)
        self._load_last_summary_safe()

    # ============================================================
    # SINCRONIZACIÓN CON SUPABASE
    # ============================================================

    def _sync_from_cloud(self):
        """Carga perfil desde Supabase si existe y es más reciente."""
        if not self.supabase or not self.supabase.is_connected():
            return

        try:
            cloud_profile = self.supabase.load_user_profile(self.user_id)
            if not cloud_profile:
                return

            # Si el perfil local es más reciente, no sobrescribir
            if Path(self.profile_path).exists():
                try:
                    with open(self.profile_path, "r", encoding="utf-8") as f:
                        local = json.load(f)
                    local_time = local.get("last_interaction", "2000-01-01")
                    cloud_time = cloud_profile.get("last_interaction", "2000-01-01")
                    if local_time and cloud_time and local_time > cloud_time:
                        return  # Local es más reciente
                except:
                    pass

            # Usar perfil de la nube
            self.user_profile = UserProfile.from_dict(self.user_id, cloud_profile)
            self._save_profile_local()
            print(f"[Brain] Perfil sincronizado desde Supabase para {self.user_id}")
        except Exception as e:
            print(f"[Brain] Error sincronizando desde Supabase: {e}")

    def _sync_to_cloud(self):
        """Guarda perfil en Supabase."""
        if not self.supabase or not self.supabase.is_connected():
            return

        try:
            self.supabase.save_user_profile(self.user_id, self.user_profile.to_dict())

            # Sincronizar facts también
            facts = self.get_user_facts()
            if facts:
                self.supabase.sync_user_facts(self.user_id, facts)
        except Exception as e:
            print(f"[Brain] Error sincronizando a Supabase: {e}")

    def _load_profile(self) -> UserProfile:
        """Carga perfil con sincronización desde Supabase."""
        # 1. Intentar sincronizar desde la nube primero
        self._sync_from_cloud()

        # 2. Cargar desde local (ya sincronizado o original)
        if Path(self.profile_path).exists():
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return UserProfile.from_dict(self.user_id, data)
            except Exception as e:
                print(f"[Brain] Error cargando perfil local: {e}")

        return UserProfile(self.user_id)

    def _save_profile(self):
        """Guarda perfil local y sincroniza con Supabase."""
        self._save_profile_local()
        self._sync_to_cloud()

    def _save_profile_local(self):
        """Guarda perfil solo en disco local."""
        try:
            with open(self.profile_path, "w", encoding="utf-8") as f:
                json.dump(self.user_profile.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Brain] Error guardando perfil local: {e}")

    # ============================================================
    # BASE DE DATOS SQLITE
    # ============================================================

    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                user_input TEXT,
                emotion TEXT,
                sentiment_score REAL,
                response TEXT,
                topics TEXT,
                context TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS long_term_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                value TEXT,
                importance REAL,
                created_at TEXT,
                last_accessed TEXT,
                category TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                summary TEXT,
                follow_up_questions TEXT,
                interactions_covered INTEGER,
                mood_at_summary TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                description TEXT,
                event_date TEXT,
                created_at TEXT,
                completed INTEGER DEFAULT 0
            )
        """)

        conn.commit()
        conn.close()

    # ============================================================
    # GUARDAR INTERACCIÓN
    # ============================================================

    def save_interaction(self, user_input: str, emotion_data: dict, response: str = ""):
        emotion = emotion_data.get("mood", "neutral")
        topics = self.extract_topics(user_input)

        # Actualizar perfil del usuario
        self.user_profile.update_from_interaction(user_input, emotion, topics)
        self._save_profile()  # Guarda local + Supabase

        entry = {
            "timestamp": datetime.now().isoformat(),
            "input": user_input,
            "response": response,
            "emotion": emotion,
            "score": emotion_data.get("score", 0.0)
        }

        self.conversation_buffer.append(entry)
        if len(self.conversation_buffer) > KEEP_RECENT_N:
            self.conversation_buffer.pop(0)

        self.interactions_since_summary += 1

        # Guardar en SQLite local
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO interactions (timestamp, user_input, emotion, sentiment_score, response, topics, context)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            entry["timestamp"], user_input, emotion, emotion_data.get("score", 0.0),
            response, json.dumps(topics), json.dumps(self.user_profile.to_dict())
        ))
        conn.commit()
        conn.close()

        self._extract_user_facts(user_input)

        if self.interactions_since_summary >= SUMMARY_EVERY_N:
            self._generate_and_save_summary(emotion)
            self.interactions_since_summary = 0

    # ============================================================
    # SALUDOS PROACTIVOS - HONESTOS, SIN ALUCINACIÓN
    # ============================================================

    def generate_proactive_greeting(self) -> str:
        """Genera un saludo proactivo basado SOLO en facts confirmados y estado emocional real."""
        context = self.user_profile.get_context_for_greeting()
        name = context.get("name", "")
        name_prefix = f"{name}, " if name else ""

        # Usuario nuevo
        if context["interaction_count"] == 0:
            return f"Hola! Soy AURA. Me gustaria conocerte mejor. {name_prefix}Como te llamas?"

        # 1. PRIORIDAD: Detectar estado emocional negativo reciente y ofrecer apoyo
        recent_emotions = self._get_recent_emotional_state()
        if recent_emotions["is_negative"] and recent_emotions["confidence"] > 0.5:
            if recent_emotions["dominant"] == "triste":
                return f"Hola {name_prefix}Se que no ha sido facil ultimamente. Estoy aqui contigo, en lo que necesites."
            elif recent_emotions["dominant"] == "ansioso":
                return f"Hola {name_prefix}Respira conmigo. Un paso a la vez. En que puedo ayudarte hoy?"
            elif recent_emotions["dominant"] == "cansado":
                return f"Hola {name_prefix}Parece que has tenido dias pesados. Tomate tu tiempo, estoy aqui."
            elif recent_emotions["dominant"] == "enojado":
                return f"Hola {name_prefix}Entiendo que las cosas han sido frustrantes. Quieres hablar de ello?"

        # 2. Si pasó mucho tiempo, saludo simple sin inventar contexto
        if context.get("hours_since_last") and context["hours_since_last"] > 24:
            return f"Hola {name_prefix}Hace tiempo que no hablamos. Como has estado?"

        # 3. Solo usar metas confirmadas (facts reales), nunca resúmenes
        goals = context.get("goals", [])
        if goals and random.random() > 0.7:  # Reducido para no ser invasivo
            goal = random.choice(goals[-2:])  # Solo metas recientes
            return f"Hola {name_prefix}Como van esos planes de '{goal}'?"

        # 4. Curiosidad solo si hay áreas desconocidas (muy baja probabilidad)
        curiosity = self.user_profile.get_curiosity_prompt()
        if curiosity and random.random() > 0.85:
            return f"Hola {name_prefix}{curiosity}"

        # 5. Saludo genérico cálido (default)
        greetings = [
            f"Hola {name_prefix}En que puedo ayudarte hoy?",
            f"Hola de nuevo {name_prefix}Como te sientes?",
            f"Hey {name_prefix}Tienes algo en mente?",
            f"Hola {name_prefix}Que tal tu dia?"
        ]
        return random.choice(greetings)

    def _get_recent_emotional_state(self) -> Dict:
        """Analiza las últimas interacciones para detectar estado emocional negativo."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            # Últimas 10 interacciones
            c.execute("""
                SELECT emotion, sentiment_score FROM interactions
                ORDER BY timestamp DESC LIMIT 10
            """)
            rows = c.fetchall()
            conn.close()

            if not rows or len(rows) < 3:
                return {"is_negative": False, "confidence": 0.0, "dominant": "neutral"}

            negative_emotions = {"triste", "ansioso", "enojado", "cansado"}
            negative_count = sum(1 for r in rows if r[0] in negative_emotions)
            total = len(rows)

            # Calcular emoción dominante
            mood_counts = {}
            for r in rows:
                mood = r[0]
                mood_counts[mood] = mood_counts.get(mood, 0) + 1

            dominant = max(mood_counts, key=mood_counts.get)
            confidence = negative_count / total

            return {
                "is_negative": negative_count >= total * 0.5,
                "confidence": confidence,
                "dominant": dominant
            }
        except Exception as e:
            print(f"[Brain] Error analizando estado emocional: {e}")
            return {"is_negative": False, "confidence": 0.0, "dominant": "neutral"}

    def generate_proactive_checkin(self) -> Optional[str]:
        """Genera un mensaje proactivo basado en el estado del usuario."""
        upcoming = self._get_upcoming_events(hours=48)
        if upcoming:
            event = upcoming[0]
            return f"Recordatorio: tienes '{event['description']}' el {event['event_date']}. Necesitas ayuda con algo?"

        patterns = self.user_profile.data["emotional_patterns"]
        negative_emotions = {"triste", "ansioso", "enojado"}

        recent_negative = 0
        for key, emotions in list(patterns.items())[-3:]:
            if any(e in negative_emotions for e in emotions[-2:]):
                recent_negative += 1

        if recent_negative >= 2:
            return "He notado que has estado un poco bajo de animo ultimamente. Quieres hablar de algo?"

        if self.user_profile.data["interaction_count"] % 5 == 0:
            return self.user_profile.get_curiosity_prompt()

        return None

    # ============================================================
    # RESÚMENES CON SUPABASE - CARGA SEGURA (sin alucinación)
    # ============================================================

    def _generate_and_save_summary(self, current_mood: str = "neutral"):
        recent = self.get_recent_context(SUMMARY_EVERY_N)
        if not recent:
            return

        conversation_text = "\n".join([
            f"Usuario ({r['emotion']}): {r['input']}"
            + (f"\nAURA: {r.get('response','')}" if r.get('response') else "")
            for r in recent
        ])

        profile_context = self.user_profile.to_dict()

        prompt_system = (
            "Eres un asistente que analiza conversaciones y genera resumenes con preguntas de seguimiento. "
            "Tu resumen debe:\n"
            "1. Ser maximo 2 oraciones en espanol\n"
            "2. Identificar temas pendientes o preocupaciones no resueltas\n"
            "3. Generar 1-2 preguntas naturales para la proxima conversacion\n"
            "Responde en formato: RESUMEN: [resumen] | PREGUNTAS: [preguntas]"
        )

        messages = [
            {"role": "system", "content": prompt_system},
            {"role": "user", "content": f"Perfil: {json.dumps(profile_context, ensure_ascii=False)}\n\nConversacion:\n{conversation_text}"}
        ]

        summary = None
        follow_up = ""

        if self.groq.is_enabled():
            try:
                result = self.groq.chat(messages, temperature=0.4)
                if result and "RESUMEN:" in result:
                    parts = result.split("| PREGUNTAS:")
                    summary = parts[0].replace("RESUMEN:", "").strip()
                    follow_up = parts[1].strip() if len(parts) > 1 else ""
                else:
                    summary = result
            except Exception as e:
                print(f"[Brain] Error generando resumen: {e}")

        if not summary:
            moods = [r['emotion'] for r in recent]
            topics_all = []
            for r in recent:
                topics_all.extend(r.get('topics', []))
            dominant_mood = max(set(moods), key=moods.count) if moods else "neutral"
            topic_str = ", ".join(set(topics_all[:3])) if topics_all else "temas generales"
            summary = f"El usuario ha estado predominantemente {dominant_mood}. Temas: {topic_str}."
            follow_up = "Hay algo mas en lo que pueda ayudarte?"

        # Guardar en SQLite local
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO conversation_summaries (created_at, summary, follow_up_questions, interactions_covered, mood_at_summary)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), summary, follow_up, len(recent), current_mood))
        conn.commit()
        conn.close()

        # Guardar en Supabase para sincronización
        if self.supabase and self.supabase.is_connected():
            try:
                self.supabase.save_conversation_summary(self.user_id, summary, follow_up, current_mood)
            except Exception as e:
                print(f"[Brain] Error guardando resumen en Supabase: {e}")

        if self.conversation_summary:
            self.conversation_summary = f"{self.conversation_summary}\n[Actualizacion] {summary}"
        else:
            self.conversation_summary = summary

        if len(self.conversation_summary) > 800:
            self.conversation_summary = self._compress_summary(self.conversation_summary)

        print(f"[Brain] Resumen: {summary[:80]}... | Preguntas: {follow_up[:60]}...")

    def _load_last_summary_safe(self):
        """Carga resúmenes pero los marca como 'para referencia interna', no para el saludo."""
        # Solo cargar desde SQLite local, NO desde Supabase (para evitar alucinación)
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                SELECT summary, follow_up_questions FROM conversation_summaries
                ORDER BY created_at DESC LIMIT 2
            """)
            rows = c.fetchall()
            conn.close()
            if rows:
                summaries = []
                for r in rows:
                    summaries.append(r[0])
                    if r[1]:
                        summaries.append(f"[Pregunta pendiente: {r[1]}]")
                self.conversation_summary = " | ".join(reversed(summaries))
                print(f"[Brain] Contexto previo cargado local ({len(rows)} resumenes)")
        except Exception as e:
            print(f"[Brain] No se pudo cargar resumen previo: {e}")

    # ============================================================
    # FACTS DEL USUARIO CON SUPABASE
    # ============================================================

    def get_user_facts(self) -> Dict[str, str]:
        """Obtiene facts desde Supabase primero, luego SQLite."""
        # 1. Intentar desde Supabase (sincronización entre dispositivos)
        if self.supabase and self.supabase.is_connected():
            try:
                cloud_facts = self.supabase.get_user_facts_from_cloud(self.user_id)
                if cloud_facts:
                    return cloud_facts
            except Exception as e:
                print(f"[Brain] Error cargando facts de Supabase: {e}")

        # 2. Fallback a SQLite local
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            threshold = (datetime.now() - timedelta(days=30)).isoformat()
            c.execute("""
                SELECT key, value, category FROM long_term_memory
                WHERE importance >= 0.6 AND last_accessed >= ?
                ORDER BY importance DESC, last_accessed DESC LIMIT 15
            """, (threshold,))
            rows = c.fetchall()
            conn.close()
            return {r[0]: {"value": r[1], "category": r[2]} for r in rows}
        except Exception:
            return {}

    # ============================================================
    # RESTO DE MÉTODOS
    # ============================================================

    def _get_upcoming_events(self, hours: int = 48) -> List[Dict]:
        now = datetime.now()
        future = now + timedelta(hours=hours)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT event_type, description, event_date FROM events
            WHERE event_date BETWEEN ? AND ? AND completed = 0
            ORDER BY event_date ASC
        """, (now.isoformat(), future.isoformat()))
        rows = c.fetchall()
        conn.close()
        return [{"type": r[0], "description": r[1], "event_date": r[2]} for r in rows]

    def add_event(self, event_type: str, description: str, event_date: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO events (event_type, description, event_date, created_at)
            VALUES (?, ?, ?, ?)
        """, (event_type, description, event_date, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def _compress_summary(self, long_summary: str) -> str:
        if self.groq.is_enabled():
            try:
                messages = [
                    {"role": "system", "content": "Comprime este resumen a maximo 2 oraciones en espanol. Solo el resumen."},
                    {"role": "user", "content": long_summary}
                ]
                compressed = self.groq.chat(messages, temperature=0.2)
                if compressed:
                    return compressed
            except Exception:
                pass
        return long_summary[-600:]

    def _extract_user_facts(self, text: str):
        text_lower = text.lower()
        facts = []
        patterns = [
            (r"soy ([a-zA-Z]+)", "user_real_name", 0.75, "basic"),
            (r"me llamo ([a-zA-Záéíóúñ]+)", "user_real_name", 0.9, "basic"),
            (r"tengo (\d+) años", "user_age", 0.9, "basic"),
            (r"estoy estudiando ([a-zA-Záéíóúñ\s]+)", "user_studies", 0.8, "work"),
            (r"trabajo (?:en|de|como) ([a-zA-Záéíóúñ\s]+)", "user_job", 0.8, "work"),
            (r"(?:me gusta|amo|adoro) ([a-zA-Záéíóúñ\s]+)", "user_likes", 0.6, "hobbies"),
            (r"(?:no me gusta|odio|detesto) ([a-zA-Záéíóúñ\s]+)", "user_dislikes", 0.6, "hobbies"),
            (r"mi meta (?:es )?([a-zA-Záéíóúñ\s,.]+?)(?:\.|$)", "user_goals", 0.85, "goals"),
            (r"quiero (?:lograr|aprender|hacer) ([a-zA-Záéíóúñ\s,.]+?)(?:\.|$)", "user_goals", 0.85, "goals"),
            (r"(?:me preocupa|estoy preocupado por) ([a-zA-Záéíóúñ\s]+)", "user_worries", 0.75, "emotions"),
        ]

        for pattern, key, importance, category in patterns:
            match = re.search(pattern, text_lower)
            if match:
                value = match.group(1).strip()
                if len(value) > 2:
                    facts.append((key, value, importance, category))
                    if key == "user_real_name":
                        self.user_profile.data["basic_info"]["name"] = value.capitalize()
                    elif key == "user_age":
                        self.user_profile.data["basic_info"]["age"] = value

        if not facts:
            return

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        now = datetime.now().isoformat()

        for key, value, importance, category in facts:
            try:
                c.execute("""
                    INSERT INTO long_term_memory (key, value, importance, created_at, last_accessed, category)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value,
                        last_accessed=excluded.last_accessed,
                        category=excluded.category
                """, (key, value, importance, now, now, category))
            except Exception:
                pass

        conn.commit()
        conn.close()
        self._save_profile()  # Guarda local + Supabase

    def get_recent_context(self, n: int = 5) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT timestamp, user_input, emotion, sentiment_score, topics, response
            FROM interactions
            ORDER BY timestamp DESC
            LIMIT ?
        """, (n,))
        rows = c.fetchall()
        conn.close()
        return [{
            "timestamp": r[0], "input": r[1], "emotion": r[2], "score": r[3],
            "topics": json.loads(r[4]) if r[4] else [], "response": r[5] or ""
        } for r in reversed(rows)]

    def get_full_context_for_prompt(self) -> str:
        parts = []
        profile = self.user_profile.to_dict()
        if profile["basic_info"]:
            info_str = ", ".join(f"{k}: {v}" for k, v in profile["basic_info"].items())
            parts.append(f"[Datos del usuario] {info_str}")
        if profile["interests"]:
            parts.append(f"[Intereses] {', '.join(profile['interests'])}")
        if profile["goals"]:
            parts.append(f"[Metas] {', '.join(profile['goals'][-3:])}")
        emotional_pattern = self.user_profile.get_emotional_pattern()
        if emotional_pattern:
            parts.append(f"[Patrones emocionales] {emotional_pattern}")
        facts = self.get_user_facts()
        if facts:
            facts_str = ", ".join(f"{k.replace('_',' ')}: {v['value']}" for k, v in facts.items())
            parts.append(f"[Lo que recuerdo] {facts_str}")
        # NO incluir conversation_summary en el prompt para evitar alucinación
        if self.conversation_buffer:
            recent_lines = []
            for entry in self.conversation_buffer:
                recent_lines.append(
                    f"Usuario ({entry['emotion']}): {entry['input']}"
                    + (f"\nAURA: {entry['response']}" if entry.get('response') else "")
                )
            parts.append("[Mensajes recientes]\n" + "\n".join(recent_lines))
        return "\n\n".join(parts) if parts else ""

    def extract_topics(self, text: str) -> List[str]:
        keywords = []
        important_words = ["triste", "feliz", "estresado", "trabajo", "familia",
                           "estudio", "salud", "dinero", "amor", "amigos", "examen",
                           "cansado", "dormir", "comer", "ejercicio", "musica",
                           "tarea", "proyecto", "pareja", "jefe", "clases", "hobby",
                           "meta", "objetivo", "miedo", "ansiedad", "sueno"]
        text_lower = text.lower()
        for word in important_words:
            if word in text_lower:
                keywords.append(word)
        return keywords

    def generate_response(self, user_input: str, emotion_data: dict, personality: dict) -> str:
        full_context = self.get_full_context_for_prompt()
        emotion_str = emotion_data.get("mood", "neutral")
        secondary = emotion_data.get("secondary_mood")
        if secondary:
            emotion_str += f" con rasgos de {secondary}"
        trend = emotion_data.get("trend", "estable")
        is_new_user = self.user_profile.data["interaction_count"] < 3

        # Construir prompt sin f-strings complejos
        new_user_rule = "12. Es un usuario nuevo. Pregunta cosas sobre el para conocerlo mejor." if is_new_user else ""

        system_prompt = (
            f"Eres {personality['name']}, un amigo virtual {personality['attitude']}.\n"
            f"Hablas de forma {personality['speaking_style']}.\n"
            f"Nivel de empatia: {personality['empathy_level']}.\n"
            f"Nivel de humor: {personality['humor_level']}.\n\n"
            "REGLAS OBLIGATORIAS:\n"
            "1. Responde EXCLUSIVAMENTE EN ESPANOL. Nunca en otro idioma.\n"
            "2. Respuestas cortas y naturales (maximo 2 frases).\n"
            "3. Se calido y personal. Solo usa los [Datos del usuario] y [Lo que recuerdo] que te proporciono arriba.\n"
            "4. NUNCA digas que eres una IA o un asistente. Eres un amigo.\n"
            "5. NO uses emojis.\n"
            "6. Suena como un amigo atento, no como un manual ni soporte tecnico.\n"
            "7. Primero valida o refleja lo que el usuario dijo; luego aporta una idea concreta.\n"
            "8. Haz como maximo una pregunta de seguimiento, y solo si ayuda a continuar.\n"
            "9. Evita listas, discursos largos y frases genericas.\n"
            "10. SI NO HAY DATOS en [Lo que recuerdo] o [Datos del usuario], NO inventes que el usuario te conto algo antes. Solo responde a lo que dice ahora.\n"
            '11. NUNCA digas "me acorde que..." o "la ultima vez hablamos de..." a menos que este EXPLICITAMENTE en los datos proporcionados.\n'
            f"{new_user_rule}\n\n"
            f"{full_context}\n\n"
            f"Estado emocional actual: {emotion_str} | Tendencia: {trend}\n\n"
            "RESPONDE SOLO EN ESPANOL:"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]

        if self.groq.is_enabled():
            try:
                response = self.groq.chat(messages, temperature=0.8)
                if response:
                    response = self._remove_emojis(response)
                    self._check_and_save_music_recommendation(user_input, response)
                    return response
            except Exception as e:
                print(f"[Brain] Groq error: {e}")

        if OLLAMA_AVAILABLE:
            try:
                result = ollama.chat(model='qwen2.5:7b', messages=messages)
                response_text = self._remove_emojis(result['message']['content'])
                self._check_and_save_music_recommendation(user_input, response_text)
                return response_text
            except Exception as e:
                print(f"[Brain] Ollama error: {e}")

        response = self._remove_emojis(self.fallback_response(user_input, emotion_data, personality))
        self._check_and_save_music_recommendation(user_input, response)
        return response

    def generate_advice(self, text: str, emotion_data: dict, context: List[Dict], personality: dict) -> str:
        all_topics = []
        for c in context:
            all_topics.extend(c.get("topics", []))
        topic_counts: Dict[str, int] = {}
        for t in all_topics:
            topic_counts[t] = topic_counts.get(t, 0) + 1
        main_topic = max(topic_counts, key=topic_counts.get) if topic_counts else "general"

        if self.groq.is_enabled():
            full_context = self.get_full_context_for_prompt()
            advice_prompt = f"""Eres {personality['name']}, un amigo virtual empatico.
{full_context}
El usuario pide consejo sobre: {text}
Tema recurrente: {main_topic}
Estado emocional: {emotion_data.get('mood', 'neutral')}
Da un consejo breve (maximo 2 frases) en espanol, calido y personalizado.
NO uses emojis. Responde solo el consejo."""

            messages = [
                {"role": "system", "content": advice_prompt},
                {"role": "user", "content": text}
            ]
            try:
                advice = self.groq.chat(messages, temperature=0.7)
                if advice:
                    return self._remove_emojis(advice)
            except Exception:
                pass

        advice_templates = {
            "trabajo": ["Basandome en lo que me has contado... Has considerado hablar con tu jefe?", "El trabajo puede ser estresante. Tu salud mental es primero."],
            "estudio": ["Para el estudio, la tecnica Pomodoro funciona genial. La has probado?", "Organiza tus temas por prioridad. Yo puedo ayudarte a hacer un plan."],
            "amor": ["Las relaciones son complejas. Lo importante es que seas fiel a ti mismo.", "La comunicacion honesta suele ser la clave. Has intentado hablarlo?"],
            "salud": ["Tu salud es lo mas importante. Has considerado consultar a un profesional?", "Pequenos habitos diarios hacen grandes cambios. Empieza poco a poco."],
            "dinero": ["El estres financiero es real. Has hecho un presupuesto?", "Recuerda: tu valor no depende de tu cuenta bancaria."]
        }
        return random.choice(advice_templates.get(main_topic, [
            "Gracias por confiar en mi. Mi consejo: se paciente contigo mismo. Todo pasa.",
            "Confia en tu intuicion. Tu sabes mas de lo que crees."
        ]))

    def get_conversation_summary_for_display(self) -> str:
        return self.conversation_summary or "Conversacion nueva, sin historial previo."

    def _check_and_save_music_recommendation(self, user_input: str, response: str):
        user_lower = user_input.lower()
        response_lower = response.lower()
        is_music_question = ("musica" in user_lower and any(w in user_lower for w in ["recomienda", "recomiendas", "que musica"]))
        is_music_response = any(w in response_lower for w in ["recomiendo", "te recomiendo", "cancion", "cancion"])
        if not (is_music_question or is_music_response):
            return
        song_patterns = [
            r'te recomiendo ["\']?([^"\'.!?\n]{3,60})["\']?',
            r'recomiendo ["\']?([^"\'.!?\n]{3,60})["\']?',
            r'"([^"]{3,60})"',
        ]
        songs_found = []
        for pattern in song_patterns:
            for match in re.findall(pattern, response, re.IGNORECASE):
                clean = match.strip().strip('"').strip("'")
                if 2 < len(clean) < 100 and clean not in songs_found:
                    songs_found.append(clean)
        if songs_found and self.amigo:
            self.amigo.last_recommendations.append({
                "type": "music_recommendation",
                "songs": songs_found[:2],
                "timestamp": datetime.now().isoformat()
            })
            self.amigo.last_recommendations = self.amigo.last_recommendations[-5:]

    def _remove_emojis(self, text: str) -> str:
        emoji_pattern = re.compile(
            "["
            u"\U0001F600-\U0001F64F"
            u"\U0001F300-\U0001F5FF"
            u"\U0001F680-\U0001F6FF"
            u"\U0001F1E0-\U0001F1FF"
            u"\u2600-\u26FF"
            u"\u2700-\u27BF"
            u"\uFE00-\uFE0F"
            u"\u200D"
            u"\u2640-\u2642"
            "]+",
            flags=re.UNICODE
        )
        return emoji_pattern.sub('', text).strip()

    def fallback_response(self, user_input: str, emotion_data: dict, personality: dict) -> str:
        mood = emotion_data.get("mood", "neutral")
        name = self.user_profile.data["basic_info"].get("name", "")
        name_prefix = f"{name}, " if name else ""
        responses = {
            "feliz": [f"{name_prefix}Me alegra escucharte asi. Cuentame mas.", "Que buena onda! Que te tiene tan bien?"],
            "triste": [f"{name_prefix}Lo siento mucho. Quieres hablar de ello? Estoy aqui.", "Entiendo que sea dificil. No estas solo."],
            "enojado": ["Respiro contigo... Que paso?", "Entiendo tu frustracion. A veces la vida es asi."],
            "ansioso": ["Respira conmigo: inhala... exhala...", "Todo va a estar bien. Un paso a la vez."],
            "cansado": ["Parece que necesitas descansar. Cuando fue tu ultima pausa?", "El cansancio es real. No te presiones tanto."],
            "neutral": ["Entiendo. Hay algo mas en lo que pueda ayudarte?", "Cuentame mas sobre eso."]
        }
        return random.choice(responses.get(mood, responses["neutral"]))