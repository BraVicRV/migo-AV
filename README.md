# 🎭 Amigo Virtual - AURA

Amigo virtual personalizable con IA local, voz, memoria emocional y recordatorios.

## 📋 Requisitos

- Python 3.8+
- Windows / Linux / Mac
- Micrófono (opcional, para voz)
- Altavoces (opcional, para respuesta de voz)

## 🚀 Instalación

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 2. Instalar Ollama (para IA local)

Descarga desde: https://ollama.com

Luego ejecuta:
```bash
ollama pull qwen2.5:7b
```

> Si prefieres otro modelo: `ollama pull llama3.1:8b`

### 3. Verificar instalación

```bash
ollama list
```

Deberías ver `qwen2.5:7b` o el modelo que descargaste.

## ▶️ Ejecución

### Modo básico (solo texto)

```bash
cd amigo_virtual
python main.py
```

### Modo con voz (requiere micrófono)

El programa detectará automáticamente si tienes micrófono. Si no, usará modo texto.

## 🎮 Comandos disponibles

| Comando | Acción |
|---------|--------|
| `hola` | Saludo |
| `hora` | Dime la hora actual |
| `pon música` | Reproduce música según tu estado de ánimo |
| `recuérdame [tarea]` | Agrega un recordatorio |
| `estudiar [tema]` | Activa modo estudio Pomodoro |
| `consejo` | Pide un consejo basado en tu historial |
| `cambia tu nombre a [nombre]` | Personaliza el nombre de AURA |
| `cambia tu actitud a [cálida/energética/seria]` | Cambia la personalidad |
| `salir` / `exit` / `bye` | Apagar |

## ⚙️ Personalización

Edita `config/personality.json` para cambiar:
- Nombre del amigo
- Actitud (cálida, energética, seria, etc.)
- Nivel de humor
- Nivel de empatía
- Estilo de habla
- Géneros musicales favoritos

## 📁 Estructura

```
amigo_virtual/
├── main.py              # Punto de entrada
├── config/
│   ├── personality.json # Personalidad del amigo
│   └── user_profile.json# Perfil del usuario
├── core/
│   ├── brain.py         # Motor de IA y memoria
│   ├── voice.py         # Manejo de voz (STT/TTS)
│   ├── scheduler.py     # Recordatorios programados
│   └── emotions.py      # Análisis emocional
├── modules/
│   ├── music.py         # Reproductor musical
│   ├── tasks.py         # Gestión de tareas
│   └── study.py         # Modo estudio
└── data/
    ├── memories/        # Memoria conversacional (SQLite)
    └── audio/           # Archivos de audio temporales
```

## 🔧 Solución de problemas

### "No module named 'speechrecognition'"
```bash
pip install SpeechRecognition pyttsx3 PyAudio
```

### "Ollama no encontrado"
Asegúrate de que Ollama esté instalado y corriendo:
```bash
ollama serve
```

### "No se detecta micrófono"
El programa funcionará en modo texto. Para voz, conecta un micrófono USB.

## 🤝 Contribuir

Este proyecto es personalizable. Puedes:
- Cambiar el modelo de IA en `core/brain.py`
- Agregar nuevas personalidades en `config/`
- Extender funciones en `modules/`

---

**Creado con ❤️ para ser tu compañero virtual**
