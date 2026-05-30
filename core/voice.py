"""
MANEJADOR DE VOZ
STT (Speech-to-Text) y TTS (Text-to-Speech)
Usa gTTS para español latino natural
"""

import tempfile
import os
import threading
import queue
import speech_recognition as sr
from gtts import gTTS
from pathlib import Path
import platform
import subprocess

class VoiceManager:
    def __init__(self):
        self.speaking = False
        self.audio_queue = queue.Queue()
        
        # Verificar disponibilidad de gTTS
        try:
            from gtts import gTTS
            self.gtts_available = True
        except ImportError:
            print("gTTS no instalado. Ejecuta: pip install gtts")
            self.gtts_available = False
            
        # Inicializar STT
        try:
            self.recognizer = sr.Recognizer()
            self.microphone = sr.Microphone()
            self.stt_available = True
            # Calibrar para ruido ambiental
            with self.microphone as source:
                print("Calibrando microfono...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                print("Microfono listo")
        except Exception as e:
            print(f"STT no disponible: {e}")
            self.stt_available = False
            
    def speak(self, text: str):
        """Convierte texto a voz en español latino"""
        if not self.gtts_available:
            print(f"[gTTS no disponible] {text}")
            return
            
        # Limpiar texto para TTS
        clean_text = self._clean_for_tts(text)
        
        # Hablar en hilo separado para no bloquear
        threading.Thread(
            target=self._speak_thread,
            args=(clean_text,),
            daemon=True
        ).start()
        
    def _speak_thread(self, text: str):
        """Hilo de reproduccion de voz con gTTS"""
        self.speaking = True
        temp_path = None
        try:
            # Crear archivo temporal para el audio
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                temp_path = fp.name
            
            # Generar audio con gTTS (espanol latino)
            tts = gTTS(text=text, lang='es', slow=False)
            tts.save(temp_path)
            
            # Reproducir segun el sistema operativo (MINIMIZADO en Windows)
            system = platform.system()
            if system == "Windows":
                # Usar start /min para minimizar la ventana
                subprocess.Popen(
                    f'start /min "" "{temp_path}"',
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            elif system == "Darwin":  # macOS
                subprocess.Popen(
                    ['afplay', temp_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:  # Linux
                subprocess.Popen(
                    f'mpg321 "{temp_path}" 2>/dev/null || mpg123 "{temp_path}" 2>/dev/null',
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                
            # Esperar un poco para que se reproduzca
            import time
            time.sleep(len(text) * 0.08)  # Aproximadamente 0.08 seg por caracter
            
            # Limpiar archivo temporal
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
                
        except Exception as e:
            print(f"Error TTS: {e}")
        finally:
            self.speaking = False
        
    def listen(self) -> str:
        """Escucha y transcribe voz del usuario"""
        if not self.stt_available:
            return input("(STT no disponible, escribe): ")
            
        try:
            with self.microphone as source:
                print("Escuchando... (habla ahora)")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                
            print("Procesando...")
            text = self.recognizer.recognize_google(audio, language="es-ES")
            print(f"Tu (voz): {text}")
            return text
            
        except sr.WaitTimeoutError:
            print("No escuche nada...")
            return ""
        except sr.UnknownValueError:
            print("No entendi, puedes repetir?")
            return ""
        except sr.RequestError as e:
            print(f"Error de conexion STT: {e}")
            return input("(Error STT, escribe): ")
        except Exception as e:
            print(f"Error STT: {e}")
            return ""
            
    def _clean_for_tts(self, text: str) -> str:
        """Limpia texto para mejor pronunciacion TTS"""
        import re
        # Eliminar emojis
        text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', '', text)
        
        # Simplificar algunas abreviaturas
        replacements = {
            "xD": "ja ja",
            ":)": "",
            ":(": "",
            "lol": "ja ja ja",
            "omg": "oh dios mio",
            "wtf": "que demonios",
            "idk": "no se"
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
            
        return text.strip()