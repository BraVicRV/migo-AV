"""
GESTOR DE RUTINAS Y HORARIOS
Maneja horarios activos para evitar interacciones espontaneas
Soporta horarios por dia de la semana
Mejorado: soporte para consultas de "mañana", "hoy", "pasado mañana"
Mejorado: parsing de horarios en lenguaje natural
Mejorado: soporte para fechas en español
"""

import schedule
import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Callable
import json
import re
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
        # Normalizar día
        day = self._normalize_day(day)
        # Normalizar horas
        start = self._normalize_time(start)
        end = self._normalize_time(end)
        
        # Verificar si ya existe un horario igual
        for existing in self.active_hours:
            if existing.get("day") == day and existing.get("start") == start and existing.get("end") == end:
                # Actualizar nombre
                existing["name"] = name or existing["name"]
                existing["course"] = course or name or existing["course"]
                self.save_schedule()
                return
        
        self.active_hours.append({
            "day": day,
            "start": start,
            "end": end,
            "name": name or f"{start} - {end}",
            "course": course or name or f"{start} - {end}"
        })
        # Ordenar por hora
        self.active_hours.sort(key=lambda x: (x["day"], x["start"]))
        self.save_schedule()
    
    def remove_active_hour(self, index: int):
        """Elimina un bloque de horario"""
        if 0 <= index < len(self.active_hours):
            self.active_hours.pop(index)
            self.save_schedule()
    
    def get_day_name(self, date: datetime = None) -> str:
        """Obtiene el nombre del dia en español. Si no se pasa fecha, usa hoy."""
        if date is None:
            date = datetime.now()
        days = {
            0: "lunes", 1: "martes", 2: "miércoles",
            3: "jueves", 4: "viernes", 5: "sábado", 6: "domingo"
        }
        return days.get(date.weekday(), "lunes")
    
    def get_full_date_es(self, date: datetime = None) -> str:
        """
        Devuelve la fecha completa en español.
        Ejemplo: "martes 14 de julio"
        """
        if date is None:
            date = datetime.now()
        
        day_name = self.get_day_name(date)
        day_num = date.day
        month_name = self._get_month_name(date.month)
        
        return f"{day_name} {day_num} de {month_name}"
    
    def _get_month_name(self, month: int) -> str:
        """Devuelve el nombre del mes en español."""
        months = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
            5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
            9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
        }
        return months.get(month, "enero")
    
    def get_relative_day(self, text: str) -> str:
        """
        Convierte referencias relativas de tiempo a nombre de dia.
        Ej: "mañana" -> dia de mañana, "hoy" -> dia de hoy
        """
        text_lower = text.lower().strip()
        today = datetime.now()
        
        if text_lower in ["hoy", "hoy dia", "hoy día"]:
            return self.get_day_name(today)
        elif text_lower in ["mañana", "manana", "mñn"]:
            tomorrow = today + timedelta(days=1)
            return self.get_day_name(tomorrow)
        elif text_lower in ["pasado mañana", "pasado manana"]:
            day_after = today + timedelta(days=2)
            return self.get_day_name(day_after)
        elif text_lower in ["ayer"]:
            yesterday = today - timedelta(days=1)
            return self.get_day_name(yesterday)
        else:
            # Buscar nombre de dia en el texto
            days = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
            for day in days:
                if day in text_lower:
                    return day
            return self.get_day_name(today)  # Default a hoy
    
    def is_in_active_hours(self) -> bool:
        """Verifica si está dentro de un horario activo (NO debe interrumpir)"""
        now = datetime.now()
        current_day = self.get_day_name(now)
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
        current_day = self.get_day_name(now)
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
        day = self._normalize_day(day)
        return [b for b in self.active_hours if b.get("day", "").lower() == day.lower()]
    
    def get_schedule_for_relative_day(self, text: str) -> List[Dict]:
        """Obtiene el horario para un dia relativo (mañana, hoy, etc.)"""
        day = self.get_relative_day(text)
        return self.get_schedule_for_day(day)
    
    def get_weekly_schedule(self) -> Dict[str, List[Dict]]:
        """Obtiene el horario semanal completo"""
        days = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        weekly = {}
        for day in days:
            weekly[day] = self.get_schedule_for_day(day)
        return weekly
    
    def get_schedule(self) -> List[Dict]:
        """Obtiene la lista de horarios para mostrar en UI"""
        return self.active_hours
    
    def _normalize_day(self, day: str) -> str:
        """Normaliza el nombre del día a español"""
        day = day.lower().strip()
        
        # Mapeo de días
        day_map = {
            "lun": "lunes",
            "lunes": "lunes",
            "mar": "martes",
            "martes": "martes",
            "mié": "miércoles",
            "mie": "miércoles",
            "miércoles": "miércoles",
            "miercoles": "miércoles",
            "jue": "jueves",
            "jueves": "jueves",
            "vie": "viernes",
            "viernes": "viernes",
            "sab": "sábado",
            "sáb": "sábado",
            "sábado": "sábado",
            "sabado": "sábado",
            "dom": "domingo",
            "domingo": "domingo"
        }
        
        return day_map.get(day, day)
    
    def _normalize_time(self, time_str: str) -> str:
        """
        Normaliza una cadena de tiempo a formato HH:MM (24h)
        Soporta: "5", "5pm", "17:00", "5:30", "5 de la tarde", etc.
        """
        if not time_str:
            return "00:00"
        
        time_str = str(time_str).lower().strip()
        
        # Ya está en formato HH:MM
        if re.match(r'^\d{1,2}:\d{2}$', time_str):
            return time_str
        
        # Extraer hora y minutos
        hour_match = re.search(r'(\d{1,2})', time_str)
        if not hour_match:
            return "00:00"
        
        hour = int(hour_match.group(1))
        minute = 0
        
        # Buscar minutos
        minute_match = re.search(r':(\d{2})', time_str)
        if minute_match:
            minute = int(minute_match.group(1))
        
        # Buscar si es PM (tarde/noche)
        is_pm = any(word in time_str for word in ['pm', 'tarde', 'noche', 'de la tarde', 'de la noche'])
        
        # Buscar si es AM (mañana)
        is_am = any(word in time_str for word in ['am', 'mañana', 'de la mañana'])
        
        # Si es PM y la hora es menor a 12, sumar 12
        if is_pm and hour < 12:
            hour += 12
        
        # Si es AM y la hora es 12, convertir a 0
        if is_am and hour == 12:
            hour = 0
        
        # Si la hora es menor a 6 y no especifica AM/PM, probablemente es PM
        if hour < 6 and not is_am and not is_pm:
            # Si el texto contiene "tarde" o "noche", es PM
            if 'tarde' in time_str or 'noche' in time_str:
                hour += 12
            # Si contiene "mañana", es AM
            elif 'mañana' in time_str:
                # Ya está bien
                pass
        
        return f"{hour:02d}:{minute:02d}"
    
    def parse_schedule_text(self, text: str):
        """
        Parsea un texto para extraer información de horario
        Ejemplos:
        - "Agrega clase de anatomia de 5 a 7 de la tarde"
        - "Nueva clase de Matematicas el martes de 5 a 7 de la tarde"
        - "Clase de IA el lunes de 17 a 19"
        - "Agregame la clase de anatomia de 5 a 7 de la tarde"
        """
        text = text.lower().strip()
        
        # Buscar el día
        days = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        day_found = None
        for day in days:
            if day in text:
                day_found = day
                break
        
        # Si no se encuentra el día, buscar referencias relativas
        if not day_found:
            if "hoy" in text:
                day_found = self.get_day_name()
            elif "mañana" in text or "manana" in text:
                tomorrow = datetime.now() + timedelta(days=1)
                day_found = self.get_day_name(tomorrow)
            else:
                day_found = "lunes"  # Por defecto
        
        # Buscar el nombre de la clase
        name_match = re.search(r'clase\s+(?:de\s+)?([a-zA-Záéíóúñ\s]+?)(?:\s+(?:el|de|a|desde|de\s+las|\d|para|los))', text)
        if name_match:
            class_name = name_match.group(1).strip()
            # Limpiar el nombre
            class_name = re.sub(r'\s+el\s+', ' ', class_name)
            class_name = re.sub(r'\s+de\s+', ' ', class_name)
            class_name = class_name.strip()
        else:
            # Intentar otro patrón: "X el lunes" o "X de 5"
            name_match = re.search(r'^([a-zA-Záéíóúñ\s]+?)\s+(?:el|de|a|desde|para|los|las)', text)
            if name_match:
                class_name = name_match.group(1).strip()
            else:
                # Si no se encuentra, usar "Clase"
                class_name = "Clase"
        
        # Si el nombre es muy largo o contiene palabras comunes, limpiar
        class_name = class_name.replace('agregame', '').replace('agregar', '').replace('nueva', '').strip()
        class_name = class_name.replace('la clase de', '').replace('clase de', '').strip()
        class_name = class_name.replace('mi', '').strip()
        
        # Si quedó vacío, usar "Clase"
        if not class_name:
            class_name = "Clase"
        
        # Buscar horas
        time_patterns = [
            r'de\s+(\d{1,2}(?::\d{2})?)\s*(?:a|hasta|para)\s+(\d{1,2}(?::\d{2})?)\s*(?:de\s+la\s+)?(tarde|noche|mañana)?',
            r'(\d{1,2}(?::\d{2})?)\s*(?:a|hasta|para)\s+(\d{1,2}(?::\d{2})?)\s*(?:de\s+la\s+)?(tarde|noche|mañana)?',
            r'(\d{1,2}(?::\d{2})?)\s*-\s*(\d{1,2}(?::\d{2})?)\s*(?:de\s+la\s+)?(tarde|noche|mañana)?',
            r'(\d{1,2})\s*(?:a|hasta)\s+(\d{1,2})\s*(?:de\s+la\s+)?(tarde|noche|mañana)?',
        ]
        
        start_time = None
        end_time = None
        period = None
        
        for pattern in time_patterns:
            match = re.search(pattern, text)
            if match:
                start_time = match.group(1)
                end_time = match.group(2)
                if len(match.groups()) > 2:
                    period = match.group(3)
                
                # Si hay período (tarde/noche/mañana), agregarlo
                if period:
                    if 'tarde' in period or 'noche' in period:
                        start_time = f"{start_time} pm"
                        end_time = f"{end_time} pm"
                    elif 'mañana' in period:
                        start_time = f"{start_time} am"
                        end_time = f"{end_time} am"
                break
        
        if not start_time or not end_time:
            return None
        
        # Normalizar horas
        start = self._normalize_time(start_time)
        end = self._normalize_time(end_time)
        
        # Si la hora de fin es menor que la de inicio, asumir que es PM
        try:
            if int(end.replace(':', '')) < int(start.replace(':', '')):
                end_hour = int(end.split(':')[0]) + 12
                if end_hour >= 24:
                    end_hour -= 24
                end = f"{end_hour:02d}:{end.split(':')[1]}"
        except:
            pass
        
        return {
            "day": day_found,
            "start": start,
            "end": end,
            "name": class_name.capitalize(),
            "course": class_name.capitalize()
        }
    
    def format_schedule_text(self, schedule: Dict = None) -> str:
        """Formatea el horario para mostrarlo en el chat"""
        if schedule is None:
            schedule = self.get_weekly_schedule()
        
        days = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        result = []
        
        for day in days:
            classes = schedule.get(day, [])
            if classes:
                class_list = []
                for cls in classes:
                    class_list.append(f"  • {cls.get('name', 'Clase')} de {cls.get('start', '')} a {cls.get('end', '')}")
                result.append(f"**{day.capitalize()}:**")
                result.extend(class_list)
        
        if not result:
            return "📭 No tienes clases agendadas."
        
        return "\n".join(result)
    
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