"""
😊 ANALIZADOR DE EMOCIONES
Detecta estado de ánimo del usuario
"""

import re
from typing import Dict, List

class EmotionAnalyzer:
    def __init__(self):
        # Diccionario de palabras emocionales en español
        self.emotion_lexicon = {
            "feliz": ["feliz", "contento", "alegre", "genial", "excelente", "maravilloso", 
                     "fantástico", "increíble", "perfecto", "encantado", "radiante", "eufórico",
                     "bien", "mejor", "increíble", "chévere", "bacano", "padre", "chido"],
            "triste": ["triste", "deprimido", "melancólico", "llorar", "llanto", "dolor", 
                      "sufrimiento", "desanimado", "apagado", "vacío", "solo", "aburrido",
                      "mal", "peor", "horrible", "fatal", "decepcionado"],
            "enojado": ["enojado", "furioso", "molesto", "irritado", "cabreado", "odio", 
                       "rabia", "frustrado", "indignado", "harto", "estresado", "agobiado"],
            "ansioso": ["ansioso", "nervioso", "preocupado", "angustiado", 
                       "tensión", "pánico", "miedo", "inseguro", "dudoso"],
            "cansado": ["cansado", "agotado", "exhausto", "somnoliento", "dormir", "fatiga",
                       "sin energía", "rendido", "pesado"],
            "emocionado": ["emocionado", "expectante", "ilusionado", "motivado", "inspirado",
                          "entusiasmado", "ansioso_positivo", "feliz"]
        }

        # Intensificadores
        self.intensifiers = ["muy", "super", "extremadamente", "demasiado", "bastante", "tan",
                            "re", "ultra", "mega", "hyper"]
        self.negations = ["no", "nunca", "jamás", "tampoco", "sin", "ni"]

    def analyze(self, text: str) -> Dict:
        """Analiza texto y devuelve estado emocional"""
        text_lower = text.lower()
        words = text_lower.split()

        scores = {emotion: 0 for emotion in self.emotion_lexicon}

        for i, word in enumerate(words):
            for emotion, keywords in self.emotion_lexicon.items():
                if word in keywords:
                    score = 1.0

                    # Verificar intensificadores
                    if i > 0 and words[i-1] in self.intensifiers:
                        score += 0.5

                    # Verificar negaciones (3 palabras antes)
                    start = max(0, i-3)
                    if any(n in words[start:i] for n in self.negations):
                        score *= -0.5  # Negación invierte y reduce

                    scores[emotion] += score

        # Determinar emoción dominante
        if max(scores.values()) == 0:
            dominant = "neutral"
            sentiment_score = 0.0
        else:
            dominant = max(scores, key=scores.get)
            sentiment_score = scores[dominant]

            # Normalizar score entre -1 y 1
            total = sum(abs(v) for v in scores.values())
            if total > 0:
                sentiment_score = scores[dominant] / total

        return {
            "mood": dominant,
            "score": round(sentiment_score, 2),
            "all_scores": scores
        }

    def detect_music_mood(self, text: str) -> str:
        """Detecta estado de ánimo para recomendar música"""
        emotion = self.analyze(text)

        # Mapear emoción a género musical
        music_map = {
            "feliz": "pop_energetico",
            "triste": "lofi_relajante",
            "enojado": "rock_pesado",
            "ansioso": "clasica_relajante",
            "cansado": "ambient_suave",
            "emocionado": "electro_energetico",
            "neutral": "pop_variado"
        }

        return music_map.get(emotion["mood"], "pop_variado")
