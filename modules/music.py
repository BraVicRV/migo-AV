# modules/music.py - Usa yt-dlp para obtener URL directa del video

import random
import webbrowser
from typing import Dict, List, Optional

try:
    from yt_dlp import YoutubeDL
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    print("yt-dlp no instalado. Ejecuta: pip install yt-dlp")


class MusicRecommender:
    def __init__(self):
        self.current_song = None
        self.is_playing = False
        
        # Base de datos de busquedas por estado de animo
        self.mood_searches = {
            "feliz": ["happy upbeat music", "musica feliz", "pop alegre"],
            "triste": ["sad music", "musica triste", "melancolic songs"],
            "enojado": ["rock music", "metal music", "musica energica"],
            "ansioso": ["relaxing music", "musica relajante", "calming music"],
            "cansado": ["sleep music", "ambient music", "musica para descansar"],
            "estudio": ["lofi hip hop study", "classical music", "musica para concentrarse"],
            "relajado": ["soft piano music", "spa music", "musica tranquila"],
            "neutral": ["pop music", "latino hits", "top songs"]
        }
    
    def _get_youtube_url(self, query: str) -> Optional[str]:
        """Busca el primer video de YouTube y devuelve su URL directa"""
        if not YTDLP_AVAILABLE:
            # Fallback: abrir busqueda
            return f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
        
        try:
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,
                'default_search': 'ytsearch',
                'playlistend': 1,
            }
            
            search_query = f"ytsearch1:{query}"
            
            with YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(search_query, download=False)
                
                if 'entries' in result and result['entries']:
                    video = result['entries'][0]
                    if video and video.get('id'):
                        video_url = f"https://youtube.com/watch?v={video['id']}"
                        return video_url
                        
        except Exception as e:
            print(f"Error buscando en YouTube: {e}")
        
        return f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    
    def find_song(self, search_text: str) -> Dict:
        """Busca una cancion y obtiene su URL directa"""
        query = search_text.strip()
        
        # Obtener URL directa del video
        video_url = self._get_youtube_url(query)
        
        return {
            'title': query,
            'artist': 'YouTube',
            'url': video_url,
            'query': query
        }
    
    def recommend_for_mood(self, mood: str, user_genres: List[str]) -> Dict:
        """Recomienda musica segun estado de animo"""
        searches = self.mood_searches.get(mood, ["music"])
        query = random.choice(searches)
        
        video_url = self._get_youtube_url(query)
        
        return {
            'title': f"Musica {mood}",
            'artist': 'Recomendacion',
            'url': video_url,
            'query': query
        }
    
    def play(self, song: Dict):
        """Abre la cancion en el navegador"""
        self.current_song = song
        url = song.get('url')
        
        if url:
            print(f"Abriendo URL: {url[:80]}...")
            webbrowser.open(url)
            self.is_playing = True
        else:
            print("No se pudo abrir la cancion")
    
    def stop(self):
        """Detiene (cierra el navegador - manualmente)"""
        self.is_playing = False
        print("Para detener la musica, cierra la pestaña del navegador")
    
    def get_status(self) -> str:
        if self.is_playing:
            return "Reproduciendo en navegador"
        return "Detenido"
    
    def get_current_song(self) -> Optional[Dict]:
        return self.current_song


# Crear instancia global
music_recommender = MusicRecommender()