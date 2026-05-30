"""
📝 GESTOR DE TAREAS Y EVENTOS
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

class TaskManager:
    def __init__(self, storage_path: str = "data/tasks.json"):
        self.storage_path = storage_path
        Path("data").mkdir(exist_ok=True)
        self.tasks = self.load_tasks()

    def load_tasks(self) -> List[Dict]:
        """Carga tareas guardadas"""
        if Path(self.storage_path).exists():
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def save_tasks(self):
        """Guarda tareas"""
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(self.tasks, f, ensure_ascii=False, indent=2)

    def add(self, title: str, due_date: Optional[str] = None, 
            priority: str = "media", category: str = "general"):
        """Agrega nueva tarea"""
        task = {
            "id": len(self.tasks) + 1,
            "title": title,
            "created_at": datetime.now().isoformat(),
            "due_date": due_date,
            "priority": priority,
            "category": category,
            "completed": False,
            "reminded": False
        }

        self.tasks.append(task)
        self.save_tasks()

    def complete(self, task_id: int):
        """Marca tarea como completada"""
        for task in self.tasks:
            if task["id"] == task_id:
                task["completed"] = True
                self.save_tasks()
                return True
        return False

    def get_pending(self) -> List[Dict]:
        """Obtiene tareas pendientes"""
        return [t for t in self.tasks if not t["completed"]]

    def get_for_today(self) -> List[Dict]:
        """Obtiene tareas para hoy"""
        today = datetime.now().date().isoformat()
        return [
            t for t in self.tasks 
            if not t["completed"] and t.get("due_date", "").startswith(today)
        ]

    def get_upcoming(self, hours: int = 24) -> List[Dict]:
        """Obtiene eventos próximos"""
        now = datetime.now()
        future = now + timedelta(hours=hours)

        upcoming = []
        for task in self.tasks:
            if task.get("due_date"):
                try:
                    due = datetime.fromisoformat(task["due_date"])
                    if now <= due <= future and not task["completed"]:
                        upcoming.append(task)
                except:
                    pass

        return upcoming
