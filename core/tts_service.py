# core/tts_service.py
# Servicio de Texto a Voz con Edge TTS (gratuito, alta calidad)
# Soporta múltiples voces, caché y fallback a gTTS
# Sincronización de voz con el navegador y ESP32

import os
import asyncio
import base64
import tempfile
import hashlib
import json
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
    print("[TTS] ✅ Edge TTS cargado correctamente")
except ImportError as e:
    EDGE_TTS_AVAILABLE = False
    print(f"[TTS] ⚠️ Edge TTS no disponible: {e}")
    print("[TTS] Instala con: pip install edge-tts")

# Fallback a gTTS si Edge no está disponible
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
    print("[TTS] ✅ gTTS disponible como fallback")
except ImportError:
    GTTS_AVAILABLE = False
    print("[TTS] ⚠️ gTTS no disponible")


class TTSService:
    """
    Servicio de Texto a Voz usando Edge TTS.
    - Voces de alta calidad (similares a Web Speech API)
    - Caché para evitar regenerar audio
    - Soporte para múltiples voces y regiones
    - Sincronización de voz con navegador y ESP32
    - Fallback a gTTS si Edge TTS falla
    """
    
    # Mapeo de voces del navegador a Edge TTS
    voice_map = {
        # Voces femeninas
        "Microsoft Salome Online (Natural) - Spanish (Colombia)": "es-CO-SalomeNeural",
        "Microsoft Sabina Online (Natural) - Spanish (Mexico)": "es-MX-DaliaNeural",
        "Microsoft Carolina Online (Natural) - Spanish (Chile)": "es-CL-CatalinaNeural",
        "Microsoft Elena Online (Natural) - Spanish (Spain)": "es-ES-ElviraNeural",
        "Microsoft Lucia Online (Natural) - Spanish (Argentina)": "es-AR-ElenaNeural",
        # Voces masculinas
        "Microsoft Andres Online (Natural) - Spanish (Colombia)": "es-CO-GonzaloNeural",
        "Microsoft Jorge Online (Natural) - Spanish (Mexico)": "es-MX-JorgeNeural",
        "Microsoft Lorenzo Online (Natural) - Spanish (Spain)": "es-ES-AlvaroNeural",
        # Por defecto
        "default_female": "es-MX-DaliaNeural",
        "default_male": "es-MX-JorgeNeural",
    }
    
    # Voces disponibles en español (Edge TTS)
    VOICES = {
        # México (Español Latino)
        "es-MX-JorgeNeural": {"name": "Jorge", "gender": "masculino", "region": "mx"},
        "es-MX-DaliaNeural": {"name": "Dalia", "gender": "femenino", "region": "mx"},
        # España
        "es-ES-AlvaroNeural": {"name": "Álvaro", "gender": "masculino", "region": "es"},
        "es-ES-ElviraNeural": {"name": "Elvira", "gender": "femenino", "region": "es"},
        # Colombia
        "es-CO-SalomeNeural": {"name": "Salomé", "gender": "femenino", "region": "co"},
        "es-CO-GonzaloNeural": {"name": "Gonzalo", "gender": "masculino", "region": "co"},
        # Argentina
        "es-AR-ElenaNeural": {"name": "Elena", "gender": "femenino", "region": "ar"},
        # Chile
        "es-CL-CatalinaNeural": {"name": "Catalina", "gender": "femenino", "region": "cl"},
    }
    
    def __init__(self):
        self.audio_cache_dir = Path("data/audio_cache")
        self.audio_cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Mapeo de género a voz (prioridad)
        self.voice_by_gender = {
            "femenino": "es-MX-DaliaNeural",
            "masculino": "es-MX-JorgeNeural",
            "neutral": "es-ES-ElviraNeural"
        }
        
        # Voz por defecto
        self.default_voice = "es-MX-DaliaNeural"
        
        # Estadísticas de caché
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "total_audio_generated": 0
        }
        
        print(f"[TTS] 📁 Caché de audio en: {self.audio_cache_dir}")
        print(f"[TTS] 🎤 Voz por defecto: {self.default_voice}")
    
    # ============================================================
    # FUNCIONES DE MAPEO DE VOCES
    # ============================================================
    
    def get_voice_for_name(self, voice_name: str, gender: str = "femenino") -> str:
        """
        Obtiene la voz de Edge TTS correspondiente al nombre de la voz del navegador.
        
        Args:
            voice_name: Nombre de la voz del navegador (ej: "Microsoft Salome Online")
            gender: Género por defecto si no se encuentra la voz
            
        Returns:
            str: ID de la voz Edge TTS
        """
        if not voice_name:
            # Usar por defecto según género
            if gender == "masculino":
                return self.voice_map.get("default_male")
            return self.voice_map.get("default_female")
        
        # Buscar coincidencia exacta o parcial en el mapa
        voice_lower = voice_name.lower()
        for key, value in self.voice_map.items():
            if key.lower() in voice_lower or voice_lower in key.lower():
                return value
        
        # Si no se encuentra, buscar por género en el nombre
        if "male" in voice_lower or "masculino" in voice_lower or "andres" in voice_lower or "jorge" in voice_lower or "lorenzo" in voice_lower:
            return self.voice_map.get("default_male")
        
        # Por defecto femenino
        return self.voice_map.get("default_female")
    
    def get_voice_for_personality(self, gender: str = "femenino", region: str = "mx") -> str:
        """
        Devuelve la voz adecuada según la personalidad del usuario.
        
        Args:
            gender: "femenino", "masculino", "neutral"
            region: "mx", "es", "co", "ar", "cl"
            
        Returns:
            str: ID de la voz Edge TTS
        """
        # Priorizar género
        if gender in self.voice_by_gender:
            return self.voice_by_gender[gender]
        
        # Si no, buscar por región
        for voice_id, info in self.VOICES.items():
            if info.get("region") == region:
                return voice_id
        
        return self.default_voice
    
    def get_available_voices(self) -> Dict[str, Dict]:
        """Devuelve todas las voces disponibles."""
        return self.VOICES
    
    def get_voice_info(self, voice_id: str) -> Optional[Dict]:
        """Devuelve información de una voz específica."""
        return self.VOICES.get(voice_id)
    
    # ============================================================
    # FUNCIONES DE CACHÉ
    # ============================================================
    
    def _get_cache_key(self, text: str, voice: str, rate: float, pitch: float) -> str:
        """Genera una clave única para el caché."""
        content = f"{text}_{voice}_{rate}_{pitch}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()
    
    def _get_cached_audio(self, cache_key: str) -> Optional[bytes]:
        """Busca audio en caché."""
        cache_path = self.audio_cache_dir / f"{cache_key}.mp3"
        if cache_path.exists():
            # Verificar que no esté expirado (24 horas)
            mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
            if (datetime.now() - mtime).total_seconds() < 86400:  # 24 horas
                with open(cache_path, "rb") as f:
                    audio_bytes = f.read()
                self.cache_stats["hits"] += 1
                return audio_bytes
            else:
                # Archivo expirado, eliminarlo
                cache_path.unlink()
        self.cache_stats["misses"] += 1
        return None
    
    def _save_to_cache(self, cache_key: str, audio_bytes: bytes):
        """Guarda audio en caché."""
        cache_path = self.audio_cache_dir / f"{cache_key}.mp3"
        with open(cache_path, "wb") as f:
            f.write(audio_bytes)
    
    # ============================================================
    # FUNCIONES PRINCIPALES DE TTS
    # ============================================================
    
    async def text_to_speech(
        self, 
        text: str, 
        voice: Optional[str] = None,
        rate: float = 1.0, 
        pitch: float = 1.0,
        use_cache: bool = True
    ) -> Optional[bytes]:
        """
        Convierte texto a audio MP3 usando Edge TTS.
        
        Args:
            text: Texto a convertir
            voice: ID de la voz (ej: "es-MX-DaliaNeural")
            rate: Velocidad (0.5 a 2.0)
            pitch: Tono (0.5 a 2.0)
            use_cache: Si usa caché para evitar regenerar
            
        Returns:
            bytes: Audio en formato MP3, o None si falla
        """
        if not text or not text.strip():
            return None
        
        # Limpiar texto
        text = text.strip()
        
        # Usar voz por defecto si no se especifica
        if not voice:
            voice = self.default_voice
        
        # Verificar que la voz existe
        if voice not in self.VOICES and voice not in self.voice_by_gender.values():
            print(f"[TTS] ⚠️ Voz '{voice}' no encontrada, usando default")
            voice = self.default_voice
        
        # Generar clave de caché
        cache_key = self._get_cache_key(text, voice, rate, pitch)
        
        # Buscar en caché
        if use_cache:
            cached_audio = self._get_cached_audio(cache_key)
            if cached_audio:
                return cached_audio
        
        # Generar audio con Edge TTS
        if EDGE_TTS_AVAILABLE:
            try:
                audio_bytes = await self._edge_tts(text, voice, rate, pitch)
                if audio_bytes:
                    self.cache_stats["total_audio_generated"] += 1
                    # Guardar en caché
                    if use_cache:
                        self._save_to_cache(cache_key, audio_bytes)
                    return audio_bytes
            except Exception as e:
                print(f"[TTS] ❌ Edge TTS falló: {e}")
        
        # Fallback a gTTS
        if GTTS_AVAILABLE:
            try:
                print("[TTS] 🔄 Usando fallback gTTS...")
                audio_bytes = self._gtts(text)
                if audio_bytes:
                    self.cache_stats["total_audio_generated"] += 1
                    return audio_bytes
            except Exception as e:
                print(f"[TTS] ❌ gTTS falló: {e}")
        
        return None
    
    async def _edge_tts(self, text: str, voice: str, rate: float = 1.0, pitch: float = 1.0) -> bytes:
        """Genera audio con Edge TTS."""
        # Ajustar velocidad (Edge TTS usa "+XX%" o "-XX%")
        rate_percent = int((rate - 1.0) * 100)
        rate_str = f"{'+' if rate_percent >= 0 else ''}{rate_percent}%"
        
        # Ajustar tono
        pitch_percent = int((pitch - 1.0) * 100)
        pitch_str = f"{'+' if pitch_percent >= 0 else ''}{pitch_percent}Hz"
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Crear comunicador
            communicate = edge_tts.Communicate(text, voice, rate=rate_str, pitch=pitch_str)
            
            # Guardar audio
            await communicate.save(tmp_path)
            
            # Leer bytes
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()
                
            return audio_bytes
            
        except Exception as e:
            raise e
        finally:
            # Limpiar archivo temporal
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass
    
    def _gtts(self, text: str) -> bytes:
        """Genera audio con Google TTS (fallback)."""
        tts = gTTS(text=text, lang="es", slow=False)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            tts.save(tmp_path)
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()
            return audio_bytes
        except Exception as e:
            raise e
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass
    
    # ============================================================
    # FUNCIONES PARA ENVÍO AL ESP32
    # ============================================================
    
    async def text_to_speech_base64(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: float = 1.0,
        pitch: float = 1.0,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        Convierte texto a audio y retorna en base64.
        Útil para enviar al ESP32.
        
        Args:
            text: Texto a convertir
            voice: ID de la voz
            rate: Velocidad
            pitch: Tono
            use_cache: Si usa caché
            
        Returns:
            str: Audio en base64, o None si falla
        """
        audio_bytes = await self.text_to_speech(text, voice, rate, pitch, use_cache)
        if audio_bytes:
            return base64.b64encode(audio_bytes).decode("utf-8")
        return None
    
    async def text_to_speech_base64_with_voice(
        self, 
        text: str, 
        voice_name: str = None,
        gender: str = "femenino",
        rate: float = 0.95
    ) -> Optional[str]:
        """
        Convierte texto a audio usando una voz específica del navegador.
        La voice_name es el nombre de la voz del navegador (ej: "Microsoft Salome Online")
        
        Args:
            text: Texto a convertir
            voice_name: Nombre de la voz del navegador
            gender: Género por defecto si no se encuentra la voz
            rate: Velocidad (0.5 a 2.0)
            
        Returns:
            str: Audio en base64, o None si falla
        """
        if not text:
            return None
        
        # Obtener la voz de Edge TTS correspondiente
        voice = self.get_voice_for_name(voice_name, gender)
        
        # Si no se encontró, usar por defecto
        if not voice:
            voice = self.voice_map.get("default_female")
        
        # Generar audio con la voz mapeada
        return await self.text_to_speech_base64(text, voice, rate)
    
    async def text_to_speech_url(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: float = 1.0,
        pitch: float = 1.0,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        Genera audio y lo guarda en caché. Retorna URL para descarga.
        Útil para streaming al ESP32.
        
        Args:
            text: Texto a convertir
            voice: ID de la voz
            rate: Velocidad
            pitch: Tono
            use_cache: Si usa caché
            
        Returns:
            str: URL del audio, o None si falla
        """
        audio_bytes = await self.text_to_speech(text, voice, rate, pitch, use_cache)
        if not audio_bytes:
            return None
        
        cache_key = self._get_cache_key(text, voice, rate, pitch)
        cache_path = self.audio_cache_dir / f"{cache_key}.mp3"
        
        # Asegurar que el archivo existe
        if not cache_path.exists():
            self._save_to_cache(cache_key, audio_bytes)
        
        # Retornar URL (asumiendo que los archivos estáticos están montados)
        return f"/audio_cache/{cache_path.name}"
    
    # ============================================================
    # FUNCIONES DE ESTADÍSTICAS Y MANTENIMIENTO
    # ============================================================
    
    def get_cache_stats(self) -> Dict:
        """Devuelve estadísticas del caché."""
        total = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / total * 100) if total > 0 else 0
        
        return {
            "hits": self.cache_stats["hits"],
            "misses": self.cache_stats["misses"],
            "total_audio_generated": self.cache_stats["total_audio_generated"],
            "hit_rate_percent": round(hit_rate, 1),
            "cache_dir_size_mb": self._get_cache_size_mb()
        }
    
    def _get_cache_size_mb(self) -> float:
        """Calcula el tamaño total del caché en MB."""
        total_bytes = sum(f.stat().st_size for f in self.audio_cache_dir.glob("*.mp3"))
        return round(total_bytes / (1024 * 1024), 2)
    
    def cleanup_old_cache(self, max_age_hours: int = 24):
        """Limpia archivos de caché antiguos."""
        now = datetime.now()
        count = 0
        for filepath in self.audio_cache_dir.glob("*.mp3"):
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
            if (now - mtime).total_seconds() > max_age_hours * 3600:
                filepath.unlink()
                count += 1
        if count > 0:
            print(f"[TTS] 🗑️ Limpiados {count} archivos de caché antiguos")
        return count


# ============================================================
# INSTANCIA GLOBAL
# ============================================================

tts_service = TTSService()


# ============================================================
# FUNCIÓN DE PRUEBA RÁPIDA
# ============================================================

async def test_tts():
    """Prueba rápida del servicio TTS."""
    print("\n" + "="*50)
    print("🧪 Probando TTS Service")
    print("="*50)
    
    # Probar diferentes voces
    test_phrases = [
        "Hola, soy AURA, tu amiga virtual. ¿Cómo estás hoy?",
        "Me alegra verte. ¿En qué puedo ayudarte?",
    ]
    
    voices_to_test = [
        "es-MX-DaliaNeural",
        "es-MX-JorgeNeural",
        "es-ES-ElviraNeural"
    ]
    
    for voice in voices_to_test:
        voice_info = tts_service.get_voice_info(voice)
        print(f"\n🎤 Probando voz: {voice} ({voice_info.get('name', 'Unknown')})")
        
        for phrase in test_phrases:
            print(f"   📝 Texto: {phrase[:50]}...")
            
            audio = await tts_service.text_to_speech(phrase, voice)
            if audio:
                print(f"   ✅ Audio generado: {len(audio)} bytes")
            else:
                print(f"   ❌ Falló la generación")
    
    # Probar mapeo de voces del navegador
    print("\n🔍 Probando mapeo de voces del navegador:")
    browser_voices = [
        "Microsoft Salome Online (Natural) - Spanish (Colombia)",
        "Microsoft Jorge Online (Natural) - Spanish (Mexico)",
        "Voz desconocida"
    ]
    
    for voice_name in browser_voices:
        mapped = tts_service.get_voice_for_name(voice_name)
        print(f"   '{voice_name}' → '{mapped}'")
    
    # Estadísticas
    print("\n📊 Estadísticas de caché:")
    stats = tts_service.get_cache_stats()
    print(f"   Hits: {stats['hits']}")
    print(f"   Misses: {stats['misses']}")
    print(f"   Hit rate: {stats['hit_rate_percent']}%")
    print(f"   Tamaño caché: {stats['cache_dir_size_mb']} MB")
    print(f"   Audio generado: {stats['total_audio_generated']}")
    
    print("\n✅ Prueba completada")


if __name__ == "__main__":
    asyncio.run(test_tts())