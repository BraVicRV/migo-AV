"""
CLIENTE DE SUPABASE PARA AURA
Centraliza perfiles de usuario, API keys, horarios y sincronizacion
"""

import os
from typing import Dict, Optional, List
from datetime import datetime

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


class SupabaseManager:
    def __init__(self):
        self._client: Optional[Client] = None
        self._initialized = False
        self.url = ""
        self.key = ""

    def _ensure_initialized(self):
        """Inicializa la conexion bajo demanda."""
        if self._initialized:
            return

        self.url = os.getenv("SUPABASE_URL", "")
        self.key = os.getenv("SUPABASE_KEY", "")

        # Debug
        print(f"[SupabaseManager] URL: {self.url[:50] if self.url else 'VACIA'}...")
        print(f"[SupabaseManager] Key presente: {bool(self.key)}")
        print(f"[SupabaseManager] Supabase disponible: {SUPABASE_AVAILABLE}")

        if not self.url:
            print("[SupabaseManager] SUPABASE_URL no esta definida")
            self._initialized = True
            return

        if not self.key:
            print("[SupabaseManager] SUPABASE_KEY no esta definida")
            self._initialized = True
            return

        if not SUPABASE_AVAILABLE:
            print("[SupabaseManager] Libreria supabase no instalada. Ejecuta: pip install supabase")
            self._initialized = True
            return

        try:
            self._client = create_client(self.url, self.key)
            print("[SupabaseManager] Conectado correctamente")
        except Exception as e:
            print(f"[SupabaseManager] Error de conexion: {e}")
            print(f"[SupabaseManager] URL usada: {self.url[:50]}...")
            print(f"[SupabaseManager] Key longitud: {len(self.key)}")

        self._initialized = True

    def is_connected(self) -> bool:
        self._ensure_initialized()
        return self._client is not None

    def _is_duplicate_key_error(self, error) -> bool:
        """Detecta si un error es por clave duplicada (23505)."""
        error_str = str(error).lower()
        return "23505" in error_str or "duplicate key" in error_str or "unique constraint" in error_str

    def _handle_upsert(self, table: str, data: Dict, unique_field: str = "user_id") -> bool:
        """
        Intenta upsert. Si falla por duplicate key, hace update directo.
        Retorna True si el dato quedo guardado correctamente.
        """
        if not self._client:
            return False

        try:
            # Intentar upsert primero
            result = self._client.table(table).upsert(data).execute()
            return True
        except Exception as e:
            if self._is_duplicate_key_error(e):
                # Fallback: update directo
                try:
                    user_id = data.get("user_id")
                    if not user_id:
                        print(f"[Supabase] No se puede hacer update: falta user_id en datos")
                        return False

                    # Remover campos que no se deben actualizar (created_at)
                    update_data = {k: v for k, v in data.items() if k != "created_at"}

                    self._client.table(table)\
                        .update(update_data)\
                        .eq(unique_field, user_id)\
                        .execute()
                    return True
                except Exception as e2:
                    print(f"[Supabase] Error en update fallback para {table}: {e2}")
                    return False
            else:
                print(f"[Supabase] Error en upsert para {table}: {e}")
                return False

    # ============================================================
    # PERFILES DE USUARIO
    # ============================================================

    def save_user_profile(self, user_id: str, profile_data: Dict) -> bool:
        self._ensure_initialized()
        if not self._client:
            return False

        data = {
            "user_id": user_id,
            "profile_json": profile_data,
            "updated_at": datetime.now().isoformat(),
            "created_at": datetime.now().isoformat()
        }

        return self._handle_upsert("user_profiles", data)

    def load_user_profile(self, user_id: str) -> Optional[Dict]:
        self._ensure_initialized()
        if not self._client:
            return None

        try:
            result = self._client.table("user_profiles")\
                .select("profile_json")\
                .eq("user_id", user_id)\
                .execute()

            if result.data and len(result.data) > 0:
                return result.data[0]["profile_json"]
            return None
        except Exception as e:
            print(f"[Supabase] Error cargando perfil: {e}")
            return None

    # ============================================================
    # API KEYS DE GROQ
    # ============================================================

    def save_api_key(self, user_id: str, api_key: str, model: str = "llama3-8b-8192") -> bool:
        self._ensure_initialized()
        if not self._client:
            return False

        data = {
            "user_id": user_id,
            "api_key": api_key,
            "model": model,
            "is_active": True,
            "updated_at": datetime.now().isoformat()
        }

        return self._handle_upsert("user_api_keys", data)

    def get_api_key(self, user_id: str) -> Optional[str]:
        self._ensure_initialized()
        if not self._client:
            return None

        try:
            result = self._client.table("user_api_keys")\
                .select("api_key, model")\
                .eq("user_id", user_id)\
                .eq("is_active", True)\
                .execute()

            if result.data and len(result.data) > 0:
                return result.data[0]["api_key"]
            return None
        except Exception as e:
            print(f"[Supabase] Error obteniendo API key: {e}")
            return None

    # ============================================================
    # RESUMENES DE CONVERSACION
    # ============================================================

    def save_conversation_summary(self, user_id: str, summary: str, 
                                   follow_up: str = "", mood: str = "neutral") -> bool:
        self._ensure_initialized()
        if not self._client:
            return False

        try:
            data = {
                "user_id": user_id,
                "summary": summary,
                "follow_up_questions": follow_up,
                "mood_at_summary": mood,
                "created_at": datetime.now().isoformat()
            }

            # Los resumenes son insert-only (no upsert), permitimos duplicados
            result = self._client.table("conversation_summaries").insert(data).execute()
            return True
        except Exception as e:
            print(f"[Supabase] Error guardando resumen: {e}")
            return False

    def get_conversation_summaries(self, user_id: str, limit: int = 5) -> List[Dict]:
        self._ensure_initialized()
        if not self._client:
            return []

        try:
            result = self._client.table("conversation_summaries")\
                .select("*")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()

            return result.data if result.data else []
        except Exception as e:
            print(f"[Supabase] Error obteniendo resumenes: {e}")
            return []

    # ============================================================
    # HECHOS DEL USUARIO
    # ============================================================

    def sync_user_facts(self, user_id: str, facts: Dict) -> bool:
        self._ensure_initialized()
        if not self._client:
            return False

        try:
            # Borrar facts antiguos
            self._client.table("user_facts").delete().eq("user_id", user_id).execute()

            inserts = []
            for key, value_data in facts.items():
                if isinstance(value_data, dict):
                    value = value_data.get("value", "")
                    category = value_data.get("category", "general")
                else:
                    value = str(value_data)
                    category = "general"

                inserts.append({
                    "user_id": user_id,
                    "fact_key": key,
                    "fact_value": value,
                    "category": category,
                    "updated_at": datetime.now().isoformat()
                })

            if inserts:
                result = self._client.table("user_facts").insert(inserts).execute()
                return True
            return True
        except Exception as e:
            print(f"[Supabase] Error sincronizando facts: {e}")
            return False

    def get_user_facts_from_cloud(self, user_id: str) -> Dict:
        self._ensure_initialized()
        if not self._client:
            return {}

        try:
            result = self._client.table("user_facts")\
                .select("fact_key, fact_value, category")\
                .eq("user_id", user_id)\
                .execute()

            facts = {}
            for row in result.data if result.data else []:
                facts[row["fact_key"]] = {
                    "value": row["fact_value"],
                    "category": row["category"]
                }
            return facts
        except Exception as e:
            print(f"[Supabase] Error obteniendo facts: {e}")
            return {}

    # ============================================================
    # HORARIO DE CLASES (USER SCHEDULES) - NUEVO
    # ============================================================

    def save_user_schedule(self, user_id: str, schedule_data: List[Dict]) -> bool:
        """Guarda el horario completo de un usuario en Supabase."""
        self._ensure_initialized()
        if not self._client:
            return False

        try:
            # Borrar horario antiguo del usuario
            self._client.table("user_schedules").delete().eq("user_id", user_id).execute()

            # Insertar nuevo horario
            if schedule_data:
                inserts = []
                for item in schedule_data:
                    inserts.append({
                        "user_id": user_id,
                        "day": item.get("day", ""),
                        "start_time": item.get("start", ""),
                        "end_time": item.get("end", ""),
                        "name": item.get("name", ""),
                        "course": item.get("course", ""),
                        "created_at": datetime.now().isoformat()
                    })

                result = self._client.table("user_schedules").insert(inserts).execute()
            return True
        except Exception as e:
            print(f"[Supabase] Error guardando horario: {e}")
            return False

    def load_user_schedule(self, user_id: str) -> List[Dict]:
        """Carga el horario de un usuario desde Supabase."""
        self._ensure_initialized()
        if not self._client:
            return []

        try:
            result = self._client.table("user_schedules")\
                .select("day, start_time, end_time, name, course")\
                .eq("user_id", user_id)\
                .execute()

            if result.data:
                return [{
                    "day": row["day"],
                    "start": row["start_time"],
                    "end": row["end_time"],
                    "name": row["name"],
                    "course": row["course"]
                } for row in result.data]
            return []
        except Exception as e:
            print(f"[Supabase] Error cargando horario: {e}")
            return []

    # ============================================================
    # TAREAS DEL USUARIO (USER TASKS) - NUEVO
    # ============================================================

    def save_user_tasks(self, user_id: str, tasks_data: List[Dict]) -> bool:
        """Guarda las tareas de un usuario en Supabase."""
        self._ensure_initialized()
        if not self._client:
            return False

        try:
            # Borrar tareas antiguas del usuario
            self._client.table("user_tasks").delete().eq("user_id", user_id).execute()

            # Insertar nuevas tareas
            if tasks_data:
                inserts = []
                for task in tasks_data:
                    inserts.append({
                        "user_id": user_id,
                        "task_id": task.get("id", 0),
                        "title": task.get("title", ""),
                        "due_date": task.get("due_date", ""),
                        "priority": task.get("priority", "media"),
                        "category": task.get("category", "general"),
                        "completed": task.get("completed", False),
                        "created_at": task.get("created_at", datetime.now().isoformat())
                    })

                result = self._client.table("user_tasks").insert(inserts).execute()
            return True
        except Exception as e:
            print(f"[Supabase] Error guardando tareas: {e}")
            return False

    def load_user_tasks(self, user_id: str) -> Optional[List[Dict]]:
        """Carga las tareas de un usuario desde Supabase."""
        self._ensure_initialized()
        if not self._client:
            return None

        try:
            result = self._client.table("user_tasks")\
                .select("task_id, title, due_date, priority, category, completed, created_at")\
                .eq("user_id", user_id)\
                .execute()

            if result.data:
                return [{
                    "id": row["task_id"],
                    "title": row["title"],
                    "due_date": row["due_date"],
                    "priority": row["priority"],
                    "category": row["category"],
                    "completed": row["completed"],
                    "created_at": row["created_at"]
                } for row in result.data]
            return []
        except Exception as e:
            print(f"[Supabase] Error cargando tareas: {e}")
            return None

    # ============================================================
    # UTILIDADES DE LIMPIEZA (para tests)
    # ============================================================

    def delete_user_data(self, user_id: str) -> bool:
        """Borra todos los datos de un usuario. Util para tests."""
        self._ensure_initialized()
        if not self._client:
            return False

        tables = ["user_profiles", "user_api_keys", "user_facts", "conversation_summaries", "user_schedules", "user_tasks"]
        success = True

        for table in tables:
            try:
                self._client.table(table).delete().eq("user_id", user_id).execute()
            except Exception as e:
                print(f"[Supabase] Error borrando de {table}: {e}")
                success = False

        return success


# Instancia global
_supabase_manager = None

def get_supabase_manager() -> SupabaseManager:
    global _supabase_manager
    if _supabase_manager is None:
        _supabase_manager = SupabaseManager()
    return _supabase_manager

def reset_supabase_manager():
    """Fuerza la recreacion del singleton (util para tests)."""
    global _supabase_manager
    _supabase_manager = None