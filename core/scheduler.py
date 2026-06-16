"""
GESTOR DE RUTINAS Y HORARIOS
Maneja horarios activos para evitar interacciones espontaneas
Soporta horarios por dia de la semana
"""

import schedule
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional, Callable
import json
from pathlib import Path

# Importar Supabase si está disponible
try:
    from core.supabase_client import get_supabase_manager
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

class RoutineScheduler:
    def __init__(self, amigo_instance, user_id: str = "default"):
        self.amigo = amigo_instance
        self.user_id = user_id
        self.schedule_thread = None
        self.running = False
        self.active_hours = []  # Ahora guarda {day, start, end, name, course}
        self.supabase = get_supabase_manager() if SUPABASE_AVAILABLE else None
        self.load_schedule()
    
    def load_schedule(self):
        """Carga horarios: primero desde Supabase, luego fallback a JSON local."""
        loaded = False

        # 1. Intentar cargar desde Supabase (multi-dispositivo)
        if self.supabase and self.supabase.is_connected():
            try:
                cloud_schedule = self.supabase.load_user_schedule(self.user_id)
                if cloud_schedule:
                    self.active_hours = cloud_schedule
                    print(f"[Scheduler] Horario cargado desde Supabase para {self.user_id}")
                    loaded = True
            except Exception as e:
                print(f"[Scheduler] Error cargando de Supabase: {e}")

        # 2. Fallback a JSON local
        if not loaded:
            schedule_path = Path(f"config/schedule_{self.user_id}.json")
            if schedule_path.exists():
                with open(schedule_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.active_hours = data.get('active_hours', [])
                print(f"[Scheduler] Horario cargado desde local para {self.user_id}")
            else:
                # Horarios por defecto solo para usuario default (no para usuarios web)
                if self.user_id == "default":
                    self.active_hours = [
                        {"day": "lunes", "start": "09:00", "end": "13:00", "name": "Robotica", "course": "Robotica"},
                        {"day": "lunes", "start": "15:00", "end": "18:00", "name": "Ingles", "course": "Ingles"},
                        {"day": "martes", "start": "09:00", "end": "13:00", "name": "Programacion", "course": "Programacion"},
                        {"day": "miercoles", "start": "10:00", "end": "12:00", "name": "Matematicas", "course": "Matematicas"},
                        {"day": "jueves", "start": "14:00", "end": "17:00", "name": "Fisica", "course": "Fisica"},
                        {"day": "viernes", "start": "08:00", "end": "12:00", "name": "Historia", "course": "Historia"},
                    ]
                    self.save_schedule()
                else:
                    self.active_hours = []
                    print(f"[Scheduler] Nuevo horario vacio para usuario {self.user_id}")
    
    def save_schedule(self):
        """Guarda horarios en Supabase y localmente."""
        # 1. Guardar en Supabase (primario)
        if self.supabase and self.supabase.is_connected():
            try:
                self.supabase.save_user_schedule(self.user_id, self.active_hours)
                print(f"[Scheduler] Horario sincronizado a Supabase para {self.user_id}")
            except Exception as e:
                print(f"[Scheduler] Error sincronizando a Supabase: {e}")

        # 2. Guardar localmente (backup/fallback)
        Path("config").mkdir(exist_ok=True)
        schedule_path = f"config/schedule_{self.user_id}.json"
        with open(schedule_path, 'w', encoding='utf-8') as f:
            json.dump({"active_hours": self.active_hours}, f, indent=2, ensure_ascii=False)
    
    def add_active_hour(self, day: str, start: str, end: str, name: str = "", course: str = ""):
        """Agrega un bloque de horario para un dia especifico"""
        self.active_hours.append({
            "day": day.lower(),
            "start": start,
            "end": end,
            "name": name or f"{start} - {end}",
            "course": course or name
        })
        self.save_schedule()
    
    def remove_active_hour(self, index: int):
        """Elimina un bloque de horario"""
        if 0 <= index < len(self.active_hours):
            self.active_hours.pop(index)
            self.save_schedule()
    
    def get_day_name(self) -> str:
        """Obtiene el nombre del dia actual en español"""
        days = {
            0: "lunes", 1: "martes", 2: "miercoles",
            3: "jueves", 4: "viernes", 5: "sabado", 6: "domingo"
        }
        return days.get(datetime.now().weekday(), "lunes")
    
    def is_in_active_hours(self) -> bool:
        """Verifica si está dentro de un horario activo (NO debe interrumpir)"""
        now = datetime.now()
        current_day = self.get_day_name()
        current_time = now.strftime("%H:%M")
        
        for block in self.active_hours:
            if block.get("day", "").lower() == current_day:
                start = block["start"]
                end = block["end"]
                if start <= current_time <= end:
                    return True
        return False
    
    def get_current_course(self) -> str:
        """Obtiene la materia/clase actual si está en horario activo"""
        now = datetime.now()
        current_day = self.get_day_name()
        current_time = now.strftime("%H:%M")
        
        for block in self.active_hours:
            if block.get("day", "").lower() == current_day:
                start = block["start"]
                end = block["end"]
                if start <= current_time <= end:
                    return block.get("course", block.get("name", "Clase"))
        return ""
    
    def get_schedule_for_day(self, day: str) -> List[Dict]:
        """Obtiene el horario para un dia especifico"""
        return [b for b in self.active_hours if b.get("day", "").lower() == day.lower()]
    
    def get_weekly_schedule(self) -> Dict[str, List[Dict]]:
        """Obtiene el horario semanal completo"""
        days = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
        weekly = {}
        for day in days:
            weekly[day] = self.get_schedule_for_day(day)
        return weekly
    
    def add_daily(self, hour, minute=None, callback=None, days=None):
        """
        Agrega una rutina diaria.
        
        Soporta dos formatos:
        1. add_daily(8, 0, callback)                    -> hora/minuto separados
        2. add_daily(dt_time(8, 0), callback)            -> objeto time
        3. add_daily(8, 0, callback, days=[0,1,2])      -> dias como numeros
        4. add_daily(8, 0, callback, days=['monday'])    -> dias como strings
        """
        # Detectar si hour es un objeto time (tiene .hour y .minute)
        if hasattr(hour, 'hour') and hasattr(hour, 'minute'):
            h, m = hour.hour, hour.minute
            # Si se paso callback en minute (segundo argumento)
            if minute is not None and callable(minute):
                callback = minute
                minute = None
        else:
            h, m = hour, minute if minute is not None else 0
        
        if callback is None:
            raise ValueError("callback es requerido")
        
        schedule_time = f"{h:02d}:{m:02d}"
        
        def wrapped_callback():
            if not self.is_in_active_hours():
                callback()
        
        # Mapeo de numeros a nombres de dias para schedule
        day_map = {
            0: "monday", 1: "tuesday", 2: "wednesday", 
            3: "thursday", 4: "friday", 5: "saturday", 6: "sunday"
        }
        
        if days:
            for d in days:
                # Convertir numero a nombre si es necesario
                day_name = day_map.get(d, d) if isinstance(d, int) else d
                try:
                    getattr(schedule.every(), day_name).at(schedule_time).do(wrapped_callback)
                except AttributeError:
                    print(f"[Scheduler] Dia invalido: {day_name}, usando daily")
                    schedule.every().day.at(schedule_time).do(wrapped_callback)
        else:
            schedule.every().day.at(schedule_time).do(wrapped_callback)
    
    def add_interval(self, minutes: int, callback):
        """Agrega rutina por intervalo"""
        def wrapped_callback():
            if not self.is_in_active_hours():
                callback()
        
        schedule.every(minutes).minutes.do(wrapped_callback)
    
    def start(self):
        """Inicia el scheduler en un hilo separado"""
        self.running = True
        self.schedule_thread = threading.Thread(target=self._run, daemon=True)
        self.schedule_thread.start()
    
    def _run(self):
        while self.running:
            schedule.run_pending()
            time.sleep(1)
    
    def stop(self):
        self.running = False
    
    def get_schedule(self) -> List[Dict]:
        """Obtiene la lista de horarios para mostrar en UI"""
        return self.active_hours