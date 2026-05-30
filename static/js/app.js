/*
 * 🎭 AURA - Amigo Virtual
 * JavaScript Frontend - WebSocket + UI Interactiva
 */

// ═══════════════════════════════════════════════════════════
// VARIABLES GLOBALES
// ═══════════════════════════════════════════════════════════

let ws = null;
let isConnected = false;
let isListening = false;
let recognition = null;
let currentStatus = 'idle';

// Mapa de emociones a emojis
const emotionEmojis = {
    'feliz': '😊',
    'triste': '😢',
    'enojado': '😠',
    'ansioso': '😰',
    'neutral': '😐',
    'emocionado': '🤩',
    'cansado': '😴',
    'sorprendido': '😲',
    'amor': '🥰',
    'miedo': '😨'
};

// ═══════════════════════════════════════════════════════════
// INICIALIZACIÓN
// ═══════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    initSpeechRecognition();

    // Auto-focus en input
    document.getElementById('messageInput').focus();
});

// ═══════════════════════════════════════════════════════════
// WEBSOCKET
// ═══════════════════════════════════════════════════════════

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        isConnected = true;
        updateConnectionStatus(true);
        console.log('🎭 Conectado a AURA');
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleMessage(data);
    };

    ws.onclose = () => {
        isConnected = false;
        updateConnectionStatus(false);
        console.log('🔌 Desconectado. Reconectando en 3s...');
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

function handleMessage(data) {
    switch (data.type) {
        case 'system':
            handleSystemMessage(data);
            break;
        case 'response':
            handleResponse(data);
            break;
        case 'status':
            handleStatus(data);
            break;
        case 'data':
            handleData(data);
            break;
        case 'error':
            handleError(data);
            break;
    }
}

function handleSystemMessage(data) {
    if (data.action === 'connected') {
        // Actualizar info de personalidad
        if (data.data) {
            document.getElementById('auraName').textContent = data.data.name || 'AURA';
            if (data.data.personality) {
                updatePersonalityDisplay(data.data.personality);
            }
        }

        // Solicitar datos adicionales
        sendCommand('get_personality');
        sendCommand('get_tasks');
        sendCommand('get_mood_history');

        addSystemMessage(`🎭 ¡${data.data?.name || 'AURA'} está lista!`);
    } else if (data.action === 'voice_received') {
        addMessage(data.transcript, 'user');
    } else if (data.action === 'personalized') {
        addSystemMessage(data.result);
        sendCommand('get_personality');
    }
}

function handleResponse(data) {
    // Quitar indicador de "pensando"
    removeTypingIndicator();

    // Mostrar mensaje de AURA
    addAuraMessage(data.text, data.emotion);

    // Actualizar estado emocional
    if (data.emotion) {
        updateEmotionDisplay(data.emotion);
    }
}

function handleStatus(data) {
    currentStatus = data.status;

    const avatarFace = document.getElementById('avatarFace');
    const avatarGlow = document.getElementById('avatarGlow');
    const soundWave = document.getElementById('soundWave');
    const avatarMouth = document.getElementById('avatarMouth');
    const statusIndicator = document.getElementById('auraStatus');

    switch (data.status) {
        case 'thinking':
            avatarFace.classList.add('thinking');
            avatarFace.classList.remove('speaking');
            avatarGlow.classList.remove('active');
            soundWave.classList.remove('active');
            avatarMouth.classList.remove('speaking');
            statusIndicator.textContent = '💭 AURA está pensando...';
            statusIndicator.className = 'status-indicator thinking';
            addTypingIndicator();
            break;

        case 'speaking':
            avatarFace.classList.remove('thinking');
            avatarFace.classList.add('speaking');
            avatarGlow.classList.add('active');
            soundWave.classList.add('active');
            avatarMouth.classList.add('speaking');
            statusIndicator.textContent = '🗣️ AURA está hablando...';
            statusIndicator.className = 'status-indicator speaking';
            break;

        case 'idle':
            avatarFace.classList.remove('thinking', 'speaking');
            avatarGlow.classList.remove('active');
            soundWave.classList.remove('active');
            avatarMouth.classList.remove('speaking');
            statusIndicator.textContent = '✨ AURA está lista';
            statusIndicator.className = 'status-indicator';
            break;
    }
}

function handleData(data) {
    switch (data.category) {
        case 'personality':
            updatePersonalityDisplay(data.data);
            break;
        case 'tasks':
            updateTasksList(data.data);
            break;
        case 'mood':
            updateMoodHistory(data.data);
            break;
    }
}

function handleError(data) {
    removeTypingIndicator();
    addSystemMessage(`❌ Error: ${data.text}`);
}

// ═══════════════════════════════════════════════════════════
// FUNCIONES DE UI
// ═══════════════════════════════════════════════════════════

function sendMessage() {
    const input = document.getElementById('messageInput');
    const text = input.value.trim();

    if (!text || !isConnected) return;

    // Mostrar mensaje del usuario
    addMessage(text, 'user');

    // Enviar al servidor
    ws.send(JSON.stringify({
        type: 'text',
        text: text
    }));

    // Limpiar input
    input.value = '';
    input.focus();
}

function quickCommand(command) {
    const input = document.getElementById('messageInput');
    input.value = command;
    sendMessage();
}

function handleKeyPress(event) {
    if (event.key === 'Enter') {
        sendMessage();
    }
}

function addMessage(text, sender) {
    const container = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;
    messageDiv.textContent = text;
    container.appendChild(messageDiv);
    scrollToBottom();
}

function addAuraMessage(text, emotion) {
    const container = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message aura';

    const name = document.getElementById('auraName').textContent || 'AURA';

    let html = `
        <div class="message-header">
            <span>🎭</span>
            <span>${name}</span>
        </div>
        <div class="message-text">${text}</div>
        <div class="message-time">${new Date().toLocaleTimeString('es-ES', {hour: '2-digit', minute:'2-digit'})}</div>
    `;

    if (emotion && emotion.mood) {
        const emoji = emotionEmojis[emotion.mood] || '😐';
        html += `<div class="emotion-tag">${emoji} ${emotion.mood} (${emotion.sentiment_score?.toFixed(2) || '0.00'})</div>`;
    }

    messageDiv.innerHTML = html;
    container.appendChild(messageDiv);
    scrollToBottom();
}

function addSystemMessage(text) {
    const container = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message aura';
    messageDiv.style.opacity = '0.7';
    messageDiv.style.fontSize = '12px';
    messageDiv.textContent = text;
    container.appendChild(messageDiv);
    scrollToBottom();
}

function addTypingIndicator() {
    const container = document.getElementById('chatMessages');

    // Remover si ya existe
    removeTypingIndicator();

    const indicator = document.createElement('div');
    indicator.id = 'typingIndicator';
    indicator.className = 'message aura typing-indicator';
    indicator.innerHTML = '<span></span><span></span><span></span>';
    container.appendChild(indicator);
    scrollToBottom();
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.remove();
    }
}

function scrollToBottom() {
    const container = document.getElementById('chatMessages');
    container.scrollTop = container.scrollHeight;
}

// ═══════════════════════════════════════════════════════════
// PERSONALIDAD Y ESTADO
// ═══════════════════════════════════════════════════════════

function updatePersonalityDisplay(personality) {
    if (!personality) return;

    document.getElementById('auraName').textContent = personality.name || 'AURA';
    document.getElementById('auraAttitude').textContent = personality.attitude || 'cálida';
    document.getElementById('auraVoice').textContent = personality.voice_type || 'femenina suave';
    document.getElementById('auraHumor').textContent = personality.humor_level || 'moderado';
    document.getElementById('auraEmpathy').textContent = personality.empathy_level || 'alta';
}

function updateEmotionDisplay(emotion) {
    const emojiEl = document.getElementById('emotionEmoji');
    const nameEl = document.getElementById('emotionName');
    const fillEl = document.getElementById('sentimentFill');
    const scoreEl = document.getElementById('sentimentScore');

    if (emotion) {
        const emoji = emotionEmojis[emotion.mood] || '😐';
        emojiEl.textContent = emoji;
        nameEl.textContent = emotion.mood || 'Neutral';

        const score = emotion.sentiment_score || 0;
        // Convertir score (-1 a 1) a porcentaje (0 a 100)
        const percentage = ((score + 1) / 2) * 100;
        fillEl.style.width = `${percentage}%`;
        scoreEl.textContent = score.toFixed(2);
    }
}

function updateMoodHistory(history) {
    const container = document.getElementById('moodHistory');
    container.innerHTML = '';

    if (!history || history.length === 0) return;

    // Mostrar últimos 5 estados
    const recent = history.slice(-5);
    recent.forEach(mood => {
        const tag = document.createElement('span');
        tag.className = 'mood-tag';
        const emoji = emotionEmojis[mood.mood] || '😐';
        tag.textContent = `${emoji} ${mood.mood}`;
        container.appendChild(tag);
    });
}

function updateTasksList(tasks) {
    const container = document.getElementById('tasksList');
    container.innerHTML = '';

    if (!tasks || tasks.length === 0) {
        container.innerHTML = '<div class="empty-tasks">No hay tareas pendientes</div>';
        return;
    }

    tasks.forEach(task => {
        const item = document.createElement('div');
        item.className = 'task-item';
        item.innerHTML = `
            <input type="checkbox">
            <span>${task.title || task}</span>
        `;
        container.appendChild(item);
    });
}

// ═══════════════════════════════════════════════════════════
// PANELES TOGGLE
// ═══════════════════════════════════════════════════════════

function toggleTasksPanel() {
    const panel = document.getElementById('tasksPanel');
    panel.classList.toggle('hidden');
    sendCommand('get_tasks');
}

function togglePersonalizePanel() {
    const panel = document.getElementById('personalizePanel');
    panel.classList.toggle('hidden');
}

// ═══════════════════════════════════════════════════════════
// COMANDOS
// ═══════════════════════════════════════════════════════════

function sendCommand(command) {
    if (!isConnected) return;

    ws.send(JSON.stringify({
        type: 'command',
        command: command
    }));
}

function personalize(attribute, value) {
    if (!value) return;

    ws.send(JSON.stringify({
        type: 'personalize',
        attribute: attribute,
        value: value
    }));
}

// ═══════════════════════════════════════════════════════════
// RECONOCIMIENTO DE VOZ (Web Speech API)
// ═══════════════════════════════════════════════════════════

function initSpeechRecognition() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        console.log('Web Speech API no disponible');
        document.getElementById('micBtn').style.display = 'none';
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();

    recognition.lang = 'es-ES';
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => {
        isListening = true;
        document.getElementById('micBtn').classList.add('active');
        document.getElementById('micIndicator').classList.remove('hidden');
    };

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        document.getElementById('messageInput').value = transcript;

        // Enviar como mensaje de voz
        ws.send(JSON.stringify({
            type: 'voice',
            transcript: transcript
        }));

        // También enviar como texto para procesar
        setTimeout(() => sendMessage(), 100);
    };

    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        isListening = false;
        document.getElementById('micBtn').classList.remove('active');
        document.getElementById('micIndicator').classList.add('hidden');
    };

    recognition.onend = () => {
        isListening = false;
        document.getElementById('micBtn').classList.remove('active');
        document.getElementById('micIndicator').classList.add('hidden');
    };
}

function toggleMic() {
    if (!recognition) {
        alert('Tu navegador no soporta reconocimiento de voz. Usa Chrome o Edge.');
        return;
    }

    if (isListening) {
        recognition.stop();
    } else {
        recognition.start();
    }
}

// ═══════════════════════════════════════════════════════════
// UTILIDADES
// ═══════════════════════════════════════════════════════════

function updateConnectionStatus(connected) {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');

    if (connected) {
        dot.classList.add('connected');
        text.textContent = 'Conectado';
    } else {
        dot.classList.remove('connected');
        text.textContent = 'Desconectado';
    }
}

// Animación de los ojos siguiendo el cursor
document.addEventListener('mousemove', (e) => {
    const pupils = document.querySelectorAll('.pupil');
    const eyes = document.querySelectorAll('.eye');

    eyes.forEach((eye, index) => {
        const rect = eye.getBoundingClientRect();
        const eyeCenterX = rect.left + rect.width / 2;
        const eyeCenterY = rect.top + rect.height / 2;

        const angle = Math.atan2(e.clientY - eyeCenterY, e.clientX - eyeCenterX);
        const distance = Math.min(3, Math.hypot(e.clientX - eyeCenterX, e.clientY - eyeCenterY) / 20);

        const pupil = pupils[index];
        if (pupil) {
            const x = Math.cos(angle) * distance;
            const y = Math.sin(angle) * distance;
            pupil.style.transform = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`;
        }
    });
});