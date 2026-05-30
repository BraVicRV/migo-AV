"""
GESTOR DE RUTINAS Y HORARIOS
Maneja horarios activos para evitar interacciones espontaneas
Soporta horarios por dia de la semana
"""

import schedule
import time
import threading
from datetime import datetime
from typing import List, Dict
import json
from pathlib import Path

class RoutineScheduler:
    def __init__(self, amigo_instance):
        self.amigo = amigo_instance
        self.schedule_thread = None
        self.running = False
        self.active_hours = []  # Ahora guarda {day, start, end, name, course}
        self.load_schedule()
    
    def load_schedule(self):
        """Carga horarios guardados"""
        schedule_path = Path("config/schedule.json")
        if schedule_path.exists():
            with open(schedule_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.active_hours = data.get('active_hours', [])
        else:
            # Horarios por defecto (ejemplo)
            self.active_hours = [
                {"day": "lunes", "start": "09:00", "end": "13:00", "name": "Robotica", "course": "Robotica"},
                {"day": "lunes", "start": "15:00", "end": "18:00", "name": "Ingles", "course": "Ingles"},
                {"day": "martes", "start": "09:00", "end": "13:00", "name": "Programacion", "course": "Programacion"},
                {"day": "miercoles", "start": "10:00", "end": "12:00", "name": "Matematicas", "course": "Matematicas"},
                {"day": "jueves", "start": "14:00", "end": "17:00", "name": "Fisica", "course": "Fisica"},
                {"day": "viernes", "start": "08:00", "end": "12:00", "name": "Historia", "course": "Historia"},
            ]
            self.save_schedule()
    
    def save_schedule(self):
        """Guarda horarios"""
        Path("config").mkdir(exist_ok=True)
        with open("config/schedule.json", 'w', encoding='utf-8') as f:
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
    
    def add_daily(self, hour: int, minute: int, callback, days=None):
        """Agrega una rutina diaria"""
        schedule_time = f"{hour:02d}:{minute:02d}"
        
        def wrapped_callback():
            if not self.is_in_active_hours():
                callback()
        
        if days:
            getattr(schedule.every(), days[0]).at(schedule_time).do(wrapped_callback)
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