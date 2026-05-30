"""
📚 ASISTENTE DE ESTUDIO
Modo Pomodoro y ayuda académica
"""

import asyncio
import random
from datetime import datetime
from typing import Dict, List

class StudyAssistant:
    def __init__(self):
        self.active_session = False
        self.subject = ""
        self.pomodoro_count = 0

    def start_session(self, subject: str):
        """Inicia sesión de estudio"""
        self.active_session = True
        self.subject = subject
        self.pomodoro_count = 0

    def get_welcome_message(self, subject: str, personality: dict) -> str:
        """Mensaje de bienvenida al modo estudio"""
        messages = [
            f"¡Modo estudio activado! 📚 Vamos a dominar {subject}. ¿Listo para el primer Pomodoro de 25 min?",
            f"Perfecto, vamos a estudiar {subject}. Recuerda: 25 min de foco, 5 min de descanso. ¡Tú puedes! 💪",
            f"Modo concentración ON. {subject} no se va a aprender solo. ¿Empezamos? 🧠"
        ]
        return random.choice(messages)

    async def interactive_session(self, amigo):
        """Sesión interactiva de estudio"""
        while self.active_session:
            # Ciclo Pomodoro
            self.pomodoro_count += 1

            # Foco (25 min en producción, 10 seg para demo)
            focus_msg = f"⏱️ Pomodoro #{self.pomodoro_count}: 25 minutos de foco en {self.subject}. ¡Concentración máxima!"
            print("\n📚 [{}] {}".format(amigo.name, focus_msg))

            # Simular temporizador (en producción usar asyncio.sleep(1500))
            await asyncio.sleep(5)  # Demo: 5 segundos

            # Descanso
            if self.pomodoro_count % 4 == 0:
                break_msg = "¡Descanso largo de 15 min! Has completado 4 pomodoros. ¡Excelente trabajo! 🎉"
                await asyncio.sleep(3)  # Demo
            else:
                break_msg = "Descanso de 5 min. Levántate, estira, respira. 🧘‍♀️"
                await asyncio.sleep(2)  # Demo

            print("\n📚 [{}] {}".format(amigo.name, break_msg))

            # Preguntar si continuar
            print("\n👤 Tú: (continuar: sí/no)")
            # En implementación real, esperar input del usuario

            if self.pomodoro_count >= 2:  # Demo: terminar después de 2
                self.active_session = False

        farewell = f"¡Sesión terminada! Estudiaste {self.subject} durante {self.pomodoro_count} pomodoros. ¡Descansa! 🌟"
        print("\n📚 [{}] {}".format(amigo.name, farewell))
