"""
ANALIZADOR DE EMOCIONES MEJORADO
- Análisis de frase completa (no palabra por palabra)
- Ventana de contexto para negaciones (maneja "no estoy mal")
- Intensificadores acumulativos ("muy muy cansado")
- Detección de emociones mixtas ("feliz pero nervioso")
- Historial emocional con tendencia
- Puntuación normalizada entre -1.0 y 1.0
"""

import re
from typing import Dict, List, Tuple, Optional
from collections import deque
from datetime import datetime


class EmotionAnalyzer:
    def __init__(self):
        # Léxico emocional expandido con pesos diferenciados
        self.emotion_lexicon = {
            "feliz": {
                "alta": ["eufórico", "encantado", "radiante", "maravilloso", "increíble",
                         "fantástico", "perfecto", "espectacular", "dichoso", "exultante"],
                "media": ["feliz", "contento", "alegre", "genial", "excelente", "animado",
                          "bien", "chévere", "bacano", "padre", "chido", "guay", "buenísimo"],
                "baja": ["mejor", "tranquilo", "calmado", "ok", "bien", "normal", "regular"]
            },
            "triste": {
                "alta": ["deprimido", "destrozado", "desesperado", "hundido", "desolado",
                         "angustiado", "roto", "devastado"],
                "media": ["triste", "melancólico", "llorar", "llanto", "desanimado",
                          "apagado", "vacío", "solo", "decepcionado", "mal", "horrible", "fatal"],
                "baja": ["aburrido", "peor", "bajo", "alicaído", "flojo"]
            },
            "enojado": {
                "alta": ["furioso", "iracundo", "rabioso", "odio", "exploto", "harto",
                         "indignado", "exasperado"],
                "media": ["enojado", "molesto", "irritado", "cabreado", "rabia",
                          "frustrado", "estresado", "agobiado"],
                "baja": ["incómodo", "fastidiado", "mosqueado"]
            },
            "ansioso": {
                "alta": ["pánico", "terror", "aterrado", "paranoico", "colapso"],
                "media": ["ansioso", "nervioso", "preocupado", "angustiado",
                          "tensión", "miedo", "inseguro", "inquieto", "agitado"],
                "baja": ["dudoso", "indeciso", "intranquilo"]
            },
            "cansado": {
                "alta": ["agotado", "exhausto", "rendido", "muerto de cansancio",
                         "sin fuerzas", "derrumbado"],
                "media": ["cansado", "somnoliento", "fatiga", "sin energía",
                          "pesado", "dormir", "sueño"],
                "baja": ["perezoso", "lento", "sin ganas"]
            },
            "emocionado": {
                "alta": ["emocionadísimo", "eufórico", "loco de alegría", "súper motivado"],
                "media": ["emocionado", "expectante", "ilusionado", "motivado",
                          "inspirado", "entusiasmado"],
                "baja": ["interesado", "curioso", "animado"]
            }
        }

        # Pesos por intensidad
        self.intensity_weights = {"alta": 1.5, "media": 1.0, "baja": 0.6}

        # Intensificadores con multiplicadores distintos
        self.intensifiers = {
            "muy": 1.4, "super": 1.5, "súper": 1.5, "extremadamente": 1.8,
            "demasiado": 1.6, "bastante": 1.3, "tan": 1.2, "re": 1.4,
            "ultra": 1.6, "mega": 1.5, "hyper": 1.5, "totalmente": 1.4,
            "completamente": 1.5, "absolutamente": 1.5, "increíblemente": 1.7
        }

        # Atenuadores (reducen la intensidad)
        self.attenuators = {
            "un poco": 0.5, "algo": 0.6, "medio": 0.6, "ligeramente": 0.4,
            "levemente": 0.4, "más o menos": 0.5, "casi": 0.7, "apenas": 0.4,
            "un tanto": 0.5, "poquito": 0.35, "poco": 0.5
        }

        # Negaciones (ventana de 4 tokens antes de la palabra emocional)
        self.negations = ["no", "nunca", "jamás", "tampoco", "sin", "ni",
                          "nada", "ningún", "ninguna", "nadie"]

        # Conectores de contraste (detectan emoción mixta)
        self.contrast_connectors = ["pero", "aunque", "sin embargo", "a pesar",
                                    "no obstante", "aun así", "igual", "de todas formas"]

        # Historial emocional de la sesión (últimas 20 detecciones)
        self.session_history: deque = deque(maxlen=20)

        # Índice plano para búsqueda rápida: palabra -> (emocion, intensidad)
        self._flat_index: Dict[str, Tuple[str, str]] = {}
        self._build_flat_index()

    # ------------------------------------------------------------------
    # Construcción del índice plano
    # ------------------------------------------------------------------

    def _build_flat_index(self):
        for emotion, levels in self.emotion_lexicon.items():
            for level, words in levels.items():
                for word in words:
                    # Si una palabra ya existe, conservar la de mayor peso
                    if word not in self._flat_index:
                        self._flat_index[word] = (emotion, level)
                    else:
                        existing_level = self._flat_index[word][1]
                        if self.intensity_weights[level] > self.intensity_weights[existing_level]:
                            self._flat_index[word] = (emotion, level)

    # ------------------------------------------------------------------
    # API pública principal
    # ------------------------------------------------------------------

    def analyze(self, text: str) -> Dict:
        """
        Analiza el texto y devuelve:
        {
            "mood": str,             # emoción dominante
            "score": float,          # -1.0 a 1.0
            "secondary_mood": str,   # segunda emoción si hay mezcla
            "all_scores": dict,      # puntuación de cada emoción
            "is_mixed": bool,        # si hay emociones mixtas
            "negated": bool,         # si la emoción fue negada
            "trend": str             # "mejorando" / "empeorando" / "estable"
        }
        """
        text_clean = self._normalize(text)
        segments = self._split_by_contrast(text_clean)

        all_scores = {e: 0.0 for e in self.emotion_lexicon}

        for segment, is_contrast in segments:
            seg_scores = self._score_segment(segment)
            # Los segmentos de contraste se suman con peso 0.6
            weight = 0.6 if is_contrast else 1.0
            for emotion, score in seg_scores.items():
                all_scores[emotion] += score * weight

        # Emoción dominante y secundaria
        sorted_emotions = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
        dominant_emotion, dominant_score = sorted_emotions[0]
        secondary_emotion, secondary_score = sorted_emotions[1]

        is_neutral = dominant_score == 0.0
        is_mixed = (not is_neutral and secondary_score > 0 and
                    secondary_score >= dominant_score * 0.55)

        if is_neutral:
            mood = "neutral"
            normalized_score = 0.0
        else:
            mood = dominant_emotion
            # Normalizar score usando suma total
            total = sum(abs(v) for v in all_scores.values())
            normalized_score = round(dominant_score / total, 3) if total > 0 else 0.0
            normalized_score = max(-1.0, min(1.0, normalized_score))

        # Registrar en historial de sesión
        entry = {
            "timestamp": datetime.now().isoformat(),
            "mood": mood,
            "score": normalized_score,
            "text_snippet": text[:60]
        }
        self.session_history.append(entry)

        return {
            "mood": mood,
            "score": normalized_score,
            "secondary_mood": secondary_emotion if is_mixed else None,
            "all_scores": {k: round(v, 3) for k, v in all_scores.items()},
            "is_mixed": is_mixed,
            "negated": self._check_if_negated(text_clean),
            "trend": self._compute_trend()
        }

    # ------------------------------------------------------------------
    # Análisis por segmento
    # ------------------------------------------------------------------

    def _score_segment(self, segment: str) -> Dict[str, float]:
        """Puntúa un segmento de texto respetando negaciones e intensificadores."""
        scores = {e: 0.0 for e in self.emotion_lexicon}
        tokens = segment.split()
        n = len(tokens)

        # Detectar frases de atenuador multi-token antes de iterar
        attenuator_spans = self._find_attenuator_spans(segment)

        i = 0
        while i < n:
            token = tokens[i]

            # Buscar en el índice plano
            if token in self._flat_index:
                emotion, level = self._flat_index[token]
                base_score = self.intensity_weights[level]

                # Ventana hacia atrás (hasta 4 tokens): negaciones, intensificadores, atenuadores
                window_start = max(0, i - 4)
                window = tokens[window_start:i]
                window_str = " ".join(window)

                # ¿Negación en ventana?
                has_negation = any(neg in window for neg in self.negations)

                # ¿Intensificador? (multiplicar el más cercano)
                intensifier_mult = 1.0
                for j in range(i - 1, window_start - 1, -1):
                    if tokens[j] in self.intensifiers:
                        intensifier_mult *= self.intensifiers[tokens[j]]
                        # Si hay dos intensificadores consecutivos ("muy muy"), sumarlos
                        if j > 0 and tokens[j - 1] in self.intensifiers:
                            intensifier_mult *= self.intensifiers[tokens[j - 1]] * 0.5
                        break

                # ¿Atenuador multi-token?
                attenuator_mult = 1.0
                for span_start, span_end, mult in attenuator_spans:
                    if span_start < i:
                        attenuator_mult = mult
                        break

                final_score = base_score * intensifier_mult * attenuator_mult

                if has_negation:
                    # Negación: invierte la emoción con penalización
                    opposite = self._opposite_emotion(emotion)
                    scores[opposite] += final_score * 0.5
                else:
                    scores[emotion] += final_score

            # Detectar frases emocionales compuestas (ej: "sin energía", "muerto de cansancio")
            else:
                bigram = " ".join(tokens[i:i+2]) if i + 1 < n else ""
                trigram = " ".join(tokens[i:i+3]) if i + 2 < n else ""
                for phrase in [trigram, bigram]:
                    if phrase and phrase in self._flat_index:
                        emotion, level = self._flat_index[phrase]
                        scores[emotion] += self.intensity_weights[level]
                        break

            i += 1

        return scores

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _normalize(self, text: str) -> str:
        text = text.lower()
        # Normalizar caracteres acentuados para el matching
        # (mantenemos los acentos pero limpiamos puntuación)
        text = re.sub(r'[^\w\sáéíóúüñ]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _split_by_contrast(self, text: str) -> List[Tuple[str, bool]]:
        """
        Divide el texto en segmentos marcando los de contraste.
        Ej: "estoy feliz pero nervioso" -> [("estoy feliz", False), ("nervioso", True)]
        """
        segments = []
        remainder = text
        is_contrast = False

        for connector in self.contrast_connectors:
            if connector in remainder:
                parts = remainder.split(connector, 1)
                segments.append((parts[0].strip(), False))
                remainder = parts[1].strip()
                is_contrast = True

        segments.append((remainder, is_contrast))
        return segments if segments else [(text, False)]

    def _find_attenuator_spans(self, segment: str) -> List[Tuple[int, int, float]]:
        """Encuentra posiciones de frases atenuadoras en el segmento."""
        spans = []
        tokens = segment.split()
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]} {tokens[i+1]}"
            if bigram in self.attenuators:
                spans.append((i, i + 2, self.attenuators[bigram]))
        return spans

    def _check_if_negated(self, text: str) -> bool:
        """Verifica si la emoción principal está negada globalmente."""
        tokens = text.split()
        for i, token in enumerate(tokens):
            if token in self._flat_index:
                window = tokens[max(0, i-4):i]
                if any(neg in window for neg in self.negations):
                    return True
        return False

    def _opposite_emotion(self, emotion: str) -> str:
        """Mapea una emoción a su opuesta para el efecto de negación."""
        opposites = {
            "feliz": "triste",
            "triste": "feliz",
            "enojado": "feliz",
            "ansioso": "cansado",
            "cansado": "feliz",
            "emocionado": "triste"
        }
        return opposites.get(emotion, "neutral")

    def _compute_trend(self) -> str:
        """
        Calcula si el estado emocional de la sesión va mejorando o empeorando.
        Usa las últimas 5 entradas del historial.
        """
        if len(self.session_history) < 3:
            return "estable"

        positive_moods = {"feliz", "emocionado"}
        negative_moods = {"triste", "enojado", "ansioso", "cansado"}

        recent = list(self.session_history)[-5:]
        scores = []
        for entry in recent:
            if entry["mood"] in positive_moods:
                scores.append(1)
            elif entry["mood"] in negative_moods:
                scores.append(-1)
            else:
                scores.append(0)

        if len(scores) < 2:
            return "estable"

        # Comparar primera mitad con segunda mitad
        mid = len(scores) // 2
        first_half = sum(scores[:mid]) / mid
        second_half = sum(scores[mid:]) / (len(scores) - mid)
        diff = second_half - first_half

        if diff >= 0.5:
            return "mejorando"
        elif diff <= -0.5:
            return "empeorando"
        return "estable"

    # ------------------------------------------------------------------
    # Utilidades públicas
    # ------------------------------------------------------------------

    def detect_music_mood(self, text: str) -> str:
        """Detecta estado de ánimo para recomendar música."""
        emotion = self.analyze(text)
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

    def get_session_summary(self) -> Dict:
        """Resumen emocional de la sesión actual para usar en el contexto de la IA."""
        if not self.session_history:
            return {"dominant_mood": "neutral", "trend": "estable", "entries": 0}

        mood_counts: Dict[str, int] = {}
        for entry in self.session_history:
            mood_counts[entry["mood"]] = mood_counts.get(entry["mood"], 0) + 1

        dominant = max(mood_counts, key=mood_counts.get)
        return {
            "dominant_mood": dominant,
            "mood_counts": mood_counts,
            "trend": self._compute_trend(),
            "entries": len(self.session_history),
            "last_mood": self.session_history[-1]["mood"] if self.session_history else "neutral"
        }

    def get_last_moods(self, n: int = 5) -> List[Dict]:
        """Devuelve las últimas N entradas del historial emocional."""
        return list(self.session_history)[-n:]

    def detect_pessimism_trend(self, threshold: float = -0.3, min_entries: int = 3) -> Dict:
        """
        Detecta si el usuario ha mostrado un patrón de pesimismo/negatividad reciente.
        Retorna dict con: is_pessimistic, severity, avg_score, suggestion
        """
        if len(self.session_history) < min_entries:
            return {"is_pessimistic": False, "severity": 0, "avg_score": 0, "suggestion": ""}

        recent = list(self.session_history)[-min_entries:]
        scores = [e["score"] for e in recent]
        avg_score = sum(scores) / len(scores)

        negative_emotions = {"triste", "ansioso", "enojado", "cansado"}
        neg_count = sum(1 for e in recent if e["mood"] in negative_emotions)
        neg_ratio = neg_count / len(recent)

        is_pessimistic = avg_score < threshold or neg_ratio >= 0.6

        suggestion = ""
        if is_pessimistic:
            if avg_score < -0.6:
                suggestion = "El usuario parece estar pasando por un momento muy dificil. Ofrece apoyo sincero y preguntale si quiere hablar."
            elif avg_score < -0.4:
                suggestion = "El usuario ha estado bajo de animo. Un mensaje de animo o una pregunta sobre como puede cuidarse podria ayudar."
            else:
                suggestion = "El usuario muestra algo de negatividad. Manten un tono calmado y positivo."

        return {
            "is_pessimistic": is_pessimistic,
            "severity": abs(avg_score),
            "avg_score": avg_score,
            "neg_ratio": neg_ratio,
            "suggestion": suggestion,
            "dominant_mood": max(set(e["mood"] for e in recent), key=lambda m: sum(1 for e in recent if e["mood"] == m))
        }